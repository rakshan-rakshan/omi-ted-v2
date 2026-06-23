"""
Query rewriter — decomposes a theological question into structured search terms.

The rewriter uses an LLM (via model_router) to break down a user query into
3-5 search terms with language tags and priority boosts. This enables parallel
search across multiple formulations of the same concept.

Usage:
    from services.query_rewriter import rewrite_query
    strategy = await rewrite_query("దేవుని ప్రేమ గురించి చెప్పండి")
    for term in strategy["terms"]:
        results = await hybrid_search(session, term["term"], emb, ...)
"""
from __future__ import annotations

import logging

from services.model_router import model_router

logger = logging.getLogger(__name__)


async def rewrite_query(query: str) -> dict:
    """
    Decompose a query into 3-5 structured search terms.

    Returns dict with:
        {
            "original_query": str,
            "terms": [
                {"term": str, "language": "te"|"en", "boost": float, "instructions": str},
                ...
            ]
        }

    Falls back to returning the original query as a single term if LLM unavailable.
    """
    strategy = await model_router.rewrite_query(query)

    if strategy is None:
        # Shouldn't happen (model_router returns fallback), but be safe
        strategy = {
            "terms": [{"term": query, "language": "en", "boost": 2.0, "instructions": "original query"}]
        }

    # Ensure original_query is set
    strategy["original_query"] = query

    # Validate terms
    valid_terms = []
    for t in strategy.get("terms", []):
        if isinstance(t, dict) and "term" in t:
            valid_terms.append({
                "term": str(t["term"]),
                "language": str(t.get("language", "en")),
                "boost": float(t.get("boost", 1.0)),
                "instructions": str(t.get("instructions", "")),
            })

    if not valid_terms:
        valid_terms = [{"term": query, "language": "en", "boost": 2.0, "instructions": "original query"}]

    strategy["terms"] = valid_terms
    logger.info(
        "Rewrote query into %d terms: %s",
        len(valid_terms),
        [t["term"] for t in valid_terms],
    )
    return strategy
