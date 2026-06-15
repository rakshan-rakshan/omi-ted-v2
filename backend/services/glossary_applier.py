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

    def __init__(self, terms: list[tuple[re.Pattern, str]]):
        self._terms = terms

    @classmethod
    async def from_db(cls, session) -> GlossaryApplier:
        rows = await session.execute(
            GlossaryTerm.__table__.select().where(GlossaryTerm.__table__.c.en_term.isnot(None))
        )
        terms: list[tuple[re.Pattern, str]] = []
        for row in rows:
            te_term = row.te_term.strip()
            en_term = row.en_term.strip()
            if te_term and en_term:
                try:
                    pattern = re.compile(re.escape(te_term), re.IGNORECASE)
                    terms.append((pattern, en_term))
                except re.error:
                    logger.warning("Skipping invalid glossary regex: %r", te_term)
        logger.info("GlossaryApplier loaded %d terms", len(terms))
        return cls(terms)

    def apply(self, text: str) -> str:
        """Apply all glossary replacements to *text*."""
        if not text:
            return text
        result = text
        for pattern, replacement in self._terms:
            result = pattern.sub(replacement, result)
        return result
