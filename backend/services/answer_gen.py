"""
Answer generation — RAG with Claude Haiku via OpenRouter.
"""
from __future__ import annotations

import logging
import os
import time

from config import settings

logger = logging.getLogger(__name__)


async def generate_answer(
    query: str,
    chunks: list[dict],
) -> tuple[str, list[dict], int]:
    """Generate answer from chunks. Returns (answer_text, citations, latency_ms)."""
    if not chunks:
        return "I don't have enough context to answer that question.", [], 0

    t0 = time.monotonic()

    context_parts = []
    citations = []
    for i, c in enumerate(chunks[:5]):
        label = f"[{i + 1}]"
        context_parts.append(f"{label} {c['chunk_text']}")
        citations.append({
            "index": i + 1,
            "chunk_id": c["chunk_id"],
            "title": c.get("title", ""),
        })

    context = "\n\n".join(context_parts)
    prompt = f"""You are a helpful assistant answering questions about Christian sermons and Telugu ministry content.

Use the following context to answer the question. Cite sources using [1], [2] etc.

Context:
{context}

Question: {query}

Answer concisely and accurately. If the context doesn't contain enough information, say so."""

    provider = settings.rag.generation_model
    answer = await _call_llm(prompt, provider)

    latency = int((time.monotonic() - t0) * 1000)
    return answer, citations, latency


async def _call_llm(prompt: str, provider: str) -> str:
    """Call an LLM. Supports openrouter/anthropic/* and openrouter/openai/* patterns."""
    if not provider or provider == "local":
        return _dummy_answer(prompt)

    if provider.startswith("openrouter/"):
        return await _call_openrouter(prompt, provider.replace("openrouter/", "", 1))

    return _dummy_answer(prompt)


async def _call_openrouter(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
    if not api_key:
        return _dummy_answer(prompt)

    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://omi-ted.app",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.rag.generation_max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("OpenRouter call failed: %s", e)
        return _dummy_answer(prompt)


def _dummy_answer(prompt: str) -> str:
    """Fallback: extract answer from context using simple heuristics."""
    import re

    m = re.search(r"Question: (.+)", prompt)
    question = m.group(1) if m else "your question"

    context_start = prompt.find("Context:\n")
    context_text = prompt[context_start + 9:] if context_start > 0 else ""
    context_text = re.sub(r"\[\d+\]", "", context_text).strip()
    first_sentence = context_text.split(".")[0] if context_text else ""

    if first_sentence:
        return f"Based on the available context, regarding {question}: {first_sentence}."
    return f"I don't have enough information to answer about {question}."
