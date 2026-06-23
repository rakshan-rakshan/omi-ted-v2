"""
Document upload for non-YouTube content.
POST /api/v1/documents/upload — upload article/book/audio text
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Message, Chunk
from services.chunking import chunk_segments
from services.embeddings import embed_chunks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentUploadRequest(BaseModel):
    title: str
    author: str | None = None
    source_type: str = "article"
    source_url: str | None = None
    content: str
    language: str = "te"


class DocumentUploadResponse(BaseModel):
    message_id: int
    title: str
    source_type: str
    chunk_count: int
    language: str


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    body: DocumentUploadRequest,
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadResponse:
    message = Message(
        title=body.title,
        author=body.author,
        source_type=body.source_type,
        source_url=body.source_url,
        language=body.language,
        description=body.content[:500],
        message_type="sermon",
        video_id=None,
    )
    session.add(message)
    await session.flush()

    paragraphs = [p.strip() for p in body.content.split("\n\n") if p.strip()]

    if not paragraphs:
        import re
        paragraphs = [s.strip() + "." for s in re.split(r'[.!?]+', body.content) if s.strip()]

    if not paragraphs:
        paragraphs = [body.content[:1000]]

    segment_dicts = [
        {"id": i, "text": p, "segment_index": i}
        for i, p in enumerate(paragraphs)
    ]

    from config import settings
    chunks = await chunk_segments(
        message_id=message.id,
        segments=segment_dicts,
        target_words=settings.rag.chunk_target_words,
        min_words=settings.rag.chunk_min_words,
        max_words=settings.rag.chunk_max_words,
    )

    for c in chunks:
        c.language_code = body.language

    chunk_texts = [c.chunk_text for c in chunks]
    embeddings = await embed_chunks(chunk_texts)

    chunk_objects = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        obj = Chunk(
            message_id=message.id,
            chunk_index=chunk.chunk_index,
            chunk_text=chunk.chunk_text,
            language_code=body.language,
            token_count=chunk.token_count,
            embedding=emb,
        )
        session.add(obj)
        chunk_objects.append(obj)

    await session.commit()

    return DocumentUploadResponse(
        message_id=message.id,
        title=body.title,
        source_type=body.source_type,
        chunk_count=len(chunk_objects),
        language=body.language,
    )
