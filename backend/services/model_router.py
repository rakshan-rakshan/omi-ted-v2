"""
OSS-first model routing with paid-fallback chain.

Primary: Ollama (localhost:11434) — all models local, zero cost
Fallback 1: Hugging Face Inference API (free tier)
Fallback 2: OpenRouter (paid per-token)

Usage:
    from services.model_router import model_router
    emb = await model_router.embed("దేవుని ప్రేమ")
    answer = await model_router.synthesize(query, context)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
HF_API_KEY = os.getenv("HF_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")

EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 768  # target dimension (bge-m3 outputs 1024, we truncate to match pgvector)
QUERY_REWRITE_MODEL = "qwen2.5:3b"
SYNTHESIS_MODEL = "qwen2.5:7b-instruct"

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

REQUEST_TIMEOUT = 30.0
LLM_TIMEOUT = 300.0


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _detect_language(text: str) -> str:
    te_chars = sum(1 for c in text if "\u0C00" <= c <= "\u0C7F")
    return "te" if te_chars > len(text) * 0.3 else "en"


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class ModelRouter:
    """OSS-first model routing via Ollama with paid-fallback chain."""

    def __init__(self) -> None:
        self._reranker = None
        self._reranker_checked = False
        self._ollama_available: bool | None = None  # None = unchecked

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, dict]:
        """Check availability of each provider."""
        result: dict[str, dict] = {}

        # Ollama
        ollama_ok = await self._check_ollama()
        result["ollama"] = {"available": ollama_ok, "url": OLLAMA_BASE_URL}

        # HF Inference
        hf_ok = bool(HF_API_KEY)
        result["huggingface"] = {"available": hf_ok, "has_key": hf_ok}

        # OpenRouter
        or_ok = bool(OPENROUTER_API_KEY)
        result["openrouter"] = {"available": or_ok, "has_key": or_ok}

        # Reranker
        self._ensure_reranker()
        result["reranker"] = {
            "available": self._reranker is not None,
            "model": RERANKER_MODEL,
            "type": "local-sentence-transformers",
        }

        return result

    async def _check_ollama(self) -> bool:
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                self._ollama_available = resp.status_code == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float] | None:
        """Embed a single text string. Returns 768-dim vector or None."""
        if not text.strip():
            return None

        # 1. Try Ollama
        result = await self._ollama_embed(text)
        if result is not None:
            return result

        # 2. Try HF Inference API
        result = await self._hf_embed(text)
        if result is not None:
            return result

        logger.warning("All embedding providers failed for text length=%d", len(text))
        return None

    async def embed_batch(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Batch embed texts. Returns list of 768-dim vectors."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # Try Ollama batch
            batch_result = await self._ollama_embed_batch(batch)
            if batch_result:
                all_embeddings.extend(batch_result)
                continue

            # Fallback: embed one by one via HF
            for text in batch:
                emb = await self.embed(text)
                all_embeddings.append(emb if emb else [0.0] * EMBEDDING_DIM)

        return all_embeddings

    async def _ollama_embed(self, text: str) -> list[float] | None:
        """Embed via Ollama /v1/embeddings."""
        if not await self._check_ollama():
            return None
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/v1/embeddings",
                    json={"model": EMBEDDING_MODEL, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embedding = data["data"][0]["embedding"]
                return self._truncate_to_dim(embedding, EMBEDDING_DIM)
        except Exception as e:
            logger.debug("Ollama embed failed: %s", e)
            return None

    async def _ollama_embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        """Batch embed via Ollama (Ollama supports batch input)."""
        if not await self._check_ollama():
            return None
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/v1/embeddings",
                    json={"model": EMBEDDING_MODEL, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    self._truncate_to_dim(item["embedding"], EMBEDDING_DIM)
                    for item in data["data"]
                ]
        except Exception as e:
            logger.debug("Ollama batch embed failed: %s", e)
            return None

    async def _hf_embed(self, text: str) -> list[float] | None:
        """Embed via HF Inference API (free tier)."""
        if not HF_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    f"https://api-inference.huggingface.co/pipeline/feature-extraction/BAAI/bge-m3",
                    headers={"Authorization": f"Bearer {HF_API_KEY}"},
                    json={"inputs": text, "options": {"truncate": True}},
                )
                resp.raise_for_status()
                data = resp.json()
                # HF returns [[dim1, dim2, ...]] for single input
                embedding = data[0] if isinstance(data[0], list) else data
                return self._truncate_to_dim(embedding, EMBEDDING_DIM)
        except Exception as e:
            logger.debug("HF embed failed: %s", e)
            return None

    @staticmethod
    def _truncate_to_dim(vec: list[float], dim: int) -> list[float]:
        """Truncate or pad vector to target dimension."""
        if len(vec) >= dim:
            return vec[:dim]
        return vec + [0.0] * (dim - len(vec))

    # ------------------------------------------------------------------
    # Chat completion (shared)
    # ------------------------------------------------------------------

    async def _chat_ollama(self, messages: list[dict], model: str, max_tokens: int = 1024) -> str | None:
        """Call Ollama /v1/chat/completions (OpenAI-compatible)."""
        if not await self._check_ollama():
            return None
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.debug("Ollama chat (%s) failed: %s", model, e)
            return None

    async def _chat_hf(self, messages: list[dict], model: str, max_tokens: int = 1024) -> str | None:
        """Call HF Inference API for text generation."""
        if not HF_API_KEY:
            return None
        try:
            # Convert messages to single prompt for HF inference
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers={"Authorization": f"Bearer {HF_API_KEY}"},
                    json={"inputs": prompt, "parameters": {"max_new_tokens": max_tokens}},
                )
                resp.raise_for_status()
                data = resp.json()
                return data[0]["generated_text"] if isinstance(data, list) else data.get("generated_text", "")
        except Exception as e:
            logger.debug("HF chat (%s) failed: %s", model, e)
            return None

    async def _chat_openrouter(self, messages: list[dict], model: str, max_tokens: int = 1024) -> str | None:
        """Call OpenRouter API."""
        if not OPENROUTER_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://omi-ted.app",
                    },
                    json={"model": model, "messages": messages, "max_tokens": max_tokens},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.debug("OpenRouter chat (%s) failed: %s", model, e)
            return None

    # ------------------------------------------------------------------
    # Query rewriting
    # ------------------------------------------------------------------

    async def rewrite_query(self, query: str) -> dict | None:
        """Decompose a query into structured search terms. Returns dict with 'terms' list."""
        lang = _detect_language(query)
        sys_prompt = (
            "You are a theological search query optimizer for Telugu Christian content.\n"
            "Decompose the user question into 3-5 search terms that would find relevant content\n"
            "in a sermon transcript database.\n\n"
            "Rules:\n"
            "- Include terms in the original language AND Telugu/English equivalents\n"
            "- Add theological synonyms and cross-references\n"
            "- Assign boost=2.0 to the most important term, 1.0 to others\n"
            "- Each term should be 1-5 words\n\n"
            "Return ONLY valid JSON: {\"terms\": [{\"term\": \"...\", \"language\": \"te\", \"boost\": 1.0, \"instructions\": \"...\"}]}"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": query},
        ]

        # 1. Try Ollama
        result = await self._chat_ollama(messages, QUERY_REWRITE_MODEL, max_tokens=512)
        parsed = self._parse_search_strategy(result)
        if parsed:
            return parsed

        # 2. Try HF
        result = await self._chat_hf(messages, "Qwen/Qwen2.5-1.5B-Instruct", max_tokens=512)
        parsed = self._parse_search_strategy(result)
        if parsed:
            return parsed

        # 3. Skip rewriting — return original query as single term
        return {
            "terms": [
                {"term": query, "language": lang, "boost": 2.0, "instructions": "original query"}
            ]
        }

    @staticmethod
    def _parse_search_strategy(raw: str | None) -> dict | None:
        """Parse LLM output into SearchStrategy dict."""
        if not raw:
            return None
        # Extract JSON from response (LLM might wrap in markdown)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            data = json.loads(raw[start:end])
            if "terms" in data and isinstance(data["terms"], list) and len(data["terms"]) > 0:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    # ------------------------------------------------------------------
    # Answer synthesis
    # ------------------------------------------------------------------

    async def synthesize(self, query: str, context: str, lang: str = "en") -> str:
        """Generate answer from query + context. OSS-first, paid-fallback."""
        if lang == "te":
            sys_prompt = (
                "మీరు క్రైస్తవ బోధనలు మరియు తెలుగు మంత్రిత్వ శాఖ కంటెంట్ గురించి ప్రశ్నలకు సమాధానం ఇచ్చే సహాయకుడు.\n"
                "సందర్భాన్ని ఉపయోగించి ప్రశ్నకు సమాధానం ఇవ్వండి. [1], [2] మొదలైన వాటిని ఉపయోగించి మూలాలను ఉదహరించండి.\n"
                "సంక్షిప్తంగా మరియు ఖచ్చితంగా సమాధానం ఇవ్వండి. సందర్భంలో తగినంత సమాచారం లేకపోతే, చెప్పండి."
            )
        else:
            sys_prompt = (
                "You are a helpful assistant answering questions about Christian sermons "
                "and Telugu ministry content.\n"
                "Use the following context to answer the question. Cite sources using [1], [2] etc.\n"
                "Answer concisely and accurately. If the context doesn't contain enough information, say so."
            )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ]

        # 1. Try Ollama (qwen2.5:7b-instruct)
        result = await self._chat_ollama(messages, SYNTHESIS_MODEL, max_tokens=1024)
        if result:
            return result

        # 2. Try HF Inference (Qwen2.5-7B-Instruct)
        result = await self._chat_hf(messages, "Qwen/Qwen2.5-7B-Instruct", max_tokens=1024)
        if result:
            return result

        # 3. Try OpenRouter (claude-3-haiku)
        result = await self._chat_openrouter(
            messages, "anthropic/claude-3-haiku", max_tokens=1024
        )
        if result:
            return result

        # 4. Dummy fallback
        return f"I don't have enough information to answer: {query}"

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

    def _ensure_reranker(self) -> None:
        """Lazy-load the cross-encoder reranker."""
        if self._reranker_checked:
            return
        self._reranker_checked = True
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
            logger.info("Loaded reranker: %s", RERANKER_MODEL)
        except Exception as e:
            logger.warning("Could not load reranker %s: %s", RERANKER_MODEL, e)
            self._reranker = None

    def reranker_available(self) -> bool:
        self._ensure_reranker()
        return self._reranker is not None

    async def rerank(self, query: str, chunks: list, text_attr: str = "chunk_text") -> list:
        """Rerank chunks by relevance to query. Returns sorted list."""
        self._ensure_reranker()
        if self._reranker is None or not chunks:
            return chunks

        try:
            texts = [getattr(c, text_attr, "")[:512] for c in chunks]
            pairs = [(query, t) for t in texts]
            scores = self._reranker.predict(pairs)

            scored_chunks = list(zip(chunks, scores, strict=False))
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored_chunks]
        except Exception as e:
            logger.warning("Reranking failed: %s", e)
            return chunks


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

model_router = ModelRouter()
