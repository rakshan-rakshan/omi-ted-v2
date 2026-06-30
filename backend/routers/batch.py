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

The per-video core lives in translate_video_segments() so the bulk-translate
runner (routers/translate_runner.py) can reuse it across many videos.
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, get_session
from models import Segment, TranslationCostLog, TranslationErrorLog, Video
from services.glossary_applier import GlossaryApplier
from services.glossary_prompt import hint_for_text
from services.transcript import fetch_video
from services.translate import CostMeter, translate, translate_batch
from services.translation_cache import TranslationCache

# Pure caption markers like [Music] / (applause) — never worth a translation call.
_MARKER_RE = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")


def _classify_error(msg: str) -> str:
    m = (msg or "").lower()
    if "timeout" in m or "timed out" in m: return "timeout"
    if "401" in m or "403" in m or "unauthor" in m or "api key" in m or "api_key" in m: return "auth"
    if "429" in m or "rate" in m or "quota" in m: return "rate_limit"
    if "500" in m or "502" in m or "503" in m or "504" in m: return "server"
    if "connect" in m or "network" in m or "transport" in m: return "network"
    return "exception"


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


async def translate_video_segments(
    video: Video,
    *,
    session: AsyncSession,
    provider: str | None = "openrouter",
    model: str | None = "google/gemma-3-27b-it",
    force: bool = False,
    concurrency: int = 5,
    batch_size: int = 1,
    glossary: GlossaryApplier | None = None,
    segment_ids: list[int] | None = None,
    run_id: str | None = None,
) -> dict:
    """Translate one fetched video's segments in place, then commit.

    provider == "youtube" promotes YouTube's own en_auto -> en_final for free
    (no API calls), backfilling en_auto from a fresh fetch when needed. Any other
    provider calls translate() per segment, concurrency-limited within the video.

    Returns counts: {"translated", "skipped", "errors"}. Raises HTTPException for
    the youtube path when YouTube can't supply English captions (single-endpoint use);
    the bulk runner catches exceptions per video so one bad video never stops a run.
    """
    seg_result = await session.execute(
        select(Segment).where(Segment.video_id == video.id).order_by(Segment.segment_index)
    )
    segments = seg_result.scalars().all()

    # Filter to specific segments if segment_ids provided
    if segment_ids:
        segments = [s for s in segments if s.id in set(segment_ids)]
        if not segments:
            raise HTTPException(status_code=404, detail="No matching segments found.")

    if provider == "youtube":
        # Free: backfill YouTube's own Telugu -> English caption translation
        # when older ingests have Telugu but no en_auto, then promote en_auto
        # to en_final where the human column is still empty.
        needs_backfill = [
            s for s in segments
            if force or not (s.en_auto and s.en_auto.strip())
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
        return {
            "translated": count, "skipped": len(segments) - count, "errors": 0,
            "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0,
        }

    # Worth translating: forced OR missing en_auto; skip empty text + pure [Music]/(applause) markers.
    to_translate = [
        s for s in segments
        if (force or not (s.en_auto and s.en_auto.strip()))
        and s.te_original and s.te_original.strip()
        and not _MARKER_RE.match(s.te_original)
    ]
    skipped = len(segments) - len(to_translate)
    prov = provider or "openrouter"

    # Map each unique source text back to a representative segment_index, and an
    # accumulator for failures. Records are built AFTER each gather (never appended
    # inside the concurrent coroutines) to avoid a list.append race.
    text_to_seg_index: dict[str, int] = {}
    for s in to_translate:
        text_to_seg_index.setdefault(s.te_original, s.segment_index)
    error_records: list[dict] = []

    # Cost meter for this video's translation pass.
    video_meter = CostMeter(provider=prov, model=model or "")

    # Glossary applier built once and reused (caller passes one per-run to avoid re-scanning).
    applier = glossary or await GlossaryApplier.from_db(session)
    # Raw terms for prompt-injection (OpenRouter only — other providers take no prompt).
    gloss_terms = applier.terms_raw if prov == "openrouter" else []

    # Dedup identical source texts within the video — common in sermons (refrains, "Amen", scripture).
    unique_texts = list({s.te_original for s in to_translate})

    # 1) Pre-load cache hits in ONE short-lived session (skip reads on a forced re-run).
    results: dict[str, str] = {}
    if not force:
        async with AsyncSessionLocal() as cs:
            tc = TranslationCache(cs)
            for txt in unique_texts:
                hit = await tc.get(txt, "te", "en", prov)
                if hit is not None:
                    results[txt] = applier.apply(hit)

    # 2) Translate the misses — each in its OWN short-lived session (cache writes happen there),
    #    keeping all concurrent DB I/O off the shared `session`.
    misses = [t for t in unique_texts if t not in results]
    sem = asyncio.Semaphore(concurrency)

    if batch_size > 1 and prov == "openrouter":
        # B3 batching path: chunk misses into groups, one OpenRouter call per chunk.
        async def _batch_chunk(chunk: list[str]) -> tuple[list[tuple[str, str | None]], str | None]:
            async with sem:
                async with AsyncSessionLocal() as fs:
                    tc = TranslationCache(fs)
                    local_m = CostMeter()
                    try:
                        translations = await translate_batch(
                            chunk, src="te", tgt="en", model=model, meter=local_m,
                            glossary_hint=hint_for_text("\n".join(chunk), gloss_terms),
                        )
                        pairs: list[tuple[str, str | None]] = []
                        for txt, en_raw in zip(chunk, translations):
                            if en_raw and en_raw.strip():
                                en = applier.apply(en_raw)
                                await tc.set(txt, "te", "en", prov, en_raw)
                                pairs.append((txt, en))
                            else:
                                pairs.append((txt, None))
                        await fs.commit()
                        return pairs, None
                    except Exception as exc:
                        logger.warning("Batch chunk failed: %s", exc)
                        return [(txt, None) for txt in chunk], str(exc)[:500]
                    finally:
                        video_meter.accumulate(local_m)

        chunks = [misses[i:i + batch_size] for i in range(0, len(misses), batch_size)]
        chunk_results = await asyncio.gather(*[_batch_chunk(c) for c in chunks])
        for pairs, err in chunk_results:
            for txt, en in pairs:
                if err:
                    error_records.append({"segment_index": text_to_seg_index.get(txt), "source_text": txt[:200], "error_type": _classify_error(err), "error_msg": err})
                if en:
                    results[txt] = en
    else:
        # Per-segment path — each call returns (txt, en, local_meter, err).
        async def _tx(txt: str) -> tuple[str, str | None, CostMeter, str | None]:
            async with sem:
                async with AsyncSessionLocal() as fs:
                    local_m = CostMeter()
                    try:
                        en = await translate(
                            txt, src="te", tgt="en", provider=provider, model=model,
                            cache=TranslationCache(fs), meter=local_m,
                            read_cache=False, apply_glossary=False,
                            glossary_hint=hint_for_text(txt, gloss_terms),
                        )
                        return txt, (applier.apply(en) if en else None), local_m, None
                    except Exception as exc:
                        logger.warning("Translation failed: %s", exc)
                        return txt, None, local_m, str(exc)[:500]

        if misses:
            for txt, en, lm, err in await asyncio.gather(*[_tx(t) for t in misses]):
                video_meter.accumulate(lm)
                if err:
                    error_records.append({"segment_index": text_to_seg_index.get(txt), "source_text": txt[:200], "error_type": _classify_error(err), "error_msg": err})
                if en:
                    results[txt] = en

    # 3) Write back on the shared session — single commit, never clobber a human edit.
    translated_count = 0
    for seg in to_translate:
        en = results.get(seg.te_original)
        if not en:
            continue
        seg.en_auto = en
        if not (seg.en_human and seg.en_human.strip()):
            seg.en_final = en
        translated_count += 1

    error_count = len(to_translate) - translated_count
    await session.commit()

    # 4) Record cost + error logs in a fresh session (never reuse session after commit).
    if translated_count > 0 or video_meter.cost_usd > 0 or error_records:
        async with AsyncSessionLocal() as cost_session:
            if translated_count > 0 or video_meter.cost_usd > 0:
                cost_session.add(TranslationCostLog(
                    video_id=video.id, run_id=run_id, provider=video_meter.provider,
                    model=video_meter.model or model, segments=translated_count,
                    prompt_tokens=video_meter.prompt_tokens,
                    completion_tokens=video_meter.completion_tokens,
                    cost_usd=round(video_meter.cost_usd, 8),
                ))
            for er in error_records:
                cost_session.add(TranslationErrorLog(
                    video_id=video.id, youtube_id=video.youtube_id, run_id=run_id,
                    provider=video_meter.provider, model=video_meter.model or model,
                    segment_index=er["segment_index"], error_type=er["error_type"],
                    error_msg=er["error_msg"], source_text=er["source_text"],
                    cost_usd=round(video_meter.cost_usd, 8),
                ))
            await cost_session.commit()

    return {
        "translated": translated_count,
        "skipped": skipped,
        "errors": error_count,
        "cost_usd": round(video_meter.cost_usd, 8),
        "prompt_tokens": video_meter.prompt_tokens,
        "completion_tokens": video_meter.completion_tokens,
    }


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

    if body.provider == "youtube":
        try:
            counts = await translate_video_segments(
                video,
                session=session,
                provider="youtube",
                force=body.force,
                segment_ids=body.segment_ids,
            )
        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is
        except Exception as exc:
            logger.error("YouTube translate failed for %s: %s", body.youtube_id, exc)
            raise HTTPException(
                status_code=502,
                detail=f"YouTube auto-translation failed: {exc}. Try using Sarvam or OpenRouter instead.",
            ) from exc
        return TranslateResponse(
            youtube_id=body.youtube_id, provider="youtube",
            translated=counts["translated"], skipped=counts["skipped"], errors=0,
            message=f"Applied {counts['translated']} YouTube auto-translations to en_final.",
        )

    counts = await translate_video_segments(
        video,
        session=session,
        provider=body.provider,
        model=body.model,
        force=body.force,
        concurrency=body.concurrency,
        segment_ids=body.segment_ids,
    )
    translated_count = counts["translated"]
    skipped = counts["skipped"]
    error_count = counts["errors"]

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
