"""
Translation model catalog — powers the provider/model selector + cost display.

GET /api/v1/models — selectable translators across providers, with pricing:
  - youtube        : free caption promotion (no API)
  - sarvam         : Mayura v1, ₹20 / 10k chars (per-character)
  - openrouter     : every model, free + paid, with live $/Mtok pricing

The OpenRouter list is fetched live and cached in-process (~1h TTL); on fetch
failure the last good list is served (or just the static providers).
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

router = APIRouter(tags=["models"])

# Sarvam Mayura v1 — ₹20 per 10,000 characters (per-character billing). Source: sarvam.ai/api-pricing.
SARVAM_INR_PER_CHAR = 0.002

_OR_CACHE: dict = {"at": 0.0, "data": []}
_OR_TTL_S = 3600.0


async def _openrouter_models() -> list[dict]:
    """OpenRouter catalog with normalized pricing, cached ~1h. Serves stale on error."""
    now = time.monotonic()
    if _OR_CACHE["data"] and (now - _OR_CACHE["at"]) < _OR_TTL_S:
        return _OR_CACHE["data"]

    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
            for m in r.json().get("data", []):
                pricing = m.get("pricing", {}) or {}
                try:
                    pin = float(pricing.get("prompt", "0") or 0)
                    pout = float(pricing.get("completion", "0") or 0)
                except (TypeError, ValueError):
                    pin = pout = 0.0
                free = pin == 0.0 and pout == 0.0
                out.append({
                    "provider": "openrouter",
                    "model": m.get("id"),
                    "label": m.get("name") or m.get("id"),
                    "free": free,
                    "prompt_per_mtok": round(pin * 1_000_000, 4),
                    "completion_per_mtok": round(pout * 1_000_000, 4),
                    "context": m.get("context_length"),
                    "unit": "free" if free else "token",
                })
        out.sort(key=lambda o: (not o["free"], (o["label"] or "").lower()))
    except Exception:
        return _OR_CACHE["data"] or []  # keep last good list; don't break the selector

    _OR_CACHE["data"] = out
    _OR_CACHE["at"] = now
    return out


@router.get("/models")
async def list_models() -> dict:
    """All selectable translators, grouped client-side by provider + free/paid."""
    static = [
        {"provider": "youtube", "model": None, "label": "YouTube auto-captions",
         "free": True, "unit": "free"},
        {"provider": "sarvam", "model": "mayura:v1", "label": "Sarvam Mayura v1",
         "free": False, "inr_per_char": SARVAM_INR_PER_CHAR, "unit": "char"},
    ]
    openrouter = await _openrouter_models()
    return {"options": static + openrouter, "count": len(static) + len(openrouter)}
