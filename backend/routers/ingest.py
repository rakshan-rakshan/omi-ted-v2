"""
POST /api/v1/ingest  — start transcript ingestion for a YouTube video
GET  /api/v1/ingest/jobs/{job_id} — poll job status

Flow:
  1. POST creates Video + Job rows immediately, returns job_id.
  2. FastAPI BackgroundTask calls _run_ingest, which fetches + writes Segments.
  3. GET /jobs/{id} lets the caller poll until status == done | failed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, get_session
from models import Job, Segment, Video
from services.transcript import fetch_video

router = APIRouter(tags=["ingest"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    youtube_id: str


class IngestResponse(BaseModel):
    job_id: int
    video_id: int
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: int
    video_id: int
    status: str
    error_msg: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class BatchImportRequest(BaseModel):
    youtube_ids: list[str]


class BatchImportResponse(BaseModel):
    total: int
    queued: int
    already_fetched: int
    jobs: list[IngestResponse]


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_ingest(video_id: int, job_id: int) -> None:
    """
    Run the full ingest pipeline in a background task.
    Opens its own DB session — FastAPI's request session is closed by the time this runs.
    """
    async with AsyncSessionLocal() as session:
        # Mark job as running
        job_result = await session.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one_or_none()
        video_result = await session.execute(select(Video).where(Video.id == video_id))
        video = video_result.scalar_one_or_none()

        if not job or not video:
            return  # safety guard — should never happen

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        video.status = "fetching"
        await session.commit()

        try:
            data = await fetch_video(video.youtube_id)

            # Update video metadata
            video.title      = data.title
            video.channel    = data.channel
            video.duration_s = data.duration_s

            if not data.has_te:
                video.status  = "no_transcript"
                job.status    = "done"
                job.error_msg = "No Telugu captions found on this video."
                job.finished_at = datetime.now(timezone.utc)
                await session.commit()
                return

            # Delete any segments from a previous ingest attempt
            from sqlalchemy import delete as sa_delete
            await session.execute(sa_delete(Segment).where(Segment.video_id == video_id))

            # Write segments
            seg_objects = []
            for idx, seg in enumerate(data.segments):
                obj = Segment(
                    video_id=video_id,
                    segment_index=idx,
                    start_time=seg.start_time,
                    duration=seg.duration,
                    te_original=seg.te_original,
                    en_auto=seg.en_auto,
                    en_human=None,
                    en_final=seg.en_auto,   # en_final = en_human if set, else en_auto
                    content_type="unknown",
                    is_reviewed=False,
                )
                session.add(obj)
                seg_objects.append(obj)

            # Classify content types (song/prayer/sermon)
            from services.song_detector import classify_segments
            seg_data = [{"index": s.segment_index, "text": s.te_original} for s in seg_objects]
            content_types = classify_segments(seg_data)
            for s, ct in zip(seg_objects, content_types):
                s.content_type = ct

            video.status    = "fetched"
            video.fetched_at = datetime.now(timezone.utc)
            job.status      = "done"
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()

        except Exception as exc:
            video.status    = "error"
            job.status      = "failed"
            job.error_msg   = str(exc)[:1000]
            job.finished_at = datetime.now(timezone.utc)
            await session.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=IngestResponse, status_code=202)
async def start_ingest(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """
    Queue transcript ingestion for a YouTube video.

    - If the video was already successfully fetched, returns immediately with
      status='already_fetched' (no duplicate work).
    - Otherwise creates a Job and kicks off a background task. Poll
      GET /api/v1/ingest/jobs/{job_id} to track progress.
    """
    youtube_id = body.youtube_id.strip()

    # Idempotency check
    existing_result = await session.execute(
        select(Video).where(Video.youtube_id == youtube_id)
    )
    existing = existing_result.scalar_one_or_none()

    if existing and existing.status == "fetched":
        last_job_result = await session.execute(
            select(Job)
            .where(Job.video_id == existing.id)
            .order_by(Job.id.desc())
        )
        last_job = last_job_result.scalar_one_or_none()
        return IngestResponse(
            job_id=last_job.id if last_job else -1,
            video_id=existing.id,
            status="already_fetched",
            message=f"'{existing.title or youtube_id}' is already ingested.",
        )

    # Create Video row (or reuse existing error/pending one)
    if existing is None:
        video = Video(youtube_id=youtube_id, status="pending")
        session.add(video)
        await session.flush()   # get video.id before committing
    else:
        video = existing
        video.status = "pending"

    job = Job(video_id=video.id, status="queued")
    session.add(job)
    await session.commit()
    await session.refresh(job)

    background_tasks.add_task(_run_ingest, video.id, job.id)

    return IngestResponse(
        job_id=job.id,
        video_id=video.id,
        status="queued",
        message=f"Ingestion queued for {youtube_id}. Poll /api/v1/ingest/jobs/{job.id}.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> JobStatusResponse:
    """Return the current status of an ingest job."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return JobStatusResponse(
        job_id=job.id,
        video_id=job.video_id,
        status=job.status,
        error_msg=job.error_msg,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.post("/batch", response_model=BatchImportResponse)
async def batch_import(
    body: BatchImportRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> BatchImportResponse:
    """
    Import multiple videos at once. Accepts a list of YouTube IDs.
    Returns a summary with job IDs for each queued video.
    """
    ids = list(dict.fromkeys([i.strip() for i in body.youtube_ids if i.strip()]))
    queued = 0
    already = 0
    jobs = []

    for yt_id in ids:
        result = await session.execute(
            select(Video).where(Video.youtube_id == yt_id)
        )
        existing = result.scalar_one_or_none()

        if existing and existing.status == "fetched":
            already += 1
            continue

        if existing is None:
            video = Video(youtube_id=yt_id, status="pending")
            session.add(video)
            await session.flush()
        else:
            video = existing
            video.status = "pending"

        job = Job(video_id=video.id, status="queued")
        session.add(job)
        await session.commit()
        await session.refresh(job)

        background_tasks.add_task(_run_ingest, video.id, job.id)
        queued += 1
        jobs.append(IngestResponse(
            job_id=job.id, video_id=video.id,
            status="queued", message=f"Ingestion queued for {yt_id}.",
        ))

    return BatchImportResponse(
        total=len(ids), queued=queued,
        already_fetched=already, jobs=jobs,
    )
