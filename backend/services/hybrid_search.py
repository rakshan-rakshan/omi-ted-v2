"""
Hybrid search — keyword (FTS) + semantic (vector) with RRF fusion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    te_chars = sum(1 for c in text if '\u0C00' <= c <= '\u0C7F')
    return "te" if te_chars > len(text) * 0.3 else "en"


@dataclass
class SearchResult:
    chunk_id: int
    chunk_text: str
    message_id: int
    score: float
    youtube_id: str
    title: str
    channel: str


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float] | None,
    *,
    filters: dict | None = None,
    top_k: int = 20,
) -> list[SearchResult]:
    rrf_k = settings.rag.rrf_k
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    lang = _detect_language(query_text)

    if query_embedding is None:
        return await _keyword_only(session, query_text, filters, top_k, lang)
    if dialect == "postgresql":
        return await _pg_hybrid(session, query_text, query_embedding, filters, top_k, rrf_k, lang)
    return await _sqlite_hybrid(session, query_text, query_embedding, filters, top_k, rrf_k, lang)


async def _keyword_only(
    session: AsyncSession,
    query_text: str,
    filters: dict | None,
    top_k: int,
    lang: str = "en",
) -> list[SearchResult]:
    """Fallback: keyword-only search when embeddings unavailable."""
    import sqlalchemy as sa

    # No language_code gate: corpus is single-language but users query cross-lingually
    # (EN + TE). Relevance is handled by the multilingual embedder + reranker.
    conditions = ["c.chunk_text LIKE :q"]
    params = {"q": f"%{query_text}%", "top_k": top_k}
    if filters:
        if filters.get("speaker"):
            conditions.append("v.channel LIKE :speaker")
            params["speaker"] = f"%{filters['speaker']}%"
        if filters.get("book"):
            conditions.append("c.scripture_refs LIKE :book")
            params["book"] = f"%{filters['book']}%"

    where = " AND ".join(conditions)
    sql = f"""
        SELECT c.id, c.chunk_text, c.message_id, m.title, v.youtube_id, v.channel
        FROM chunks c
        JOIN messages m ON m.id = c.message_id
        JOIN videos v ON v.id = m.video_id
        WHERE {where}
        LIMIT :top_k
    """
    result = await session.execute(sa.text(sql), params)
    rows = result.all()
    return [
        SearchResult(chunk_id=r.id, chunk_text=r.chunk_text, message_id=r.message_id,
                     score=1.0, youtube_id=r.youtube_id, title=r.title, channel=r.channel)
        for r in rows
    ]


async def _pg_hybrid(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    filters: dict | None,
    top_k: int,
    rrf_k: int,
    lang: str = "en",
) -> list[SearchResult]:
    from sqlalchemy import text

    emb_str = ",".join(str(v) for v in query_embedding)

    # No language_code gate — cross-lingual retrieval (see _keyword_only).
    conditions = ["TRUE"]
    if filters:
        if filters.get("speaker"):
            conditions.append("m.title ILIKE :speaker_pattern")
        if filters.get("book"):
            conditions.append("c.scripture_refs ILIKE :book_pattern")

    sql = f"""
    WITH semantic AS (
        SELECT c.id, c.chunk_text, c.message_id,
               1 - (c.embedding <=> ARRAY[{emb_str}]::vector) AS score,
               m.title, m.description, v.youtube_id, v.channel
        FROM chunks c
        JOIN messages m ON m.id = c.message_id
        JOIN videos v ON v.id = m.video_id
        WHERE {' AND '.join(conditions)}
        ORDER BY score DESC
        LIMIT :top_k
    ),
    keyword AS (
        SELECT c.id, c.chunk_text, c.message_id,
               ts_rank(to_tsvector('simple', c.chunk_text), plainto_tsquery('simple', :query)) AS score,
               m.title, m.description, v.youtube_id, v.channel
        FROM chunks c
        JOIN messages m ON m.id = c.message_id
        JOIN videos v ON v.id = m.video_id
        WHERE to_tsvector('simple', c.chunk_text) @@ plainto_tsquery('simple', :query)
          AND {' AND '.join(conditions)}
        ORDER BY score DESC
        LIMIT :top_k
    ),
    fused AS (
        SELECT id, chunk_text, message_id, youtube_id, title, channel,
               COALESCE(1.0 / (:rrf_k + ROW_NUMBER() OVER (ORDER BY semantic.score DESC)), 0) +
               COALESCE(1.0 / (:rrf_k2 + ROW_NUMBER() OVER (ORDER BY keyword.score DESC)), 0) AS rrf_score
        FROM (
            SELECT * FROM semantic
            UNION ALL
            SELECT * FROM keyword
        ) sub
    )
    SELECT id, chunk_text, message_id, youtube_id, title, channel, MAX(rrf_score) AS score
    FROM fused
    GROUP BY id, chunk_text, message_id, youtube_id, title, channel
    ORDER BY score DESC
    LIMIT :top_k
    """

    params = {
        "query": query_text,
        "top_k": top_k,
        "rrf_k": rrf_k,
        "rrf_k2": rrf_k,
    }
    if filters:
        if filters.get("speaker"):
            params["speaker_pattern"] = f"%{filters['speaker']}%"
        if filters.get("book"):
            params["book_pattern"] = f"%{filters['book']}%"

    result = await session.execute(text(sql), params)
    rows = result.all()
    return [
        SearchResult(
            chunk_id=r.id,
            chunk_text=r.chunk_text,
            message_id=r.message_id,
            score=float(r.score),
            youtube_id=r.youtube_id,
            title=r.title,
            channel=r.channel,
        )
        for r in rows
    ]


async def _sqlite_hybrid(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    filters: dict | None,
    top_k: int,
    rrf_k: int,
    lang: str = "en",
) -> list[SearchResult]:
    import json
    import math
    import numpy as np

    emb_arr = np.array(query_embedding)

    # No language_code gate — cross-lingual retrieval (see _keyword_only).
    conditions = ["1=1"]
    params: dict = {}
    if filters:
        if filters.get("speaker"):
            conditions.append("v.channel LIKE :speaker")
            params["speaker"] = f"%{filters['speaker']}%"
        if filters.get("book"):
            conditions.append("c.scripture_refs LIKE :book")
            params["book"] = f"%{filters['book']}%"

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT c.id, c.chunk_text, c.message_id, c.embedding,
               m.title, v.youtube_id, v.channel
        FROM chunks c
        JOIN messages m ON m.id = c.message_id
        JOIN videos v ON v.id = m.video_id
        WHERE {where_clause}
        ORDER BY c.id
    """
    result = await session.execute(sa.text(sql), params)
    rows = result.all()

    keyword_terms = set(query_text.lower().split())

    scored = []
    for r in rows:
        emb_json = r.embedding
        stored = json.loads(emb_json) if isinstance(emb_json, str) else emb_json
        if stored is None or len(stored) != len(emb_arr):
            continue
        dot = float(np.dot(emb_arr, np.array(stored)))
        semantic_score = max(0.0, dot)

        text_lower = (r.chunk_text or "").lower()
        keyword_matches = sum(1 for t in keyword_terms if t in text_lower)
        keyword_score = keyword_matches / max(len(keyword_terms), 1)

        scored.append((
            r.id, r.chunk_text, r.message_id,
            r.title or "", r.youtube_id or "", r.channel or "",
            semantic_score, keyword_score,
        ))

    sem_sorted = sorted(scored, key=lambda x: x[6], reverse=True)[:top_k]
    kw_sorted = sorted(scored, key=lambda x: x[7], reverse=True)[:top_k]

    rrf = {}
    for rank, item in enumerate(sem_sorted):
        rrf[item[0]] = rrf.get(item[0], 0) + 1.0 / (rrf_k + rank + 1)
    for rank, item in enumerate(kw_sorted):
        rrf[item[0]] = rrf.get(item[0], 0) + 1.0 / (rrf_k + rank + 1)

    item_map = {s[0]: s for s in scored}
    ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        SearchResult(
            chunk_id=item[0],
            chunk_text=item[1],
            message_id=item[2],
            score=round(rrf_score, 6),
            youtube_id=item_map[cid][5],
            title=item_map[cid][3],
            channel=item_map[cid][4],
        )
        for cid, rrf_score in ranked
        if cid in item_map
    ]
