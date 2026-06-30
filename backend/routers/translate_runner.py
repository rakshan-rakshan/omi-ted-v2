"""
Bulk translation runner — one paced background pass that translates many
fetched videos to English. The UI counterpart to the ingest dashboard run.

Mirrors routers/dashboard.py exactly in shape: a single module-level run state,
one run at a time, live progress, a co-operative stop flag.

Mounted under /api/v1 (alongside routers/batch.py):
  POST /batch/translate/run         {mode:'pending'|'all'|'ids', ids?, limit?, provider?, model?, concurrency?}
  GET  /batch/translate/run/status  — live progress of the current run
  POST /batch/translate/run/stop    — request the current run to stop

Each video is translated by routers.batch.translate_video_segments (its own
session per video), paced by TRANSLATE_PACE seconds between videos. Provider and
model default to config.yaml's llm block.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select

from database import AsyncSessionLocal
from models import Segment, Video
from services.translate import _cfg

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TranslateRunRequest(BaseModel):
    mode: str = "pending"        # pending | all | ids
    ids: list[str] | None = None
    limit: int | None = None
    provider: str | None = None  # default: config.yaml llm.provider
    model: str | None = None     # default: config.yaml llm.model
    concurrency: int | None = None        # segments/video in parallel (default: llm.concurrency)
    batch_size: int | None = None         # segments per API call (default: llm.batch_size; 1=off)
    video_concurrency: int | None = None  # videos in parallel (default: translate_run.video_concurrency)
    pace: float | None = None             # seconds between videos (default: translate_run.pace_s)


# ---------------------------------------------------------------------------
# Background paced run state (one run at a time)
# ---------------------------------------------------------------------------

_tr_run_state: dict = {
    "running": False, "mode": None, "total": 0, "processed": 0,
    "translated": 0, "errors": 0, "skipped": 0, "current": None,
    "provider": None, "model": None, "started_at": None, "stop": False,
    "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0,
}
_tr_run_task: asyncio.Task | None = None


def _public_tr_state() -> dict:
    return {k: v for k, v in _tr_run_state.items() if k != "stop"}


async def _tr_targets_for(mode: str, ids: list[str] | None) -> list[str]:
    """Return the youtube_ids to translate for this run mode (fetched videos only)."""
    async with AsyncSessionLocal() as session:
        if mode == "ids":
            wanted = [i.strip() for i in (ids or []) if i.strip()]
            if not wanted:
                return []
            rows = (await session.execute(
                select(Video.youtube_id).where(
                    Video.youtube_id.in_(wanted),
                    Video.status == "fetched",
                    Video.excluded_scope.is_(None),
                )
            )).scalars().all()
            return list(rows)

        fetched = (await session.execute(
            select(Video.id, Video.youtube_id).where(
                Video.status == "fetched", Video.excluded_scope.is_(None)
            )
        )).all()
        if mode == "all":
            return [yid for _vid, yid in fetched]

        # mode == "pending": fetched videos with >= 1 untranslated segment
        untranslated_vid_ids = set((await session.execute(
            select(Segment.video_id)
            .where(or_(Segment.en_final.is_(None), Segment.en_final == ""))
            .distinct()
        )).scalars().all())
        return [yid for vid, yid in fetched if vid in untranslated_vid_ids]


async def _tr_run_loop(
    mode: str,
    ids: list[str] | None,
    limit: int | None,
    provider: str,
    model: str,
    concurrency: int,
    batch_size: int,
    video_concurrency: int,
    pace: float,
) -> None:
    from routers.batch import translate_video_segments  # lazy: avoid import cycle
    from services.glossary_applier import GlossaryApplier

    force = mode == "all"
    try:
        targets = await _tr_targets_for(mode, ids)
        if limit:
            targets = targets[:limit]
        _tr_run_state.update(total=len(targets), processed=0, translated=0, errors=0, skipped=0)

        # Build the glossary ONCE for the whole run (one table scan, reused per video).
        async with AsyncSessionLocal() as gsession:
            shared_glossary = await GlossaryApplier.from_db(gsession)

        vsem = asyncio.Semaphore(max(1, video_concurrency))

        async def _do_video(yid: str) -> None:
            if _tr_run_state["stop"]:
                return
            async with vsem:
                if _tr_run_state["stop"]:
                    return
                _tr_run_state["current"] = yid
                try:
                    async with AsyncSessionLocal() as session:
                        video = (await session.execute(
                            select(Video).where(Video.youtube_id == yid)
                        )).scalar_one_or_none()
                        if video is None or video.status != "fetched":
                            _tr_run_state["skipped"] += 1
                            _tr_run_state["processed"] += 1
                            return
                        counts = await translate_video_segments(
                            video,
                            session=session,
                            provider=provider,
                            model=model,
                            force=force,
                            concurrency=concurrency,
                            batch_size=batch_size,
                            glossary=shared_glossary,
                            run_id=_tr_run_state.get("started_at"),
                        )
                    _tr_run_state["translated"] += counts.get("translated", 0)
                    _tr_run_state["errors"] += counts.get("errors", 0)
                    _tr_run_state["cost_usd"] = round(
                        _tr_run_state["cost_usd"] + counts.get("cost_usd", 0.0), 8
                    )
                    _tr_run_state["prompt_tokens"] += counts.get("prompt_tokens", 0)
                    _tr_run_state["completion_tokens"] += counts.get("completion_tokens", 0)
                except Exception as exc:
                    logger.warning("translate run failed for %s: %s", yid, exc)
                    _tr_run_state["errors"] += 1
                    try:
                        from models import TranslationErrorLog, Video as _V
                        async with AsyncSessionLocal() as es:
                            v = (await es.execute(select(_V.id).where(_V.youtube_id == yid))).scalar_one_or_none()
                            es.add(TranslationErrorLog(
                                video_id=v, youtube_id=yid, run_id=_tr_run_state.get("started_at"),
                                provider=provider, model=model, segment_index=None,
                                error_type="video", error_msg=str(exc)[:500], source_text=None, cost_usd=0.0,
                            ))
                            await es.commit()
                    except Exception:
                        pass
                _tr_run_state["processed"] += 1
                if pace:
                    await asyncio.sleep(pace)

        # Videos run concurrently (bounded by vsem); each gets its own session — safe.
        await asyncio.gather(*[_do_video(y) for y in targets])
    finally:
        _tr_run_state["running"] = False
        _tr_run_state["current"] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/batch/translate/run")
async def start_translate_run(body: TranslateRunRequest) -> dict:
    global _tr_run_task
    if _tr_run_state["running"]:
        raise HTTPException(409, detail="A translation run is already in progress.")
    if body.mode not in {"pending", "all", "ids"}:
        raise HTTPException(422, detail="mode must be pending | all | ids")

    cfg = _cfg()
    llm = cfg.get("llm", {})
    trun = cfg.get("translate_run", {})
    provider = body.provider or llm.get("provider", "openrouter")
    model = body.model or llm.get("model", "google/gemma-3-27b-it")
    concurrency = body.concurrency or int(llm.get("concurrency", 5))
    batch_size = body.batch_size or int(llm.get("batch_size", 1))
    video_concurrency = body.video_concurrency or int(trun.get("video_concurrency", 2))
    pace = body.pace if body.pace is not None else float(
        trun.get("pace_s", os.environ.get("TRANSLATE_PACE", "0.0"))
    )

    _tr_run_state.update(
        running=True, stop=False, mode=body.mode, total=0, processed=0,
        translated=0, errors=0, skipped=0, current=None,
        provider=provider, model=model,
        started_at=datetime.now(timezone.utc).isoformat(),
        cost_usd=0.0, prompt_tokens=0, completion_tokens=0,
    )
    _tr_run_task = asyncio.create_task(
        _tr_run_loop(body.mode, body.ids, body.limit, provider, model,
                     concurrency, batch_size, video_concurrency, pace)
    )
    return _public_tr_state()


@router.get("/batch/translate/run/status")
async def translate_run_status() -> dict:
    return _public_tr_state()


@router.post("/batch/translate/run/stop")
async def stop_translate_run() -> dict:
    _tr_run_state["stop"] = True
    return {"stopping": _tr_run_state["running"]}
