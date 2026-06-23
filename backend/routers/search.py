"""
Search and Answer endpoints.
POST /api/v1/search       — hybrid search returning ranked chunks
POST /api/v1/ask          — search + answer generation with citations
POST /api/v1/ask/advanced — multi-step RAG with query rewriting + reranking
GET  /api/v1/models/health  — model provider health check (admin)
GET  /api/v1/models/reranker — reranker availability check
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import QueryLog
from services.embeddings import embed_query
from services.hybrid_search import hybrid_search, SearchResult
from services.answer_gen import generate_answer
from services.rag_pipeline import multi_step_rag
from services.model_router import model_router

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["search"])


class SearchFilters(BaseModel):
    speaker: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    book: str | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    filters: SearchFilters | None = None


class ChunkVideoInfo(BaseModel):
    youtube_id: str = ""
    title: str = ""
    channel: str = ""


class SearchResultItem(BaseModel):
    chunk_id: int
    chunk_text: str
    message_id: int
    score: float
    video: ChunkVideoInfo


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(
    body: SearchRequest,
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    query_emb = await embed_query(body.query)
    results = await hybrid_search(
        session, body.query, query_emb,
        filters=body.filters.model_dump() if body.filters else None,
        top_k=body.top_k,
    )
    return SearchResponse(
        results=[
            SearchResultItem(
                chunk_id=r.chunk_id,
                chunk_text=r.chunk_text[:500],
                message_id=r.message_id,
                score=r.score,
                video=ChunkVideoInfo(
                    youtube_id=r.youtube_id,
                    title=r.title,
                    channel=r.channel,
                ),
            )
            for r in results
        ],
        total=len(results),
    )


class AskRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None


class CitationSource(BaseModel):
    index: int
    chunk_id: int
    chunk_text: str
    video: ChunkVideoInfo


class AskResponse(BaseModel):
    answer: str
    sources: list[CitationSource]
    search_latency_ms: int = 0
    generation_latency_ms: int = 0


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(
    body: AskRequest,
    session: AsyncSession = Depends(get_session),
) -> AskResponse:
    t0 = time.monotonic()
    query_emb = await embed_query(body.query)
    raw_results = await hybrid_search(
        session, body.query, query_emb,
        filters=body.filters.model_dump() if body.filters else None,
        top_k=5,
    )
    search_latency = int((time.monotonic() - t0) * 1000)

    chunk_dicts = [
        {
            "chunk_id": r.chunk_id,
            "chunk_text": r.chunk_text,
            "title": r.title,
            "channel": r.channel,
            "youtube_id": r.youtube_id,
        }
        for r in raw_results
    ]

    answer, citations, gen_latency = await generate_answer(body.query, chunk_dicts)

    log = QueryLog(
        query=body.query,
        filters=json.dumps(body.filters.model_dump() if body.filters else {}),
        retrieved_chunk_ids=json.dumps([r.chunk_id for r in raw_results]),
        answer_text=answer,
        citations=json.dumps(citations),
        latency_ms=search_latency + gen_latency,
        model_used="claude-haiku",
    )
    session.add(log)
    await session.commit()

    source_lookup = {c["index"]: c for c in citations}
    sources = []
    for i, r in enumerate(raw_results[:5]):
        sources.append(CitationSource(
            index=i + 1,
            chunk_id=r.chunk_id,
            chunk_text=r.chunk_text[:500],
            video=ChunkVideoInfo(youtube_id=r.youtube_id, title=r.title, channel=r.channel),
        ))

    return AskResponse(
        answer=answer,
        sources=sources,
        search_latency_ms=search_latency,
        generation_latency_ms=gen_latency,
    )


# ── Advanced RAG ──────────────────────────────────────────────────────────────


class AdvancedAskResponse(BaseModel):
    answer: str
    context: str
    sources: list[CitationSource]
    rewritten_query: dict | None = None


@router.post("/ask/advanced", response_model=AdvancedAskResponse)
async def advanced_ask_endpoint(
    body: AskRequest,
    session: AsyncSession = Depends(get_session),
) -> AdvancedAskResponse:
    result = await multi_step_rag(
        query=body.query,
        session=session,
        filters=body.filters.model_dump() if body.filters else None,
    )

    source_lookup = {s.get("chunk_id", 0): s for s in result.get("sources", [])}
    sources = [
        CitationSource(
            index=i + 1,
            chunk_id=s.get("chunk_id", 0),
            chunk_text=s.get("chunk_text", "")[:500],
            video=ChunkVideoInfo(
                youtube_id=s.get("youtube_id", ""),
                title=s.get("title", ""),
                channel=s.get("channel", ""),
            ),
        )
        for i, s in enumerate(result.get("sources", []))
    ]

    return AdvancedAskResponse(
        answer=result["answer"],
        context=result.get("context", ""),
        sources=sources,
        rewritten_query=result.get("rewritten_query"),
    )


# ── Model health endpoints ────────────────────────────────────────────────────


@router.get("/models/health")
async def models_health(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
) -> dict:
    from config import settings

    if x_admin_key != getattr(settings, "admin_key", ""):
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return await model_router.health_check()


@router.get("/models/reranker")
async def models_reranker() -> dict:
    return {
        "available": model_router._reranker is not None,
        "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "loaded": model_router._reranker_checked,
    }
