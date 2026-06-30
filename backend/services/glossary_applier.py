"""Glossary term replacement service.

Loads GlossaryTerm rows from DB and applies case-insensitive regex
replacement of Telugu terms → English terms on translated text.
"""
from __future__ import annotations

import logging
import re

from models import GlossaryTerm

logger = logging.getLogger(__name__)


class GlossaryApplier:
    """Pre-compiled glossary replacement engine."""

    def __init__(
        self,
        terms: list[tuple[re.Pattern, str]],
        raw: list[tuple[str, str, str]] | None = None,
    ):
        self._terms = terms
        # (te_term, en_term, category) — exposed for prompt-injection selection.
        self.terms_raw: list[tuple[str, str, str]] = raw or []

    @classmethod
    async def from_db(cls, session) -> GlossaryApplier:
        rows = await session.execute(
            GlossaryTerm.__table__.select().where(GlossaryTerm.__table__.c.en_term.isnot(None))
        )
        terms: list[tuple[re.Pattern, str]] = []
        raw: list[tuple[str, str, str]] = []
        for row in rows:
            te_term = row.te_term.strip()
            en_term = (row.en_term or "").strip()
            if te_term and en_term:
                try:
                    pattern = re.compile(re.escape(te_term), re.IGNORECASE)
                except re.error:
                    logger.warning("Skipping invalid glossary regex: %r", te_term)
                    continue
                terms.append((pattern, en_term))
                raw.append((te_term, en_term, row.category or "general"))
        logger.info("GlossaryApplier loaded %d terms", len(terms))
        return cls(terms, raw)

    def apply(self, text: str) -> str:
        """Apply all glossary replacements to *text*."""
        if not text:
            return text
        result = text
        for pattern, replacement in self._terms:
            result = pattern.sub(replacement, result)
        return result
