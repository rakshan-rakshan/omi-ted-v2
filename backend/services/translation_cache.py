"""Async translation cache backed by TranslationCacheEntry model.

Key is SHA256 hash of ``f"{provider}:{src}:{tgt}:{text}"``.
"""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import TranslationCacheEntry

logger = logging.getLogger(__name__)


class TranslationCache:
    """Keyed on SHA256(provider:src:tgt:text)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _make_key(text: str, src: str, tgt: str, provider: str) -> str:
        raw = f"{provider}:{src}:{tgt}:{text}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, text: str, src: str, tgt: str, provider: str) -> str | None:
        key = self._make_key(text, src, tgt, provider)
        row = await self.session.execute(
            select(TranslationCacheEntry).where(
                TranslationCacheEntry.cache_key == key,
                TranslationCacheEntry.src_lang == src,
                TranslationCacheEntry.tgt_lang == tgt,
                TranslationCacheEntry.provider == provider,
            )
        )
        entry = row.scalar_one_or_none()
        if entry is not None:
            logger.debug("Cache hit for key=%s", key[:12])
            return entry.en_text
        logger.debug("Cache miss for key=%s", key[:12])
        return None

    async def set(
        self, text: str, src: str, tgt: str, provider: str, en_text: str
    ) -> None:
        key = self._make_key(text, src, tgt, provider)
        entry = TranslationCacheEntry(
            cache_key=key,
            te_text=text,
            en_text=en_text,
            src_lang=src,
            tgt_lang=tgt,
            provider=provider,
        )
        self.session.add(entry)
        try:
            await self.session.commit()
            logger.debug("Cache set for key=%s", key[:12])
        except IntegrityError:
            # Another concurrent task cached the same text first — harmless.
            await self.session.rollback()
            logger.debug("Cache key already present (race), skipped: %s", key[:12])
