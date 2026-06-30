"""
Multi-step RAG pipeline with query decomposition, parallel search, and reranking.

Falls back to single-step RAG when advanced features fail or are disabled.

Usage:
    from services.rag_pipeline import multi_step_rag, single_step_rag
    result = await multi_step_rag(query, session, config)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from services.context_builder import build_context
from services.embeddings import embed_query
from services.hybrid_search import hybrid_search, SearchResult
from services.model_router import model_router
from services.query_rewriter import rewrite_query
from services.reranker import rerank_chunks

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    te_chars = sum(1 for c in text if "\u0C00" <= c <= "\u0C7F")
    return "te" if te_chars > len(text) * 0.3 else "en"


def _merge_results(all_results: list[list[SearchResult]]) -> list[SearchResult]:
    seen: dict[int, SearchResult] = {}
    for results in all_results:
        for r in results:
            if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                seen[r.chunk_id] = r
    return sorted(seen.values(), key=lambda x: x.score, reverse=True)


def _build_citations(chunks: list[SearchResult]) -> list[dict]:
    return [
        {
            "index": i + 1,
            "chunk_id": c.chunk_id,
            "chunk_text": c.chunk_text,
            "title": c.title,
            "youtube_id": c.youtube_id,
            "channel": c.channel,
            "start_time": c.start_time,
            "score": c.score,
        }
        for i, c in enumerate(chunks)
    ]


def _build_context_string(chunks: list[SearchResult], max_tokens: int) -> str:
    return build_context(chunks, max_tokens=max_tokens)


def _build_fallback_context(chunks: list[SearchResult]) -> str:
    parts = []
    for i, c in enumerate(chunks[:settings.rag.top_k_ask], 1):
        parts.append(f"[{i}] {c.chunk_text}")
    return "\n\n".join(parts)


async def _log_query(
    session: AsyncSession,
    query: str,
    answer: str,
    latency_ms: int,
    source_count: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        log_entry = {
            "query": query,
            "answer_length": len(answer),
            "latency_ms": latency_ms,
            "source_count": source_count,
        }
        if metadata:
            log_entry.update(metadata)

        await session.execute(
            sa.text(
                "INSERT INTO query_logs (query, answer_length, latency_ms, source_count, metadata) "
                "VALUES (:query, :answer_length, :latency_ms, :source_count, :metadata)"
            ),
            {"query": query, "answer_length": len(answer), "latency_ms": latency_ms,
             "source_count": source_count, "metadata": str(log_entry)},
        )
        await session.commit()
    except Exception as e:
        logger.debug("Failed to log query: %s", e)


async def _search_term(
    term: str,
    embedding: list[float] | None,
    filters: dict | None,
    top_k: int,
) -> list[SearchResult]:
    """Run one hybrid search in its own short-lived session.

    Each parallel search must use a distinct AsyncSession — SQLAlchemy forbids
    concurrent operations on a single session, which previously made every
    /ask/advanced call hang ~180s.
    """
    async with AsyncSessionLocal() as s:
        return await hybrid_search(s, term, embedding, filters=filters, top_k=top_k)


async def multi_step_rag(
    query: str,
    session: AsyncSession,
    *,
    language: str | None = None,
    max_tokens: int = 3000,
    enable_rewrite: bool = True,
    enable_rerank: bool = True,
    enable_context_budget: bool = True,
    filters: dict | None = None,
) -> dict[str, Any]:
    """
    Multi-step RAG pipeline:
    1. Rewrite query into decomposed search terms
    2. Parallel hybrid search across all terms
    3. Merge + deduplicate results
    4. Rerank with cross-encoder
    5. Build prioritized context within token budget
    6. Synthesize answer
    """
    t0 = time.monotonic()
    lang = language or _detect_language(query)
    rewritten_query = None
    rewritten_terms = [query]

    # Step 1: Query rewriting
    if enable_rewrite:
        try:
            rewritten_query = await rewrite_query(query)
            terms = rewritten_query.get("terms", [])
            if terms:
                rewritten_terms = [t["term"] for t in terms]
                logger.info("Rewrote query into %d terms", len(rewritten_terms))
        except Exception as e:
            logger.warning("Query rewrite failed, using original: %s", e)
            rewritten_query = None

    # Step 2: Embed all search terms + parallel hybrid search
    # Use embed_query (sentence-transformers e5-base) so query vectors live in the
    # same space as the corpus (embed_all_chunks.py uses the same model).
    embedding = await embed_query(query)
    # Each parallel search gets its own session — see _search_term.
    search_tasks = [
        _search_term(term, embedding, filters, settings.rag.top_k_search)
        for term in rewritten_terms
    ]
    try:
        all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    except Exception as e:
        logger.warning("Parallel search failed: %s", e)
        all_results = [Exception("search failed")]

    # Filter out exceptions, keep successful results
    valid_results: list[list[SearchResult]] = []
    for r in all_results:
        if isinstance(r, Exception):
            logger.warning("Search task raised: %s", r)
        elif isinstance(r, list):
            valid_results.append(r)

    if not valid_results:
        latency = int((time.monotonic() - t0) * 1000)
        await _log_query(session, query, "", latency, 0, {"error": "no_results"})
        return {
            "answer": "I don't have enough context to answer that question.",
            "context": "",
            "sources": [],
            "rewritten_query": rewritten_query,
        }

    # Step 3: Merge + deduplicate
    merged = _merge_results(valid_results)

    # Step 4: Rerank
    if enable_rerank and len(merged) > 1:
        try:
            merged = await rerank_chunks(query, merged, top_k=settings.rag.top_k_ask * 2)
        except Exception as e:
            logger.warning("Reranking failed, using original order: %s", e)

    # Step 5: Context budget
    if enable_context_budget:
        context_str = _build_context_string(merged, max_tokens)
    else:
        context_str = _build_fallback_context(merged)

    # Step 6: Synthesize
    answer = await model_router.synthesize(query, context_str, lang=lang)

    # Step 7: Build citations and log
    citations = _build_citations(merged[:settings.rag.top_k_ask])
    latency = int((time.monotonic() - t0) * 1000)

    await _log_query(session, query, answer, latency, len(citations), {
        "rewritten_terms": rewritten_terms,
        "reranked": enable_rerank,
    })

    return {
        "answer": answer,
        "context": context_str,
        "sources": citations,
        "rewritten_query": rewritten_query,
    }


async def single_step_rag(
    query: str,
    session: AsyncSession,
    *,
    language: str | None = None,
    max_tokens: int = 3000,
    filters: dict | None = None,
) -> dict[str, Any]:
    """
    Simple single-step RAG: embed → search → synthesize.
    Used as fallback when multi-step fails or for low-latency paths.
    """
    t0 = time.monotonic()
    lang = language or _detect_language(query)

    embedding = await embed_query(query)
    results = await hybrid_search(session, query, embedding, filters=filters, top_k=settings.rag.top_k_ask)

    context_str = _build_fallback_context(results)
    answer = await model_router.synthesize(query, context_str, lang=lang)

    citations = _build_citations(results)
    latency = int((time.monotonic() - t0) * 1000)

    await _log_query(session, query, answer, latency, len(citations), {"mode": "single_step"})

    return {
        "answer": answer,
        "context": context_str,
        "sources": citations,
        "rewritten_query": None,
    }
