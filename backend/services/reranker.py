"""
Reranker — cross-encoder reranking for search results.

Uses a sentence-transformers CrossEncoder to re-score (query, chunk) pairs
for relevance. The model runs locally on CPU (~80MB for ms-marco-MiniLM-L-6-v2).

Usage:
    from services.reranker import rerank_chunks
    reranked = await rerank_chunks("దేవుని ప్రేమ", search_results)
"""
from __future__ import annotations

import logging

from services.model_router import model_router
from services.hybrid_search import SearchResult

logger = logging.getLogger(__name__)


async def rerank_chunks(
    query: str,
    chunks: list[SearchResult],
    top_k: int = 10,
) -> list[SearchResult]:
    """
    Rerank search results by relevance to query using cross-encoder.

    Args:
        query: The original search query.
        chunks: List of SearchResult objects from hybrid search.
        top_k: Maximum number of results to return.

    Returns:
        Reranked list of SearchResult objects (up to top_k).
    """
    if not chunks:
        return []

    if not model_router.reranker_available():
        logger.debug("Reranker unavailable, returning original order")
        return chunks[:top_k]

    reranked = await model_router.rerank(query, chunks, text_attr="chunk_text")
    return reranked[:top_k]
