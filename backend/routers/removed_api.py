"""
Soft-remove ("recycle bin") endpoints.

POST /api/v1/videos/{youtube_id}/remove   {scope: "ingest"|"translation", reason?: str}
POST /api/v1/videos/{youtube_id}/restore
GET  /api/v1/removed?page=&page_size=&q=&scope=

A video with a non-null excluded_scope is "in the bin": hidden from every active
view (ingest universe/counts, translate corpus, translation stats) and skipped by
both ingest and translation runs. excluded_scope only records WHERE the user
removed it from, for display. Restore clears the fields.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Segment, Video

router = APIRouter(tags=["removed"])

_VALID_SCOPES = {"ingest", "translation"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RemoveRequest(BaseModel):
    scope: str
    reason: str | None = None


class RemovedResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int
    counts: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/videos/{youtube_id}/remove")
async def remove_video(
    youtube_id: str,
    body: RemoveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Soft-remove a video into the recycle bin under the given scope."""
    if body.scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422, detail="scope must be ingest | translation")

    video = (
        await session.execute(select(Video).where(Video.youtube_id == youtube_id))
    ).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail=f"Video {youtube_id} not found.")

    video.excluded_scope = body.scope
    video.excluded_reason = body.reason or None
    video.excluded_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "youtube_id": youtube_id,
        "excluded_scope": video.excluded_scope,
        "excluded_reason": video.excluded_reason,
        "excluded_at": video.excluded_at.isoformat() if video.excluded_at else None,
    }


@router.post("/videos/{youtube_id}/restore")
async def restore_video(
    youtube_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Restore a video from the recycle bin — clears the exclusion fields."""
    video = (
        await session.execute(select(Video).where(Video.youtube_id == youtube_id))
    ).scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail=f"Video {youtube_id} not found.")

    video.excluded_scope = None
    video.excluded_reason = None
    video.excluded_at = None
    await session.commit()

    return {"youtube_id": youtube_id, "restored": True}


@router.get("/removed", response_model=RemovedResponse)
async def list_removed(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    q: str | None = None,
    scope: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RemovedResponse:
    """List soft-removed videos (recycle bin), newest first, with per-scope counts."""
    videos = (
        await session.execute(
            select(Video).where(Video.excluded_scope.isnot(None))
        )
    ).scalars().all()

    # Per-scope counts over ALL excluded videos (ignoring the scope filter).
    counts = {
        "ingest": sum(1 for v in videos if v.excluded_scope == "ingest"),
        "translation": sum(1 for v in videos if v.excluded_scope == "translation"),
    }

    # Segment + translated counts per video (group-by, same pattern as dashboard.py).
    seg_counts = dict(
        (await session.execute(
            select(Segment.video_id, func.count(Segment.id)).group_by(Segment.video_id)
        )).all()
    )
    translated_counts = dict(
        (await session.execute(
            select(
                Segment.video_id,
                func.sum(case((and_(Segment.en_final.isnot(None), Segment.en_final != ""), 1), else_=0)),
            ).group_by(Segment.video_id)
        )).all()
    )

    # Filter (scope + case-insensitive q over youtube_id/title) in Python.
    ql = q.lower().strip() if q else None
    filtered = []
    for v in videos:
        if scope and v.excluded_scope != scope:
            continue
        if ql and ql not in v.youtube_id.lower() and ql not in (v.title or "").lower():
            continue
        filtered.append(v)

    # Newest removals first; None excluded_at sorts last.
    filtered.sort(
        key=lambda v: v.excluded_at or datetime.min,
        reverse=True,
    )

    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 1

    items = [
        {
            "youtube_id": v.youtube_id,
            "title": v.title,
            "scope": v.excluded_scope,
            "reason": v.excluded_reason,
            "excluded_at": v.excluded_at.isoformat() if v.excluded_at else None,
            "status": v.status,
            "segment_count": int(seg_counts.get(v.id, 0) or 0),
            "translated_count": int(translated_counts.get(v.id, 0) or 0),
        }
        for v in page_items
    ]

    return RemovedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        counts=counts,
    )
