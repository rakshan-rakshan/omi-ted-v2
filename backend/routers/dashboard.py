"""
Ingest dashboard — the live control surface over the full ~7,139-URL backlog.

Mounted under /api/v1/ingest (alongside routers/ingest.py):
  GET  /universe?status=&q=&page=&page_size=  — every CSV URL reconciled with DB status (paginated)
  GET  /summary                               — counts by status incl. not_attempted + run state
  POST /run     {mode:'new'|'retry'|'ids', ids?, limit?}  — start ONE paced background run
  GET  /run/status                            — live progress of the current run
  POST /run/stop                              — request the current run to stop

The run reuses routers.ingest._run_ingest (which honors YT_CONCURRENCY + YTDLP_COOKIES_FILE),
paced by INGEST_PACE between videos. Only one run at a time.
"""
from __future__ import annotations

import asyncio
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, get_session
from models import Job, Segment, Video

router = APIRouter(tags=["dashboard"])

_CSV_PATH = Path(__file__).parent.parent / "scripts" / "urls_to_ingest.csv"
_VIDEO_STATUSES = ["fetched", "fetching", "pending", "error", "no_transcript"]


# ---------------------------------------------------------------------------
# CSV universe (cached — the 7,139 URLs + titles live only in the CSV)
# ---------------------------------------------------------------------------

_csv_cache: dict[str, str] | None = None


def _load_csv_rows() -> dict[str, str]:
    """Return {youtube_id: title} for the full URL universe."""
    global _csv_cache
    if _csv_cache is None:
        rows: dict[str, str] = {}
        try:
            with open(_CSV_PATH, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    yid = (r.get("youtube_id") or "").strip()
                    if yid:
                        rows[yid] = (r.get("title") or "").strip()
        except FileNotFoundError:
            rows = {}
        _csv_cache = rows
    return _csv_cache


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UniverseRow(BaseModel):
    youtube_id: str
    title: str | None
    status: str            # not_attempted | pending | fetching | fetched | error | no_transcript
    segment_count: int
    translated_count: int = 0
    error_msg: str | None = None


class UniversePage(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[UniverseRow]


class SummaryResponse(BaseModel):
    total: int
    fetched: int
    percent: float
    counts: dict[str, int]
    translation: dict
    csv_total: int
    run: dict


class RunRequest(BaseModel):
    mode: str = "new"          # new | retry | ids
    ids: list[str] | None = None
    limit: int | None = None


# ---------------------------------------------------------------------------
# Background paced run state
# ---------------------------------------------------------------------------

_run_state: dict = {
    "running": False, "mode": None, "total": 0, "processed": 0,
    "succeeded": 0, "failed": 0, "skipped": 0, "current": None,
    "started_at": None, "stop": False,
}
_run_task: asyncio.Task | None = None


def _public_run_state() -> dict:
    return {k: v for k, v in _run_state.items() if k != "stop"}


async def _targets_for(mode: str, ids: list[str] | None) -> list[str]:
    async with AsyncSessionLocal() as session:
        if mode == "ids":
            return [i.strip() for i in (ids or []) if i.strip()]
        if mode == "retry":
            rows = (
                await session.execute(
                    select(Video.youtube_id).where(
                        Video.status.in_(["error", "no_transcript"]),
                        Video.excluded_scope.is_(None),
                    )
                )
            ).scalars().all()
            return list(rows)
        # mode == "new": CSV ids not yet in the DB at all
        have = set((await session.execute(select(Video.youtube_id))).scalars().all())
        return [yid for yid in _load_csv_rows().keys() if yid not in have]


async def _run_loop(mode: str, ids: list[str] | None, limit: int | None) -> None:
    from routers.ingest import _run_ingest  # lazy: avoid import cycle at startup

    pace = float(os.environ.get("INGEST_PACE", "2.5"))
    try:
        targets = await _targets_for(mode, ids)
        if limit:
            targets = targets[:limit]
        _run_state.update(total=len(targets), processed=0, succeeded=0, failed=0, skipped=0)

        for yid in targets:
            if _run_state["stop"]:
                break
            _run_state["current"] = yid

            # Ensure a Video + Job row (skip ones already fetched).
            async with AsyncSessionLocal() as session:
                video = (
                    await session.execute(select(Video).where(Video.youtube_id == yid))
                ).scalar_one_or_none()
                if video is not None and video.status == "fetched":
                    _run_state["skipped"] += 1
                    _run_state["processed"] += 1
                    continue
                if video is None:
                    video = Video(youtube_id=yid, status="pending")
                    session.add(video)
                    await session.flush()
                else:
                    video.status = "pending"
                job = Job(video_id=video.id, status="queued")
                session.add(job)
                await session.commit()
                vid_id, job_id = video.id, job.id

            await _run_ingest(vid_id, job_id)  # own session + YT_CONCURRENCY semaphore

            async with AsyncSessionLocal() as session:
                v = (
                    await session.execute(select(Video.status).where(Video.id == vid_id))
                ).scalar_one_or_none()
            if v == "fetched":
                _run_state["succeeded"] += 1
            else:
                _run_state["failed"] += 1
            _run_state["processed"] += 1
            await asyncio.sleep(pace)
    finally:
        _run_state["running"] = False
        _run_state["current"] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=SummaryResponse)
async def summary(session: AsyncSession = Depends(get_session)) -> SummaryResponse:
    csv_ids = set(_load_csv_rows().keys())
    rows = (await session.execute(
        select(Video.youtube_id, Video.status, Video.excluded_scope)
    )).all()
    db_status = {yid: st for (yid, st, _exc) in rows}
    excluded = {yid for (yid, _st, exc) in rows if exc}
    # Excluded videos drop out of the universe entirely (no status bucket).
    universe = (csv_ids | set(db_status.keys())) - excluded

    counts = {s: 0 for s in _VIDEO_STATUSES}
    counts["not_attempted"] = 0
    for yid in universe:
        st = db_status.get(yid, "not_attempted")
        counts[st] = counts.get(st, 0) + 1

    total = len(universe)
    fetched = counts["fetched"]

    # Translation progress across fetched videos (segment-level + video-level).
    seg_rows = (await session.execute(
        select(
            Segment.video_id,
            func.count(Segment.id),
            func.sum(case((and_(Segment.en_final.isnot(None), Segment.en_final != ""), 1), else_=0)),
        )
        .where(Segment.video_id.in_(
            select(Video.id).where(Video.status == "fetched", Video.excluded_scope.is_(None))
        ))
        .group_by(Segment.video_id)
    )).all()
    translated_videos = partial_videos = 0
    total_segments = translated_segments = 0
    for _vid, seg_total, seg_tr in seg_rows:
        seg_total = int(seg_total or 0)
        seg_tr = int(seg_tr or 0)
        total_segments += seg_total
        translated_segments += seg_tr
        if seg_total > 0 and seg_tr >= seg_total:
            translated_videos += 1
        elif seg_tr > 0:
            partial_videos += 1
    translation = {
        "translated_videos": translated_videos,
        "partial_videos": partial_videos,
        "untranslated_videos": max(0, fetched - translated_videos - partial_videos),
        "total_segments": total_segments,
        "translated_segments": translated_segments,
        "percent": round(100 * translated_segments / total_segments, 1) if total_segments else 0.0,
    }

    return SummaryResponse(
        total=total,
        fetched=fetched,
        percent=round(100 * fetched / total, 1) if total else 0.0,
        counts=counts,
        translation=translation,
        csv_total=len(csv_ids),
        run=_public_run_state(),
    )


@router.get("/universe", response_model=UniversePage)
async def universe(
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
) -> UniversePage:
    csv_rows = _load_csv_rows()  # {yid: title}

    videos = (await session.execute(select(Video))).scalars().all()
    db_by_id = {v.youtube_id: v for v in videos}
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
    err_rows = (
        await session.execute(
            select(Job.video_id, Job.error_msg)
            .where(Job.error_msg.isnot(None))
            .order_by(Job.id.desc())
        )
    ).all()
    err_map: dict[int, str] = {}
    for vid, msg in err_rows:
        err_map.setdefault(vid, msg)  # desc order → first seen is latest

    universe_ids = list(csv_rows.keys())
    for yid in db_by_id:  # include DB videos not in the CSV
        if yid not in csv_rows:
            universe_ids.append(yid)

    rows: list[UniverseRow] = []
    ql = q.lower().strip() if q else None
    for yid in universe_ids:
        v = db_by_id.get(yid)
        if v and v.excluded_scope:  # in the recycle bin — hide from active universe
            continue
        st = v.status if v else "not_attempted"
        if status and status != "all" and st != status:
            continue
        title = (v.title if v and v.title else csv_rows.get(yid)) or None
        if ql and ql not in yid.lower() and ql not in (title or "").lower():
            continue
        rows.append(UniverseRow(
            youtube_id=yid,
            title=title,
            status=st,
            segment_count=seg_counts.get(v.id, 0) if v else 0,
            translated_count=int(translated_counts.get(v.id, 0) or 0) if v else 0,
            error_msg=err_map.get(v.id) if (v and st == "error") else None,
        ))

    total = len(rows)
    page = max(1, page)
    start = (page - 1) * page_size
    items = rows[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 1
    return UniversePage(total=total, page=page, page_size=page_size,
                        total_pages=total_pages, items=items)


@router.post("/run")
async def start_run(body: RunRequest) -> dict:
    global _run_task
    if _run_state["running"]:
        raise HTTPException(409, detail="A run is already in progress.")
    if body.mode not in {"new", "retry", "ids"}:
        raise HTTPException(422, detail="mode must be new | retry | ids")
    _run_state.update(
        running=True, stop=False, mode=body.mode, total=0, processed=0,
        succeeded=0, failed=0, skipped=0, current=None,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _run_task = asyncio.create_task(_run_loop(body.mode, body.ids, body.limit))
    return _public_run_state()


@router.get("/run/status")
async def run_status() -> dict:
    return _public_run_state()


@router.post("/run/stop")
async def stop_run() -> dict:
    _run_state["stop"] = True
    return {"stopping": _run_state["running"]}
