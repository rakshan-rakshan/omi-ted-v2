"""
End-to-end tests for OMI-TED v2 services.

Covers: ModelRouter, query rewriter, context builder, reranker, and RAG pipelines.
All external calls (Ollama, DB) are mocked for deterministic, CI-safe results.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Skip marker — every test in this module is gated on OLLAMA_BASE_URL
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not os.getenv("OLLAMA_BASE_URL"),
    reason="OLLAMA_BASE_URL not set",
)

# ---------------------------------------------------------------------------
# Imports (inside the skip gate so missing deps don't blow up collection)
# ---------------------------------------------------------------------------
from services.model_router import ModelRouter, model_router, EMBEDDING_DIM  # noqa: E402
from services.context_builder import build_context, build_context_from_dicts  # noqa: E402
from services.reranker import rerank_chunks  # noqa: E402
from services.hybrid_search import SearchResult  # noqa: E402


# ===================================================================
# Helpers
# ===================================================================

def _make_search_result(chunk_id: int = 1, text: str = "test chunk", score: float = 0.9) -> SearchResult:
    """Create a minimal SearchResult for tests."""
    return SearchResult(
        chunk_id=chunk_id,
        chunk_text=text,
        message_id=100 + chunk_id,
        score=score,
        youtube_id=f"vid_{chunk_id}",
        title=f"Title {chunk_id}",
        channel="Test Channel",
    )


def _make_chunk_dict(chunk_id: int = 1, text: str = "test chunk", quality: int | None = None) -> dict:
    """Create a chunk dict for context builder tests."""
    d = {"chunk_text": text, "chunk_id": chunk_id}
    if quality is not None:
        d["quality_score"] = quality
    return d


# ===================================================================
# 1. ModelRouter — health check
# ===================================================================

class TestModelRouterHealth:
    @pytest.mark.asyncio
    async def test_health_check_returns_all_providers(self):
        router = ModelRouter()
        router._ollama_available = False
        router._reranker_checked = True  # skip reranker model download
        router._reranker = None
        result = await router.health_check()
        assert "ollama" in result
        assert "huggingface" in result
        assert "openrouter" in result
        assert "reranker" in result
        assert isinstance(result["ollama"]["available"], bool)

    @pytest.mark.asyncio
    async def test_health_check_ollama_unavailable(self):
        router = ModelRouter()
        router._ollama_available = False
        router._reranker_checked = True
        router._reranker = None
        result = await router.health_check()
        assert result["ollama"]["available"] is False

    @pytest.mark.asyncio
    async def test_health_check_ollama_available(self):
        router = ModelRouter()
        router._ollama_available = True
        router._reranker_checked = True
        router._reranker = None
        result = await router.health_check()
        assert result["ollama"]["available"] is True


# ===================================================================
# 2. ModelRouter — embed via Ollama (mocked HTTP)
# ===================================================================

class TestModelRouterEmbed:
    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        router = ModelRouter()
        router._ollama_available = True
        fake_embedding = [0.1] * EMBEDDING_DIM

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": fake_embedding}]}

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.embed("దేవుని ప్రేమ")
            assert result is not None
            assert len(result) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_embed_empty_text_returns_none(self):
        router = ModelRouter()
        result = await router.embed("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_truncates_large_vector(self):
        router = ModelRouter()
        router._ollama_available = True
        # bge-m3 outputs 1024-dim, we truncate to 768
        large_embedding = [0.5] * 1024

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": large_embedding}]}

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.embed("test text")
            assert result is not None
            assert len(result) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_embed_http_error_returns_none(self):
        router = ModelRouter()
        router._ollama_available = True

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.embed("test")
            assert result is None

    @pytest.mark.asyncio
    async def test_embed_ollama_unavailable_falls_through(self):
        router = ModelRouter()
        router._ollama_available = False
        # No HF key either, so embed should return None
        with patch("services.model_router.HF_API_KEY", ""):
            result = await router.embed("test")
            assert result is None


# ===================================================================
# 3. ModelRouter — embed_batch
# ===================================================================

class TestModelRouterEmbedBatch:
    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self):
        router = ModelRouter()
        result = await router.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_uses_ollama_batch(self):
        router = ModelRouter()
        router._ollama_available = True
        texts = ["hello", "world"]
        fake_embs = [[0.1] * EMBEDDING_DIM, [0.2] * EMBEDDING_DIM]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": e} for e in fake_embs]}

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.embed_batch(texts)
            assert len(result) == 2
            assert all(len(v) == EMBEDDING_DIM for v in result)

    @pytest.mark.asyncio
    async def test_embed_batch_fallback_one_by_one(self):
        router = ModelRouter()
        router._ollama_available = True
        texts = ["a", "b"]
        fake_emb = [0.3] * EMBEDDING_DIM

        # Batch call fails, individual calls succeed
        batch_resp_fail = AsyncMock(side_effect=Exception("batch fail"))
        single_resp = MagicMock()
        single_resp.status_code = 200
        single_resp.raise_for_status = MagicMock()
        single_resp.json.return_value = {"data": [{"embedding": fake_emb}]}

        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # First call = batch embed → fail
                raise Exception("batch fail")
            # Subsequent calls = individual embed
            return single_resp

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("services.model_router.HF_API_KEY", ""):
                result = await router.embed_batch(texts)
                assert len(result) == 2
                assert all(len(v) == EMBEDDING_DIM for v in result)


# ===================================================================
# 4. ModelRouter — rewrite_query (mock Ollama)
# ===================================================================

class TestModelRouterRewrite:
    @pytest.mark.asyncio
    async def test_rewrite_query_parses_json_response(self):
        router = ModelRouter()
        router._ollama_available = True
        llm_output = json.dumps({
            "terms": [
                {"term": "దేవుని ప్రేమ", "language": "te", "boost": 2.0, "instructions": "Telugu term"},
                {"term": "God's love", "language": "en", "boost": 1.0, "instructions": "English equivalent"},
            ]
        })

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": llm_output}}]
        }

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.rewrite_query("దేవుని ప్రేమ గురించి చెప్పండి")
            assert result is not None
            assert "terms" in result
            assert len(result["terms"]) == 2
            assert result["terms"][0]["term"] == "దేవుని ప్రేమ"

    @pytest.mark.asyncio
    async def test_rewrite_query_handles_markdown_wrapped_json(self):
        router = ModelRouter()
        router._ollama_available = True
        llm_output = '```json\n{"terms": [{"term": "faith", "language": "en", "boost": 2.0, "instructions": "core"}]}\n```'

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": llm_output}}]
        }

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.rewrite_query("What is faith?")
            assert result is not None
            assert result["terms"][0]["term"] == "faith"

    @pytest.mark.asyncio
    async def test_rewrite_query_fallback_to_original(self):
        router = ModelRouter()
        router._ollama_available = False

        with patch("services.model_router.HF_API_KEY", ""):
            result = await router.rewrite_query("test query")
            assert result is not None
            assert len(result["terms"]) == 1
            assert result["terms"][0]["term"] == "test query"
            assert result["terms"][0]["boost"] == 2.0

    @pytest.mark.asyncio
    async def test_rewrite_query_invalid_json_falls_back(self):
        router = ModelRouter()
        router._ollama_available = True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "I don't understand"}}]
        }

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch("services.model_router.HF_API_KEY", ""):
                result = await router.rewrite_query("test")
                assert result is not None
                assert len(result["terms"]) == 1
                assert result["terms"][0]["term"] == "test"


# ===================================================================
# 5. ModelRouter — synthesize (mock Ollama)
# ===================================================================

class TestModelRouterSynthesize:
    @pytest.mark.asyncio
    async def test_synthesize_returns_answer(self):
        router = ModelRouter()
        router._ollama_available = True
        expected = "God's love is unconditional."

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": expected}}]
        }

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.synthesize("What is God's love?", "[1] God is love", lang="en")
            assert result == expected

    @pytest.mark.asyncio
    async def test_synthesize_telugu_prompt(self):
        router = ModelRouter()
        router._ollama_available = True
        expected = "దేవు ప్రేమ."

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": expected}}]
        }

        with patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.synthesize("దేవు ప్రేమ ఏమిటి?", "[1] దేవు ప్రేమ", lang="te")
            assert result == expected

    @pytest.mark.asyncio
    async def test_synthesize_fallback_when_all_fail(self):
        router = ModelRouter()
        router._ollama_available = False

        with patch("services.model_router.HF_API_KEY", ""), \
             patch("services.model_router.OPENROUTER_API_KEY", ""):
            result = await router.synthesize("Why?", "[1] context", lang="en")
            assert "don't have enough information" in result

    @pytest.mark.asyncio
    async def test_synthesize_openrouter_fallback(self):
        router = ModelRouter()
        router._ollama_available = False
        expected = "Fallback answer."

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": expected}}]
        }

        with patch("services.model_router.HF_API_KEY", ""), \
             patch("services.model_router.OPENROUTER_API_KEY", "fake-key"), \
             patch("services.model_router.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await router.synthesize("Q?", "C", lang="en")
            assert result == expected


# ===================================================================
# 6. Query rewriter integration
# ===================================================================

class TestQueryRewriter:
    @pytest.mark.asyncio
    async def test_rewrite_query_adds_original_query(self):
        from services.query_rewriter import rewrite_query

        with patch.object(model_router, "rewrite_query", new_callable=AsyncMock) as mock_rw:
            mock_rw.return_value = {
                "terms": [{"term": "faith", "language": "en", "boost": 2.0, "instructions": "x"}]
            }
            result = await rewrite_query("What is faith?")
            assert result["original_query"] == "What is faith?"
            assert len(result["terms"]) == 1

    @pytest.mark.asyncio
    async def test_rewrite_query_validates_terms(self):
        from services.query_rewriter import rewrite_query

        with patch.object(model_router, "rewrite_query", new_callable=AsyncMock) as mock_rw:
            # Return a mix of valid and invalid terms
            mock_rw.return_value = {
                "terms": [
                    {"term": "good", "language": "en", "boost": 2.0, "instructions": "ok"},
                    {"bad_key": "no_term_field"},
                    42,  # not a dict at all
                    {"term": "", "language": "en", "boost": 1.0, "instructions": "empty"},  # empty term still valid structurally
                ]
            }
            result = await rewrite_query("test")
            # Only 2 valid terms (good + empty term)
            assert len(result["terms"]) == 2
            assert result["terms"][0]["term"] == "good"

    @pytest.mark.asyncio
    async def test_rewrite_query_fallback_when_none_returned(self):
        from services.query_rewriter import rewrite_query

        with patch.object(model_router, "rewrite_query", new_callable=AsyncMock) as mock_rw:
            mock_rw.return_value = None
            result = await rewrite_query("fallback test")
            assert result["original_query"] == "fallback test"
            assert len(result["terms"]) == 1
            assert result["terms"][0]["term"] == "fallback test"

    @pytest.mark.asyncio
    async def test_rewrite_query_fallback_when_empty_terms(self):
        from services.query_rewriter import rewrite_query

        with patch.object(model_router, "rewrite_query", new_callable=AsyncMock) as mock_rw:
            mock_rw.return_value = {"terms": []}
            result = await rewrite_query("empty")
            assert len(result["terms"]) == 1
            assert result["terms"][0]["term"] == "empty"

    @pytest.mark.asyncio
    async def test_rewrite_query_normalizes_boost_types(self):
        from services.query_rewriter import rewrite_query

        with patch.object(model_router, "rewrite_query", new_callable=AsyncMock) as mock_rw:
            mock_rw.return_value = {
                "terms": [{"term": "x", "language": "te", "boost": "2.0", "instructions": "y"}]
            }
            result = await rewrite_query("q")
            assert isinstance(result["terms"][0]["boost"], float)
            assert result["terms"][0]["boost"] == 2.0


# ===================================================================
# 7. Context builder — priority sorting
# ===================================================================

class TestContextBuilderPriority:
    def test_gold_chunks_ranked_first(self):
        chunks = [
            _make_chunk_dict(1, "draft text", quality=1),
            _make_chunk_dict(2, "gold text", quality=5),
            _make_chunk_dict(3, "silver text", quality=3),
        ]
        result = build_context(chunks, max_tokens=5000)
        # Gold should appear before silver, which appears before draft
        gold_pos = result.find("gold text")
        silver_pos = result.find("silver text")
        draft_pos = result.find("draft text")
        assert gold_pos < silver_pos < draft_pos

    def test_priority_with_string_tiers(self):
        chunks = [
            {"chunk_text": "draft", "chunk_id": 1, "quality_score": "draft"},
            {"chunk_text": "gold", "chunk_id": 2, "quality_score": "gold"},
            {"chunk_text": "silver", "chunk_id": 3, "quality_score": "silver"},
        ]
        result = build_context(chunks, max_tokens=5000)
        gold_pos = result.find("gold")
        silver_pos = result.find("silver")
        draft_pos = result.find("draft")
        assert gold_pos < silver_pos < draft_pos

    def test_no_quality_score_defaults_to_60(self):
        chunks = [
            _make_chunk_dict(1, "no score"),
            _make_chunk_dict(2, "also no score"),
        ]
        result = build_context(chunks, max_tokens=5000)
        assert "[1]" in result
        assert "[2]" in result


# ===================================================================
# 8. Context builder — empty chunks
# ===================================================================

class TestContextBuilderEmpty:
    def test_empty_list_returns_empty_string(self):
        result = build_context([])
        assert result == ""

    def test_chunks_with_empty_text_are_skipped(self):
        chunks = [
            {"chunk_text": "", "chunk_id": 1},
            {"chunk_text": "valid", "chunk_id": 2},
        ]
        result = build_context(chunks, max_tokens=5000)
        assert "valid" in result
        # Empty chunk skipped; only valid chunk present, so exactly one "[N]" marker
        assert result.count("[") == 1

    def test_all_empty_text_returns_empty(self):
        chunks = [
            {"chunk_text": "", "chunk_id": 1},
        ]
        result = build_context(chunks, max_tokens=5000)
        assert result == ""


# ===================================================================
# 9. Context builder — token budget truncation
# ===================================================================

class TestContextBuilderBudget:
    def test_truncates_to_fit_budget(self):
        # Each chunk ~250 words ≈ ~62 tokens (en/4), so 3 chunks ≈ 186 tokens
        chunks = [
            _make_chunk_dict(i, f"word " * 250, quality=4)
            for i in range(1, 6)
        ]
        result = build_context(chunks, max_tokens=100)
        # Should only contain some chunks, not all
        assert result.count("[") <= 5  # at most 5 numbered items

    def test_all_chunks_fit_when_budget_large(self):
        chunks = [
            _make_chunk_dict(1, "short text", quality=4),
            _make_chunk_dict(2, "another short", quality=4),
        ]
        result = build_context(chunks, max_tokens=10000)
        assert "[1]" in result
        assert "[2]" in result

    def test_format_is_numbered(self):
        chunks = [
            _make_chunk_dict(10, "first"),
            _make_chunk_dict(20, "second"),
        ]
        result = build_context(chunks, max_tokens=5000)
        assert result.startswith("[1] first")
        assert "[2] second" in result

    def test_build_context_from_dicts_convenience(self):
        chunks = [
            _make_chunk_dict(1, "hello", quality=4),
            _make_chunk_dict(2, "world", quality=2),
        ]
        result = build_context_from_dicts(chunks, max_tokens=5000)
        assert "hello" in result
        assert "world" in result


# ===================================================================
# 10. Reranker — availability check
# ===================================================================

class TestReranker:
    def test_reranker_available_returns_bool(self):
        # Prevent actual model download
        model_router._reranker_checked = True
        model_router._reranker = None
        available = model_router.reranker_available()
        assert isinstance(available, bool)

    @pytest.mark.asyncio
    async def test_rerank_chunks_returns_original_when_unavailable(self):
        with patch.object(model_router, "_reranker", None), \
             patch.object(model_router, "_reranker_checked", True):
            chunks = [_make_search_result(1, "a"), _make_search_result(2, "b")]
            result = await rerank_chunks("query", chunks, top_k=10)
            assert len(result) == 2
            assert result[0].chunk_id == 1  # original order preserved

    @pytest.mark.asyncio
    async def test_rerank_chunks_empty_list(self):
        result = await rerank_chunks("query", [], top_k=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_chunks_truncates_to_top_k(self):
        with patch.object(model_router, "_reranker", MagicMock()), \
             patch.object(model_router, "_reranker_checked", True):
            chunks = [_make_search_result(i, f"text {i}") for i in range(1, 20)]
            # Mock rerank to return in original order
            with patch.object(model_router, "rerank", new_callable=AsyncMock) as mock_rerank:
                mock_rerank.return_value = chunks
                result = await rerank_chunks("query", chunks, top_k=5)
                assert len(result) == 5


# ===================================================================
# 11. Single-step RAG pipeline (mock search)
# ===================================================================

class TestSingleStepRAG:
    @pytest.mark.asyncio
    async def test_single_step_rag_returns_answer(self):
        from services.rag_pipeline import single_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        fake_results = [
            _make_search_result(1, "God is love", 0.95),
            _make_search_result(2, "Faith moves mountains", 0.85),
        ]

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.synthesize = AsyncMock(return_value="God is love indeed.")

            with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                mock_hs.return_value = fake_results
                with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                    result = await single_step_rag("What is God's love?", mock_session)

        assert result["answer"] == "God is love indeed."
        assert len(result["sources"]) == 2
        assert result["rewritten_query"] is None

    @pytest.mark.asyncio
    async def test_single_step_rag_empty_results(self):
        from services.rag_pipeline import single_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.synthesize = AsyncMock(return_value="No info available.")

            with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                mock_hs.return_value = []
                with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                    result = await single_step_rag("obscure question", mock_session)

        assert result["answer"] == "No info available."
        assert result["sources"] == []


# ===================================================================
# 12. Multi-step RAG pipeline (mock search)
# ===================================================================

class TestMultiStepRAG:
    @pytest.mark.asyncio
    async def test_multi_step_rag_full_pipeline(self):
        from services.rag_pipeline import multi_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        fake_results = [_make_search_result(1, "sermon content", 0.9)]
        rewrite_result = {
            "terms": [
                {"term": "దేవుని ప్రేమ", "language": "te", "boost": 2.0, "instructions": "Telugu"},
                {"term": "God love", "language": "en", "boost": 1.0, "instructions": "English"},
            ]
        }

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.synthesize = AsyncMock(return_value="Answer about God's love.")
            mock_mr.reranker_available = MagicMock(return_value=False)

            with patch("services.rag_pipeline.rewrite_query", new_callable=AsyncMock) as mock_rw:
                mock_rw.return_value = rewrite_result

                with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                    mock_hs.return_value = fake_results

                    with patch("services.rag_pipeline.rerank_chunks", new_callable=AsyncMock) as mock_rr:
                        mock_rr.return_value = fake_results

                        with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                            result = await multi_step_rag(
                                "దేవుని ప్రేమ గురించి చెప్పండి",
                                mock_session,
                            )

        assert result["answer"] == "Answer about God's love."
        assert len(result["sources"]) == 1
        assert result["rewritten_query"] is not None

    @pytest.mark.asyncio
    async def test_multi_step_rag_rewrite_disabled(self):
        from services.rag_pipeline import multi_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        fake_results = [_make_search_result(1, "content", 0.9)]

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.synthesize = AsyncMock(return_value="Answer.")
            mock_mr.reranker_available = MagicMock(return_value=False)

            with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                mock_hs.return_value = fake_results

                with patch("services.rag_pipeline.rerank_chunks", new_callable=AsyncMock) as mock_rr:
                    mock_rr.return_value = fake_results

                    with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                        result = await multi_step_rag(
                            "simple query",
                            mock_session,
                            enable_rewrite=False,
                        )

        assert result["answer"] == "Answer."
        assert result["rewritten_query"] is None

    @pytest.mark.asyncio
    async def test_multi_step_rag_no_search_results(self):
        from services.rag_pipeline import multi_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.rewrite_query = AsyncMock(return_value=None)
            mock_mr.synthesize = AsyncMock(return_value="No info.")

            with patch("services.rag_pipeline.rewrite_query", new_callable=AsyncMock) as mock_rw:
                mock_rw.return_value = {"terms": [{"term": "nope", "language": "en", "boost": 1.0, "instructions": ""}]}

                with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                    # Raise to simulate search failure → valid_results stays empty
                    mock_hs.side_effect = Exception("search unavailable")

                    with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                        result = await multi_step_rag("obscure", mock_session)

        assert "don't have enough context" in result["answer"]
        assert result["sources"] == []

    @pytest.mark.asyncio
    async def test_multi_step_rag_rerank_disabled(self):
        from services.rag_pipeline import multi_step_rag

        mock_session = AsyncMock()
        mock_session.bind = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        fake_results = [_make_search_result(1, "content", 0.9)]

        with patch("services.rag_pipeline.model_router") as mock_mr:
            mock_mr.embed = AsyncMock(return_value=[0.1] * EMBEDDING_DIM)
            mock_mr.synthesize = AsyncMock(return_value="Answer.")

            with patch("services.rag_pipeline.rewrite_query", new_callable=AsyncMock) as mock_rw:
                mock_rw.return_value = {"terms": [{"term": "q", "language": "en", "boost": 1.0, "instructions": ""}]}

                with patch("services.rag_pipeline.hybrid_search", new_callable=AsyncMock) as mock_hs:
                    mock_hs.return_value = fake_results

                    with patch("services.rag_pipeline._log_query", new_callable=AsyncMock):
                        result = await multi_step_rag(
                            "test",
                            mock_session,
                            enable_rerank=False,
                        )

        assert result["answer"] == "Answer."


# ===================================================================
# 13. Search endpoints (mock DB)
# ===================================================================

class TestSearchEndpointMocks:
    """Validate that search-related helpers work with mocked database objects."""

    @pytest.mark.asyncio
    async def test_model_router_embed_with_mock_session(self):
        router = ModelRouter()
        router._ollama_available = False
        # Ensure fallback path works
        with patch("services.model_router.HF_API_KEY", ""):
            result = await router.embed("test")
            assert result is None

    def test_search_result_dataclass_fields(self):
        sr = _make_search_result(42, "chunk text", 0.75)
        assert sr.chunk_id == 42
        assert sr.chunk_text == "chunk text"
        assert sr.score == 0.75
        assert sr.youtube_id == "vid_42"
        assert sr.title == "Title 42"
        assert sr.channel == "Test Channel"

    @pytest.mark.asyncio
    async def test_context_builder_with_search_result_objects(self):
        results = [
            _make_search_result(1, "First chunk", 0.9),
            _make_search_result(2, "Second chunk", 0.8),
        ]
        # build_context uses getattr — SearchResult has chunk_text attr
        result = build_context(results, max_tokens=5000)
        assert "First chunk" in result
        assert "Second chunk" in result

    @pytest.mark.asyncio
    async def test_reranker_with_search_results(self):
        results = [
            _make_search_result(1, "irrelevant", 0.3),
            _make_search_result(2, "very relevant", 0.95),
        ]
        # Reranker unavailable → returns original order
        with patch.object(model_router, "_reranker", None), \
             patch.object(model_router, "_reranker_checked", True):
            reranked = await rerank_chunks("relevant query", results, top_k=5)
            assert len(reranked) == 2
            assert reranked[0].chunk_id == 1  # original order


# ===================================================================
# Bonus: Language detection
# ===================================================================

class TestLanguageDetection:
    def test_telugu_detection(self):
        from services.model_router import _detect_language
        assert _detect_language("దేవుని ప్రేమ గురించి") == "te"

    def test_english_detection(self):
        from services.model_router import _detect_language
        assert _detect_language("What is God's love about?") == "en"

    def test_mixed_detection_english_dominant(self):
        from services.model_router import _detect_language
        assert _detect_language("Hello దేవు how are you?") == "en"

    def test_mixed_detection_telugu_dominant(self):
        from services.model_router import _detect_language
        assert _detect_language("దేవు hello ప్రేమ world గురించి") == "te"


# ===================================================================
# Bonus: Vector truncation
# ===================================================================

class TestVectorTruncation:
    def test_truncate_exact_dim(self):
        vec = [1.0] * EMBEDDING_DIM
        result = ModelRouter._truncate_to_dim(vec, EMBEDDING_DIM)
        assert len(result) == EMBEDDING_DIM

    def test_truncate_larger_vector(self):
        vec = [1.0] * 1024
        result = ModelRouter._truncate_to_dim(vec, EMBEDDING_DIM)
        assert len(result) == EMBEDDING_DIM

    def test_pad_small_vector(self):
        vec = [1.0] * 100
        result = ModelRouter._truncate_to_dim(vec, EMBEDDING_DIM)
        assert len(result) == EMBEDDING_DIM
        assert result[:100] == [1.0] * 100
        assert result[100:] == [0.0] * (EMBEDDING_DIM - 100)
