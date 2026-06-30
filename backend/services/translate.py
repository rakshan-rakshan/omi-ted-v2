"""
Translation service. Provider and model can be overridden per-call.
Config.yaml sets defaults; batch.py passes explicit values.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

from services.glossary_applier import GlossaryApplier
from services.translation_cache import TranslationCache

logger = logging.getLogger(__name__)


@dataclass
class CostMeter:
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    char_count: int = 0

    def accumulate(self, other: "CostMeter") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd
        self.calls += other.calls
        self.char_count += other.char_count

def _cfg() -> dict:
    p = Path(__file__).parent.parent / "config.yaml"
    with open(p) as f:
        return yaml.safe_load(f)


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def _with_retry(coro_factory):
    """Run coro_factory() with exponential backoff on transient failures.

    Retries 429 + transient 5xx + timeouts/transport errors, honoring Retry-After
    on 429. Fails fast on auth/client errors (401/403/404). Tunable via config.yaml
    llm.retry_attempts / retry_base_s / retry_cap_s.
    """
    llm = _cfg().get("llm", {})
    attempts = int(llm.get("retry_attempts", 4))
    base = float(llm.get("retry_base_s", 1.0))
    cap = float(llm.get("retry_cap_s", 20.0))
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await coro_factory()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code not in RETRYABLE_STATUS or i == attempts - 1:
                raise
            # Out-of-credits won't fix itself (e.g. Sarvam returns 429 insufficient_quota_error).
            if code == 429:
                body = ""
                try:
                    body = exc.response.text or ""
                except Exception:
                    body = ""
                if "insufficient_quota" in body:
                    raise
            retry_after = exc.response.headers.get("retry-after")
            if code == 429 and retry_after and retry_after.isdigit():
                delay = min(cap, float(retry_after))
            else:
                delay = min(cap, base * (2 ** i))
            last = exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if i == attempts - 1:
                raise
            delay = min(cap, base * (2 ** i))
            last = exc
        await asyncio.sleep(delay + random.uniform(0, 0.3))
    if last:
        raise last
    raise RuntimeError("retry loop exhausted")  # pragma: no cover

async def _sarvam(text: str, src: str, tgt: str, timeout: int) -> str:
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        raise EnvironmentError("SARVAM_API_KEY not set. Add it in Settings.")
    lang = {"te": "te-IN", "en": "en-IN"}
    async def _do() -> str:
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
    return await _with_retry(_do)

async def _google(text: str, src: str, tgt: str, timeout: int) -> str:
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise EnvironmentError("GOOGLE_API_KEY not set. Add it in Settings.")
    async def _do() -> str:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": key},
                json={"q": text, "source": src, "target": tgt, "format": "text"},
            )
            r.raise_for_status()
            return r.json()["data"]["translations"][0]["translatedText"]
    return await _with_retry(_do)

async def _openrouter(text: str, src: str, tgt: str, model: str, timeout: int) -> tuple[str, dict]:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise EnvironmentError("OPENROUTER_API_KEY not set. Add it in Settings.")
    prompt = (
        f"Translate this Telugu Christian sermon text to English. "
        f"Preserve theological terms accurately. Output only the translation.\n\n{text}"
    )
    async def _do() -> tuple[str, dict]:
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
            data = r.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage") or {}
            return content, {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "cost_usd": float(usage.get("cost", 0.0) or 0.0),
            }
    return await _with_retry(_do)

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
    meter: "CostMeter | None" = None,
    *,
    read_cache: bool = True,
    apply_glossary: bool = True,
) -> str:
    if not text or not text.strip():
        return ""
    cfg = _cfg()
    llm = cfg.get("llm", {})
    p = provider or llm.get("provider", "openrouter")
    m = model or llm.get("model", "google/gemma-3-27b-it")
    t = llm.get("timeout_s", 30)

    # Check cache (skipped on forced re-translation via read_cache=False)
    if cache and llm.get("cache", True) and read_cache:
        cached = await cache.get(text, src, tgt, p)
        if cached is not None:
            return cached

    if p == "sarvam":
        result = await _sarvam(text, src, tgt, t)
        if meter:
            meter.char_count += len(text)
            meter.cost_usd += len(text) * 0.002 / float(cfg.get("inr_per_usd", 83))
            meter.calls += 1
            meter.provider = "sarvam"
    elif p == "openrouter":
        result, usage = await _openrouter(text, src, tgt, m, t)
        if meter:
            meter.prompt_tokens += usage["prompt_tokens"]
            meter.completion_tokens += usage["completion_tokens"]
            meter.cost_usd += usage["cost_usd"]
            meter.calls += 1
            meter.provider = "openrouter"
            meter.model = m
    elif p == "indictrans2":
        result = await _indictrans2(text, src, tgt)
        if result is None:
            fallback = cfg.get("indictrans2", {}).get("fallback_provider", "openrouter")
            if fallback == "sarvam":
                result = await _sarvam(text, src, tgt, t)
                if meter:
                    meter.char_count += len(text)
                    meter.cost_usd += len(text) * 0.002 / float(cfg.get("inr_per_usd", 83))
                    meter.calls += 1
                    meter.provider = "sarvam"
            else:
                result, usage = await _openrouter(text, src, tgt, m, t)
                if meter:
                    meter.prompt_tokens += usage["prompt_tokens"]
                    meter.completion_tokens += usage["completion_tokens"]
                    meter.cost_usd += usage["cost_usd"]
                    meter.calls += 1
                    meter.provider = "openrouter"
                    meter.model = m
    elif p == "google":
        result = await _google(text, src, tgt, t)
        if meter:
            meter.calls += 1
            meter.provider = "google"
    else:
        raise ValueError(f"Unknown provider: {p!r}")

    # Write to cache
    if cache and llm.get("cache", True) and result:
        await cache.set(text, src, tgt, p, result)

    # Glossary post-processing (skipped when the caller applies its own pre-built applier)
    if result and cache and apply_glossary:
        applier = await GlossaryApplier.from_db(cache.session)
        result = applier.apply(result)

    return result


_BATCH_LINE_RE = re.compile(r"^\s*(\d+)[.):]\s*(.*)", re.MULTILINE)


async def translate_batch(
    texts: list[str],
    src: str = "te",
    tgt: str = "en",
    model: str | None = None,
    meter: "CostMeter | None" = None,
) -> list[str]:
    """Pack N texts into one OpenRouter call. Falls back to per-segment on alignment failure."""
    if not texts:
        return []
    cfg = _cfg()
    llm = cfg.get("llm", {})
    m = model or llm.get("model", "google/gemma-3-27b-it")
    t = llm.get("timeout_s", 30)
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise EnvironmentError("OPENROUTER_API_KEY not set.")

    numbered = "\n".join(f"{i+1}. {txt}" for i, txt in enumerate(texts))
    prompt = (
        f"Translate each numbered Telugu Christian sermon segment to English. "
        f"Return EXACTLY {len(texts)} lines, each starting with 'N. ' where N matches the input number. "
        f"Preserve all Biblical names, theological terms, scripture references exactly. "
        f"Output only the numbered translations.\n\n{numbered}"
    )

    async def _do() -> tuple[str, dict]:
        async with httpx.AsyncClient(timeout=t) as c:
            r = await c.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://github.com/omi-ted", "Content-Type": "application/json"},
                json={"model": m, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage") or {}
            return data["choices"][0]["message"]["content"], {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "cost_usd": float(usage.get("cost", 0.0) or 0.0),
            }

    try:
        content, usage = await _with_retry(_do)
        matches = _BATCH_LINE_RE.findall(content)
        parsed = {int(n): txt.strip() for n, txt in matches}
        if len(parsed) == len(texts):
            if meter:
                meter.prompt_tokens += usage["prompt_tokens"]
                meter.completion_tokens += usage["completion_tokens"]
                meter.cost_usd += usage["cost_usd"]
                meter.calls += 1
                meter.provider = "openrouter"
                meter.model = m
            return [parsed.get(i + 1, "") for i in range(len(texts))]
        logger.warning(
            "translate_batch: expected %d lines, got %d — falling back per-segment",
            len(texts), len(parsed),
        )
    except Exception as exc:
        logger.warning("translate_batch failed: %s — per-segment fallback", exc)

    # Per-segment fallback (no batch meter update — each call updates meter individually)
    results = []
    for txt in texts:
        m_single = CostMeter()
        r = await translate(txt, src=src, tgt=tgt, provider="openrouter", model=model, meter=m_single)
        if meter:
            meter.accumulate(m_single)
        results.append(r)
    return results
