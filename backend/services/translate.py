"""
Translation service. Provider and model can be overridden per-call.
Config.yaml sets defaults; batch.py passes explicit values.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
import yaml

from services.glossary_applier import GlossaryApplier
from services.translation_cache import TranslationCache

logger = logging.getLogger(__name__)

def _cfg() -> dict:
    p = Path(__file__).parent.parent / "config.yaml"
    with open(p) as f:
        return yaml.safe_load(f)

async def _sarvam(text: str, src: str, tgt: str, timeout: int) -> str:
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise EnvironmentError("SARVAM_API_KEY not set. Add it in Settings.")
    lang = {"te": "te-IN", "en": "en-IN"}
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(
            "https://api.sarvam.ai/translate",
            json={"input": text, "source_language_code": lang.get(src, src),
                  "target_language_code": lang.get(tgt, tgt),
                  "speaker_gender": "Male", "mode": "formal",
                  "model": "mayura:v1", "enable_preprocessing": False},
            headers={"api-subscription-key": key, "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["translated_text"]

async def _google(text: str, src: str, tgt: str, timeout: int) -> str:
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise EnvironmentError("GOOGLE_API_KEY not set. Add it in Settings.")
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(
            "https://translation.googleapis.com/language/translate/v2",
            params={"key": key},
            json={"q": text, "source": src, "target": tgt, "format": "text"},
        )
        r.raise_for_status()
        return r.json()["data"]["translations"][0]["translatedText"]

async def _openrouter(text: str, src: str, tgt: str, model: str, timeout: int) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise EnvironmentError("OPENROUTER_API_KEY not set. Add it in Settings.")
    prompt = (
        f"Translate this Telugu Christian sermon text to English. "
        f"Preserve theological terms accurately. Output only the translation.\n\n{text}"
    )
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "HTTP-Referer": "https://github.com/omi-ted",
                     "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def _indictrans2(text: str, src: str, tgt: str) -> str | None:
    from services.indictrans2 import translate as it2_translate
    try:
        return await it2_translate(text, src, tgt)
    except Exception:
        return None

async def translate(
    text: str,
    src: str = "te",
    tgt: str = "en",
    provider: str | None = None,
    model: str | None = None,
    cache: TranslationCache | None = None,
) -> str:
    if not text or not text.strip():
        return ""
    cfg = _cfg()
    llm = cfg.get("llm", {})
    p = provider or llm.get("provider", "openrouter")
    m = model or llm.get("model", "google/gemma-3-27b-it")
    t = llm.get("timeout_s", 30)

    # Check cache
    if cache and llm.get("cache", True):
        cached = await cache.get(text, src, tgt, p)
        if cached is not None:
            return cached

    if p == "sarvam":
        result = await _sarvam(text, src, tgt, t)
    elif p == "openrouter":
        result = await _openrouter(text, src, tgt, m, t)
    elif p == "indictrans2":
        result = await _indictrans2(text, src, tgt)
        if result is None:
            fallback = cfg.get("indictrans2", {}).get("fallback_provider", "openrouter")
            if fallback == "sarvam":
                result = await _sarvam(text, src, tgt, t)
            else:
                result = await _openrouter(text, src, tgt, m, t)
    elif p == "google":
        result = await _google(text, src, tgt, t)
    else:
        raise ValueError(f"Unknown provider: {p!r}")

    # Write to cache
    if cache and llm.get("cache", True) and result:
        await cache.set(text, src, tgt, p, result)

    # Glossary post-processing
    if result and cache:
        applier = await GlossaryApplier.from_db(cache.session)
        result = applier.apply(result)

    return result
