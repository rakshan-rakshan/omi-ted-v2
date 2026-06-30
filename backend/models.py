"""ORM models — schema is canonical in project-settings.md.

Tables: videos, segments, jobs, glossary.
en_final = en_human if set, else en_auto (computed at read time).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

import database
from database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    youtube_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    channel: Mapped[str | None] = mapped_column(String(200))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    # status: pending | fetching | fetched | no_transcript | error
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # Soft-remove ("recycle bin"): non-null scope = excluded from all active views + runs.
    excluded_scope: Mapped[str | None] = mapped_column(String(20), index=True)  # "ingest" | "translation"
    excluded_reason: Mapped[str | None] = mapped_column(Text)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime)

    segments: Mapped[list["Segment"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)

    te_original: Mapped[str] = mapped_column(Text, nullable=False)
    en_auto: Mapped[str | None] = mapped_column(Text)
    en_human: Mapped[str | None] = mapped_column(Text)
    # en_final is computed: en_human if set else en_auto. Stored as a column for export speed.
    en_final: Mapped[str | None] = mapped_column(Text)

    # content_type: sermon | song | prayer | unknown
    content_type: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False, index=True)
    is_reviewed: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    quality_score: Mapped[int | None] = mapped_column(Integer)  # 1-5
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    video: Mapped["Video"] = relationship(back_populates="segments")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True, nullable=False)
    # status: queued | running | done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    error_msg: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    video: Mapped["Video"] = relationship(back_populates="jobs")


class GlossaryTerm(Base):
    __tablename__ = "glossary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    te_term: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    en_term: Mapped[str] = mapped_column(String(200), nullable=False)
    # category: theology | name | place | general
    category: Mapped[str] = mapped_column(String(20), default="general", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # JSON-encoded list[str] of English meanings (one term -> many meanings).
    # en_term stays the PRIMARY meaning (= meanings[0]) so GlossaryApplier's
    # single-replacement and existing rows keep working unchanged.
    meanings: Mapped[str | None] = mapped_column(Text)


# ═══════════════════════════════════════════════════════════════════════════
# V3 — Ministry AI Knowledge Platform additions
# ═══════════════════════════════════════════════════════════════════════════

class TranslationCacheEntry(Base):
    """Hash-keyed translation cache — avoids re-translating identical text."""
    __tablename__ = "translation_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    te_text: Mapped[str] = mapped_column(Text, nullable=False)
    en_text: Mapped[str] = mapped_column(Text, nullable=False)
    src_lang: Mapped[str] = mapped_column(String(10), nullable=False)
    tgt_lang: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Message(Base):
    """Enriched sermon entity — one per ingested video."""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(20), default="sermon", nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="youtube", nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    series: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(5), default="te", nullable=False)
    scripture_refs: Mapped[str | None] = mapped_column(Text)  # JSON array for SQLite compat
    themes: Mapped[str | None] = mapped_column(Text)           # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class Chunk(Base):
    """RAG chunk with embedding — linked to a Message."""
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    # Earliest source-segment start (seconds) — powers jump-to-moment citations.
    start_time: Mapped[float | None] = mapped_column(Float)
    embedding = mapped_column("embedding", database.Vector(768), nullable=True)

    scripture_refs: Mapped[str | None] = mapped_column(Text)  # JSON array
    topic_tags: Mapped[str | None] = mapped_column(Text)       # JSON array

    message: Mapped["Message"] = relationship()


class Notebook(Base):
    """A user-curated collection of messages (videos) to scope Q&A to."""
    __tablename__ = "notebooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class NotebookMessage(Base):
    """Join table: which messages belong to a notebook."""
    __tablename__ = "notebook_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notebook_id: Mapped[int] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )


class QueryLog(Base):
    """Search / answer evaluation log."""
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[str | None] = mapped_column(Text)                  # JSON
    retrieved_chunk_ids: Mapped[str | None] = mapped_column(Text)       # JSON
    answer_text: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[str | None] = mapped_column(Text)                 # JSON
    feedback_score: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model_used: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TranslationCostLog(Base):
    """One row per video per translation run — records cost and token usage."""
    __tablename__ = "translation_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    segments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class TranslationErrorLog(Base):
    """One row per translation failure — captures model, error, and cost context."""
    __tablename__ = "translation_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), index=True, nullable=True)
    youtube_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    segment_index: Mapped[int | None] = mapped_column(Integer)  # null = video-level error
    error_type: Mapped[str] = mapped_column(String(50), nullable=False, default="exception")
    error_msg: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text)  # truncated te_original snippet
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # cost on this video's pass
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
