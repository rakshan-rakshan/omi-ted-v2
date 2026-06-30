"""
Error reporting endpoints.

GET /api/v1/errors/ingest      — videos that failed to fetch (Job.error_msg + Video.status)
GET /api/v1/errors/translation — logged translation failures (TranslationErrorLog) with model + cost
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Job, TranslationErrorLog, Video

logger = logging.getLogger(__name__)

router = APIRouter(tags=["errors"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class IngestErrorsResponse(BaseModel):
    items: list[dict]   # {youtube_id, title, status, error_msg, finished_at, attempts}
    total: int
    page: int
    page_size: int
    total_pages: int
    counts: dict        # {error, no_transcript}


class TranslationErrorsResponse(BaseModel):
    items: list[dict]   # {id, youtube_id, title, run_id, provider, model,
                        #  segment_index, source_text, error_type, error_msg,
                        #  cost_usd, created_at}
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: dict       # {total_errors, cost_on_errored_videos, by_model, by_error_type}


# ---------------------------------------------------------------------------
# Endpoint 1: GET /errors/ingest
# ---------------------------------------------------------------------------


@router.get("/errors/ingest", response_model=IngestErrorsResponse)
async def ingest_errors(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status: str | None = Query(None, description='"error" | "no_transcript" | "all"/None = both'),
    q: str | None = Query(None, description="Search youtube_id or title (case-insensitive)"),
    session: AsyncSession = Depends(get_session),
) -> IngestErrorsResponse:
    """Videos that failed to fetch — latest job error_msg + attempt count."""

    # Pull every failed video once, reconcile with jobs in Python (SQLite-friendly).
    try:
        video_rows = (
            await session.execute(
                select(Video.id, Video.youtube_id, Video.title, Video.status).where(
                    Video.status.in_(("error", "no_transcript"))
                )
            )
        ).all()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ingest_errors: DB error reading videos: %s", exc)
        return IngestErrorsResponse(
            items=[], total=0, page=page, page_size=page_size,
            total_pages=1, counts={"error": 0, "no_transcript": 0},
        )

    # counts: always over ALL matching videos, ignoring the status filter.
    counts = {"error": 0, "no_transcript": 0}
    for _vid, _yid, _title, st in video_rows:
        if st in counts:
            counts[st] += 1

    # Latest job per video (id desc → first seen is latest) + per-video attempt count.
    latest_job: dict[int, tuple[str | None, object]] = {}  # video_id -> (error_msg, finished_at)
    attempts: dict[int, int] = {}
    try:
        job_rows = (
            await session.execute(
                select(Job.video_id, Job.error_msg, Job.finished_at).order_by(Job.id.desc())
            )
        ).all()
        for vid, msg, finished_at in job_rows:
            latest_job.setdefault(vid, (msg, finished_at))  # desc order → first seen is latest
            attempts[vid] = attempts.get(vid, 0) + 1
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ingest_errors: DB error reading jobs: %s", exc)

    ql = q.lower().strip() if q else None
    rows: list[dict] = []
    for vid, yid, title, st in video_rows:
        if status and status != "all" and st != status:
            continue
        if ql and ql not in (yid or "").lower() and ql not in (title or "").lower():
            continue
        msg, finished_at = latest_job.get(vid, (None, None))
        rows.append(
            {
                "_video_id": vid,
                "_finished_at": finished_at,
                "youtube_id": yid,
                "title": title,
                "status": st,
                "error_msg": msg,
                "finished_at": finished_at.isoformat() if finished_at else None,
                "attempts": attempts.get(vid, 0),
            }
        )

    # Order by latest job finished_at desc (nulls last), then video id desc as tiebreak.
    rows.sort(key=lambda r: (r["_finished_at"] is not None, r["_finished_at"], r["_video_id"]), reverse=True)

    total = len(rows)
    page = max(1, page)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 1

    items = [
        {
            "youtube_id": r["youtube_id"],
            "title": r["title"],
            "status": r["status"],
            "error_msg": r["error_msg"],
            "finished_at": r["finished_at"],
            "attempts": r["attempts"],
        }
        for r in page_rows
    ]

    return IngestErrorsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        counts=counts,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: GET /errors/translation
# ---------------------------------------------------------------------------


def _empty_translation_response(page: int, page_size: int) -> TranslationErrorsResponse:
    return TranslationErrorsResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
        total_pages=1,
        summary={
            "total_errors": 0,
            "cost_on_errored_videos": 0.0,
            "by_model": [],
            "by_error_type": [],
        },
    )


@router.get("/errors/translation", response_model=TranslationErrorsResponse)
async def translation_errors(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    error_type: str | None = Query(None, description="Exact error_type match"),
    q: str | None = Query(None, description="Search youtube_id or video title (case-insensitive)"),
    session: AsyncSession = Depends(get_session),
) -> TranslationErrorsResponse:
    """Logged translation failures with model + cost context.

    All TranslationErrorLog access is guarded so this returns an empty-but-valid
    response if migration 008 has not run yet.
    """

    page = max(1, page)
    ql = q.lower().strip() if q else None

    try:
        # Base query: TranslationErrorLog LEFT JOIN Video (for title). created_at desc.
        result = await session.execute(
            select(
                TranslationErrorLog.id,
                TranslationErrorLog.video_id,
                TranslationErrorLog.youtube_id,
                Video.title.label("title"),
                TranslationErrorLog.run_id,
                TranslationErrorLog.provider,
                TranslationErrorLog.model,
                TranslationErrorLog.segment_index,
                TranslationErrorLog.source_text,
                TranslationErrorLog.error_type,
                TranslationErrorLog.error_msg,
                TranslationErrorLog.cost_usd,
                TranslationErrorLog.created_at,
            )
            .outerjoin(Video, TranslationErrorLog.video_id == Video.id)
            .order_by(TranslationErrorLog.created_at.desc(), TranslationErrorLog.id.desc())
        )
        all_rows = list(result.mappings())
    except (OperationalError, ProgrammingError) as exc:
        # migration 008 not run yet — return empty-but-valid response
        logger.warning("translation_errors: DB error (table missing?): %s", exc)
        return _empty_translation_response(page, page_size)

    # Apply error_type + q filters in Python (handles the joined title cleanly).
    filtered: list[dict] = []
    for row in all_rows:
        if error_type and row["error_type"] != error_type:
            continue
        if ql:
            yid = (row["youtube_id"] or "").lower()
            title = (row["title"] or "").lower()
            if ql not in yid and ql not in title:
                continue
        filtered.append(dict(row))

    # --- summary over ALL filtered rows (pre-pagination) ---
    total_errors = len(filtered)

    # Distinct (video_id, run_id) → cost, to avoid double-counting a pass's full cost
    # that every error row of that pass carries.
    distinct_pass_cost: dict[tuple, float] = {}
    model_counts: dict[tuple[str, str | None], int] = {}
    model_pass_cost: dict[tuple[str, str | None], dict[tuple, float]] = {}
    error_type_counts: dict[str, int] = {}

    for row in filtered:
        pass_key = (row["video_id"], row["run_id"])
        cost = float(row["cost_usd"] or 0.0)
        # last write wins; all rows of one pass carry the same pass cost
        distinct_pass_cost[pass_key] = cost

        mkey = (row["provider"], row["model"])
        model_counts[mkey] = model_counts.get(mkey, 0) + 1
        model_pass_cost.setdefault(mkey, {})[pass_key] = cost

        et = row["error_type"]
        error_type_counts[et] = error_type_counts.get(et, 0) + 1

    cost_on_errored_videos = sum(distinct_pass_cost.values())

    by_model = [
        {
            "provider": provider,
            "model": model,
            "count": model_counts[(provider, model)],
            "cost_usd": sum(model_pass_cost[(provider, model)].values()),
        }
        for (provider, model) in model_counts
    ]
    by_model.sort(key=lambda m: m["count"], reverse=True)

    by_error_type = [
        {"error_type": et, "count": cnt} for et, cnt in error_type_counts.items()
    ]
    by_error_type.sort(key=lambda e: e["count"], reverse=True)

    # --- pagination over filtered rows ---
    total = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 1

    items = [
        {
            "id": r["id"],
            "youtube_id": r["youtube_id"],
            "title": r["title"],
            "run_id": r["run_id"],
            "provider": r["provider"],
            "model": r["model"],
            "segment_index": r["segment_index"],
            "source_text": r["source_text"],
            "error_type": r["error_type"],
            "error_msg": r["error_msg"],
            "cost_usd": float(r["cost_usd"] or 0.0),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in page_rows
    ]

    return TranslationErrorsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        summary={
            "total_errors": total_errors,
            "cost_on_errored_videos": cost_on_errored_videos,
            "by_model": by_model,
            "by_error_type": by_error_type,
        },
    )
