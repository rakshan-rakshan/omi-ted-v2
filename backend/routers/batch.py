"""
Batch translation — provider-agnostic, per-request provider/model override.

POST /api/v1/batch/translate
  {
    "youtube_id": "...",
    "provider": "youtube | sarvam | openrouter",
    "model": "google/gemma-3-27b-it",   // OpenRouter only
    "force": false,
    "concurrency": 5
  }

Provider "youtube" is free — it copies en_auto already in the DB to en_final
(no API calls). All others call translate().
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Segment, Video
from services.transcript import fetch_video
from services.translate import translate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch"])


class TranslateRequest(BaseModel):
    youtube_id: str
    provider: str = "openrouter"          # youtube | sarvam | openrouter
    model: str = "google/gemma-3-27b-it"  # OpenRouter model ID
    force: bool = False
    concurrency: int = 5
    segment_ids: list[int] | None = None  # If provided, only translate these segments


class TranslateResponse(BaseModel):
    youtube_id: str
    provider: str
    translated: int
    skipped: int
    errors: int
    message: str


@router.post("/batch/translate", response_model=TranslateResponse)
async def batch_translate(
    body: TranslateRequest,
    session: AsyncSession = Depends(get_session),
) -> TranslateResponse:
    result = await session.execute(select(Video).where(Video.youtube_id == body.youtube_id))
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail=f"Video {body.youtube_id} not found.")
    if video.status != "fetched":
        raise HTTPException(status_code=409, detail=f"Video not ready (status={video.status}).")

    seg_result = await session.execute(
        select(Segment).where(Segment.video_id == video.id).order_by(Segment.segment_index)
    )
    segments = seg_result.scalars().all()

    # Filter to specific segments if segment_ids provided
    if body.segment_ids:
        segments = [s for s in segments if s.id in set(body.segment_ids)]
        if not segments:
            raise HTTPException(status_code=404, detail="No matching segments found.")

    if body.provider == "youtube":
        try:
            # Free: backfill YouTube's own Telugu -> English caption translation
            # when older ingests have Telugu but no en_auto, then promote en_auto
            # to en_final where the human column is still empty.
            needs_backfill = [
                s for s in segments
                if body.force or not (s.en_auto and s.en_auto.strip())
            ]
            existing_auto_count = sum(
                1 for s in segments
                if s.en_auto and s.en_auto.strip()
            )
            if needs_backfill:
                try:
                    data = await fetch_video(video.youtube_id)
                except Exception as exc:
                    if existing_auto_count == 0:
                        raise HTTPException(
                            status_code=424,
                            detail=(
                                "YouTube free auto-translation is unavailable for this video right now. "
                                f"Telugu captions were found, but English translated captions could not be fetched: {exc}"
                            ),
                        ) from exc
                    data = None

                fetched_by_index = {
                    seg.segment_index: seg
                    for seg in (data.segments if data else [])
                    if seg.en_auto and seg.en_auto.strip()
                }
                fetched = list(fetched_by_index.values())
                if not fetched and existing_auto_count == 0:
                    raise HTTPException(
                        status_code=424,
                        detail=(
                            "YouTube free auto-translation is unavailable for this video right now. "
                            "Telugu captions were found, but YouTube did not return English translated captions. "
                            "Retry later or use Sarvam/OpenRouter."
                        ),
                    )

                def _match_en_auto(segment: Segment) -> str | None:
                    if not fetched:
                        return None
                    by_index = fetched_by_index.get(segment.segment_index)
                    if by_index and abs(by_index.start_time - segment.start_time) <= 2.0:
                        return by_index.en_auto

                    best = min(
                        fetched,
                        key=lambda candidate: abs(candidate.start_time - segment.start_time),
                    )
                    return best.en_auto if abs(best.start_time - segment.start_time) <= 2.0 else None

                for s in needs_backfill:
                    en_auto = _match_en_auto(s)
                    if en_auto:
                        s.en_auto = en_auto
            # Free — just promote en_auto → en_final for segments that have it
            count = 0
            for s in segments:
                if s.en_auto and s.en_auto.strip():
                    if not s.en_human or not s.en_human.strip():
                        s.en_final = s.en_auto
                        count += 1
            await session.commit()
            return TranslateResponse(
                youtube_id=body.youtube_id, provider="youtube",
                translated=count, skipped=len(segments) - count, errors=0,
                message=f"Applied {count} YouTube auto-translations to en_final.",
            )
        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is
        except Exception as exc:
            logger.error("YouTube translate failed for %s: %s", body.youtube_id, exc)
            raise HTTPException(
                status_code=502,
                detail=f"YouTube auto-translation failed: {exc}. Try using Sarvam or OpenRouter instead.",
            ) from exc

    to_translate = [
        s for s in segments
        if body.force or not (s.en_auto and s.en_auto.strip())
    ]
    skipped = len(segments) - len(to_translate)
    translated_count = 0
    error_count = 0
    sem = asyncio.Semaphore(body.concurrency)

    async def _do_one(seg: Segment) -> None:
        nonlocal translated_count, error_count
        async with sem:
            try:
                en_text = await translate(
                    seg.te_original,
                    src="te", tgt="en",
                    provider=body.provider,
                    model=body.model,
                )
                seg.en_auto = en_text
                if not seg.en_human or not seg.en_human.strip():
                    seg.en_final = en_text
                translated_count += 1
            except Exception as exc:
                logger.warning("Translation failed seg %d: %s", seg.id, exc)
                error_count += 1

    await asyncio.gather(*[_do_one(seg) for seg in to_translate])
    await session.commit()

    message = (
        f"Translated {translated_count} segments via {body.provider}"
        + (f" ({body.model})" if body.provider == "openrouter" else "")
        + (f", skipped {skipped}" if skipped else "")
        + (f", {error_count} errors" if error_count else "")
        + "."
    )
    return TranslateResponse(
        youtube_id=body.youtube_id, provider=body.provider,
        translated=translated_count, skipped=skipped, errors=error_count, message=message,
    )
