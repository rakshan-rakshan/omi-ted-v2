"""
Translation analytics + utility endpoints.

GET /api/v1/translation/overview  â€” aggregate cost + progress stats
GET /api/v1/translation/flags     â€” suspicious/low-quality segments
GET /api/v1/translation/sample    â€” A/B model comparison (on-demand, no persistence)
GET /api/v1/credits               â€” provider credit balances
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import Segment, TranslationCacheEntry, TranslationCostLog, Video

logger = logging.getLogger(__name__)

router = APIRouter(tags=["translation"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class OverviewResponse(BaseModel):
    total_cost_usd: float
    total_translated_segs: int
    by_model: list[dict]
    cache_saved_usd: float
    recent_runs: list[dict]


class FlagsResponse(BaseModel):
    flags: list[dict]
    total: int


class CreditsResponse(BaseModel):
    openrouter: dict | None
    sarvam: dict


# ---------------------------------------------------------------------------
# Endpoint 1: GET /translation/overview
# ---------------------------------------------------------------------------


@router.get("/translation/overview", response_model=OverviewResponse)
async def translation_overview(
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    """Aggregate cost + progress stats across all translation runs."""

    # --- cost log aggregates (table may not exist yet) ---
    by_model: list[dict] = []
    recent_runs: list[dict] = []
    total_cost_usd: float = 0.0
    cache_saved_usd: float = 0.0

    try:
        # GROUP BY provider + model
        agg_rows = await session.execute(
            select(
                TranslationCostLog.provider,
                TranslationCostLog.model,
                func.sum(TranslationCostLog.cost_usd).label("cost_usd"),
                func.sum(TranslationCostLog.segments).label("segments"),
                func.sum(TranslationCostLog.prompt_tokens).label("prompt_tokens"),
                func.sum(TranslationCostLog.completion_tokens).label("completion_tokens"),
            ).group_by(TranslationCostLog.provider, TranslationCostLog.model)
        )
        for row in agg_rows.mappings():
            entry = {
                "provider": row["provider"],
                "model": row["model"],
                "cost_usd": float(row["cost_usd"] or 0.0),
                "segments": int(row["segments"] or 0),
                "prompt_tokens": int(row["prompt_tokens"] or 0),
                "completion_tokens": int(row["completion_tokens"] or 0),
            }
            by_model.append(entry)
            total_cost_usd += entry["cost_usd"]

        # Last 10 runs (individual log rows)
        recent_result = await session.execute(
            select(TranslationCostLog)
            .order_by(TranslationCostLog.created_at.desc())
            .limit(10)
        )
        for log in recent_result.scalars():
            recent_runs.append(
                {
                    "id": log.id,
                    "video_id": log.video_id,
                    "run_id": log.run_id,
                    "provider": log.provider,
                    "model": log.model,
                    "segments": log.segments,
                    "prompt_tokens": log.prompt_tokens,
                    "completion_tokens": log.completion_tokens,
                    "cost_usd": log.cost_usd,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
            )

        # Estimate cache savings: cache hits * avg cost per segment
        if total_cost_usd > 0 and by_model:
            total_paid_segs = sum(e["segments"] for e in by_model)
            avg_cost_per_seg = total_cost_usd / total_paid_segs if total_paid_segs else 0.0
        else:
            avg_cost_per_seg = 0.0

    except (OperationalError, ProgrammingError):
        # migration 007 not run yet â€” return zeros
        avg_cost_per_seg = 0.0

    # Cache hit count (translation_cache table exists from earlier migration)
    try:
        cache_count_result = await session.execute(
            select(func.count(TranslationCacheEntry.id))
        )
        cache_count = cache_count_result.scalar() or 0
        cache_saved_usd = cache_count * avg_cost_per_seg
    except (OperationalError, ProgrammingError):
        cache_saved_usd = 0.0

    # Total translated segments (en_final not null / not empty)
    try:
        translated_result = await session.execute(
            select(func.count(Segment.id)).where(
                Segment.en_final.isnot(None),
                Segment.en_final != "",
            )
        )
        total_translated_segs = translated_result.scalar() or 0
    except (OperationalError, ProgrammingError):
        total_translated_segs = 0

    return OverviewResponse(
        total_cost_usd=total_cost_usd,
        total_translated_segs=int(total_translated_segs),
        by_model=by_model,
        cache_saved_usd=cache_saved_usd,
        recent_runs=recent_runs,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: GET /translation/flags
# ---------------------------------------------------------------------------


@router.get("/translation/flags", response_model=FlagsResponse)
async def translation_flags(
    session: AsyncSession = Depends(get_session),
) -> FlagsResponse:
    """Find suspicious or low-quality segments across all videos."""

    flags: list[dict] = []

    try:
        # --- issue="empty": en_final null/empty on fetched videos ---
        empty_result = await session.execute(
            select(
                Segment.id.label("segment_id"),
                Segment.video_id,
                Video.youtube_id,
                Segment.te_original,
                Segment.en_final,
                Segment.quality_score,
            )
            .join(Video, Segment.video_id == Video.id)
            .where(
                Video.status == "fetched",
                (Segment.en_final.is_(None)) | (Segment.en_final == ""),
            )
            .limit(100)
        )
        for row in empty_result.mappings():
            flags.append(
                {
                    "segment_id": row["segment_id"],
                    "video_id": row["video_id"],
                    "youtube_id": row["youtube_id"],
                    "issue": "empty",
                    "te_original": row["te_original"],
                    "en_final": row["en_final"],
                    "quality_score": row["quality_score"],
                }
            )

        # --- issue="identical": en_final == te_original (not null, len > 3) ---
        # Fetch candidates and filter in Python for SQLite compat
        identical_result = await session.execute(
            select(
                Segment.id.label("segment_id"),
                Segment.video_id,
                Video.youtube_id,
                Segment.te_original,
                Segment.en_final,
                Segment.quality_score,
            )
            .join(Video, Segment.video_id == Video.id)
            .where(
                Segment.en_final.isnot(None),
            )
            .limit(500)
        )
        for row in identical_result.mappings():
            te = row["te_original"] or ""
            en = row["en_final"] or ""
            if len(en) > 3 and en == te:
                flags.append(
                    {
                        "segment_id": row["segment_id"],
                        "video_id": row["video_id"],
                        "youtube_id": row["youtube_id"],
                        "issue": "identical",
                        "te_original": te,
                        "en_final": en,
                        "quality_score": row["quality_score"],
                    }
                )

        # --- issue="length_ratio": extreme length ratio ---
        ratio_result = await session.execute(
            select(
                Segment.id.label("segment_id"),
                Segment.video_id,
                Video.youtube_id,
                Segment.te_original,
                Segment.en_final,
                Segment.quality_score,
            )
            .join(Video, Segment.video_id == Video.id)
            .where(
                Segment.en_final.isnot(None),
                Segment.te_original.isnot(None),
            )
            .limit(500)
        )
        for row in ratio_result.mappings():
            te = row["te_original"] or ""
            en = row["en_final"] or ""
            if len(te) > 10 and len(en) > 10:
                ratio = len(en) / len(te)
                if ratio > 5 or ratio < 0.1:
                    flags.append(
                        {
                            "segment_id": row["segment_id"],
                            "video_id": row["video_id"],
                            "youtube_id": row["youtube_id"],
                            "issue": "length_ratio",
                            "te_original": te,
                            "en_final": en,
                            "quality_score": row["quality_score"],
                        }
                    )

        # --- issue="unreviewed": is_reviewed=False + quality_score < 3 ---
        unreviewed_result = await session.execute(
            select(
                Segment.id.label("segment_id"),
                Segment.video_id,
                Video.youtube_id,
                Segment.te_original,
                Segment.en_final,
                Segment.quality_score,
            )
            .join(Video, Segment.video_id == Video.id)
            .where(
                Segment.is_reviewed == False,  # noqa: E712
                Segment.quality_score.isnot(None),
                Segment.quality_score < 3,
            )
            .limit(100)
        )
        for row in unreviewed_result.mappings():
            flags.append(
                {
                    "segment_id": row["segment_id"],
                    "video_id": row["video_id"],
                    "youtube_id": row["youtube_id"],
                    "issue": "unreviewed",
                    "te_original": row["te_original"],
                    "en_final": row["en_final"],
                    "quality_score": row["quality_score"],
                }
            )

    except (OperationalError, ProgrammingError) as exc:
        logger.warning("translation_flags: DB error: %s", exc)

    # Deduplicate by segment_id+issue and cap at 100
    seen: set[tuple[int, str]] = set()
    deduped: list[dict] = []
    for f in flags:
        key = (f["segment_id"], f["issue"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
        if len(deduped) >= 100:
            break

    return FlagsResponse(flags=deduped, total=len(deduped))


# ---------------------------------------------------------------------------
# Endpoint 3: GET /translation/sample
# ---------------------------------------------------------------------------


@router.get("/translation/sample")
async def translation_sample(
    models: str = Query(..., description="Comma-separated provider::modelid strings"),
    n: int = Query(5, ge=1, le=20, description="Number of segments to sample"),
    youtube_id: str | None = Query(None, description="Filter to a specific video"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """On-demand A/B translation comparison. No caching, no persistence."""

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return {"segments": [], "error": "OPENROUTER_API_KEY not configured"}

    model_keys = [m.strip() for m in models.split(",") if m.strip()]
    if not model_keys:
        return {"segments": [], "error": "No models specified"}

    # Fetch n random segments with te_original len > 20
    try:
        query = (
            select(Segment)
            .join(Video, Segment.video_id == Video.id)
            .where(Video.status == "fetched")
        )
        if youtube_id:
            query = query.where(Video.youtube_id == youtube_id)

        # Fetch a larger batch and filter/sample in Python for SQLite compat
        result = await session.execute(query.limit(200))
        candidates = [
            seg for seg in result.scalars()
            if seg.te_original and len(seg.te_original) > 20
        ]
    except (OperationalError, ProgrammingError) as exc:
        return {"segments": [], "error": f"DB error: {exc}"}

    if not candidates:
        return {"segments": [], "error": "No eligible segments found"}

    import random as _random
    sampled = _random.sample(candidates, min(n, len(candidates)))

    # Import translate service
    from services.translate import translate

    output_segments: list[dict] = []
    error: str | None = None

    for seg in sampled:
        results: dict[str, str] = {}
        for model_key in model_keys:
            # Parse "provider::modelid"
            if "::" in model_key:
                provider_part, model_part = model_key.split("::", 1)
            else:
                provider_part = "openrouter"
                model_part = model_key

            try:
                translation = await translate(
                    text=seg.te_original,
                    src="te",
                    tgt="en",
                    provider=provider_part,
                    model=model_part,
                    cache=None,
                    meter=None,
                    read_cache=False,
                    apply_glossary=False,
                )
                results[model_key] = translation
            except Exception as exc:
                results[model_key] = f"[ERROR: {exc}]"
                error = str(exc)

        output_segments.append(
            {
                "te_original": seg.te_original,
                "results": results,
            }
        )

    return {"segments": output_segments, "error": error}


# ---------------------------------------------------------------------------
# Endpoint 4: GET /credits
# ---------------------------------------------------------------------------


@router.get("/credits", response_model=CreditsResponse)
async def get_credits() -> CreditsResponse:
    """Return provider credit balances."""

    sarvam_info: dict = {
        "note": "No public balance API. Check sarvam.ai dashboard."
    }

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        openrouter_info: dict | None = {
            "error": "OPENROUTER_API_KEY not set",
            "limit": None,
            "usage": 0,
            "remaining": None,
            "is_free_tier": False,
        }
        return CreditsResponse(openrouter=openrouter_info, sarvam=sarvam_info)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {key}"},
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            limit = data.get("limit")
            usage = float(data.get("usage", 0) or 0)
            is_free_tier = bool(data.get("is_free_tier", False))
            remaining = (float(limit) - usage) if limit is not None else None
            openrouter_info = {
                "limit": limit,
                "usage": usage,
                "remaining": remaining,
                "is_free_tier": is_free_tier,
            }
    except Exception as exc:
        openrouter_info = {
            "error": str(exc),
            "limit": None,
            "usage": 0,
            "remaining": None,
            "is_free_tier": False,
        }

    return CreditsResponse(openrouter=openrouter_info, sarvam=sarvam_info)
