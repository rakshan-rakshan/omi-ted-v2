"""
Bulk-translate untranslated segments te_original -> en_auto.

Provider-agnostic: the provider and model come from config.yaml (`llm.provider`
/ `llm.model`), NOT hardcoded. Swap providers with a config change, no code edit.

Each concurrent translation runs in its OWN AsyncSession (the translation cache +
glossary touch the DB) so we never share one session across asyncio.gather tasks
— that is the same concurrency bug that previously hung the RAG pipeline.

Usage:
    python -m scripts.translate_segments                  # all untranslated segments
    python -m scripts.translate_segments --limit 100      # small test batch
    python -m scripts.translate_segments --force --limit 50
    python -m scripts.translate_segments --concurrency 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import time

import sqlalchemy as sa

from database import AsyncSessionLocal
from models import Segment
from services.translate import _cfg, translate
from services.translation_cache import TranslationCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("translate_segments")

# Non-speech markers like [Music], [Laughter], [సంగీతం] — not real text. Sending them
# to an LLM wastes spend and yields meta-commentary, so skip pure-marker segments.
_MARKER_RE = re.compile(r"^\[[^\]]*\]$")


async def _fetch_pending(limit: int | None, force: bool) -> list[tuple[int, str]]:
    """Segment ids + Telugu text that need an English translation (markers skipped)."""
    async with AsyncSessionLocal() as s:
        q = sa.select(Segment.id, Segment.te_original).where(
            sa.func.coalesce(Segment.te_original, "") != ""
        )
        if not force:
            q = q.where(
                sa.or_(Segment.en_auto.is_(None), sa.func.trim(Segment.en_auto) == "")
            )
        q = q.order_by(Segment.id)
        rows = (await s.execute(q)).all()

    pending: list[tuple[int, str]] = []
    for r in rows:
        if _MARKER_RE.match((r.te_original or "").strip()):
            continue  # skip [Music]/[Laughter]/etc.
        pending.append((r.id, r.te_original))
        if limit and len(pending) >= limit:
            break
    return pending


async def _translate_one(
    seg_id: int, te_text: str, sem: asyncio.Semaphore
) -> tuple[int, str | None, str | None]:
    """Translate one segment in its own short-lived session. Returns (id, en, err)."""
    async with sem:
        async with AsyncSessionLocal() as s:
            cache = TranslationCache(s)
            try:
                en = await translate(te_text, src="te", tgt="en", cache=cache)
                return seg_id, (en or None), None
            except Exception as exc:  # provider error, timeout, etc.
                return seg_id, None, f"{type(exc).__name__}: {exc}"


async def _write_back(results: list[tuple[int, str | None, str | None]]) -> int:
    """Persist en_auto/en_final for successful translations."""
    written = 0
    async with AsyncSessionLocal() as s:
        for seg_id, en, err in results:
            if err or not en:
                continue
            seg = await s.get(Segment, seg_id)
            if seg is None:
                continue
            seg.en_auto = en
            # Don't clobber a human translation; mirror to en_final otherwise.
            if not (seg.en_human and seg.en_human.strip()):
                seg.en_final = en
            written += 1
        await s.commit()
    return written


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="max segments (test batches)")
    ap.add_argument("--force", action="store_true", help="re-translate even if en_auto set")
    ap.add_argument("--concurrency", type=int, default=5, help="parallel translation calls")
    args = ap.parse_args()

    llm = _cfg().get("llm", {})
    logger.info(
        "Translation provider=%s model=%s (config-driven)",
        llm.get("provider"), llm.get("model"),
    )

    pending = await _fetch_pending(args.limit, args.force)
    logger.info("%d segment(s) need translation", len(pending))
    if not pending:
        return

    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.monotonic()
    tasks = [asyncio.create_task(_translate_one(sid, txt, sem)) for sid, txt in pending]

    results: list[tuple[int, str | None, str | None]] = []
    for fut in asyncio.as_completed(tasks):
        results.append(await fut)
        if len(results) % 20 == 0:
            logger.info("  %d/%d translated", len(results), len(pending))

    errors = [r for r in results if r[2]]
    written = await _write_back(results)
    dt = time.monotonic() - t0
    logger.info(
        "Done. wrote=%d errors=%d in %.1fs (%.2fs/seg avg)",
        written, len(errors), dt, dt / max(len(pending), 1),
    )
    for sid, _, err in errors[:5]:
        logger.warning("  seg %s failed: %s", sid, err)


if __name__ == "__main__":
    asyncio.run(main())
