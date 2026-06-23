"""
Context builder — priority-based context truncation for RAG synthesis.

Assigns priority scores to chunks based on translation quality tier,
then truncates lowest-priority items to fit within a token budget.

Priority weights:
    gold (quality_score >= 4) = 100
    silver (quality_score 2-3) = 75
    draft (quality_score 1 or None) = 60
    default = 60

Usage:
    from services.context_builder import build_context
    context = build_context(search_results, max_tokens=3000)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Priority levels by translation quality tier
TIER_PRIORITY = {
    "gold": 100,
    "silver": 75,
    "draft": 60,
}

DEFAULT_PRIORITY = 60


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for Telugu."""
    te_chars = sum(1 for c in text if "\u0C00" <= c <= "\u0C7F")
    en_chars = len(text) - te_chars
    return int(te_chars / 2 + en_chars / 4)


def _get_priority(chunk: dict | object) -> int:
    """Get priority score for a chunk based on its quality tier."""
    if isinstance(chunk, dict):
        quality = chunk.get("quality_score") or chunk.get("score")
    else:
        quality = getattr(chunk, "quality_score", None)

    if quality is None:
        return DEFAULT_PRIORITY
    if isinstance(quality, str):
        return TIER_PRIORITY.get(quality, DEFAULT_PRIORITY)

    # Numeric quality_score (1-5)
    if quality >= 4:
        return TIER_PRIORITY["gold"]
    if quality >= 2:
        return TIER_PRIORITY["silver"]
    return TIER_PRIORITY["draft"]


@dataclass
class ContextItem:
    text: str
    priority: int
    token_count: int
    chunk_id: int | None = None


def build_context(
    chunks: list,
    max_tokens: int = 3000,
    text_attr: str = "chunk_text",
    id_attr: str = "chunk_id",
) -> str:
    """
    Build a prioritized context string within a token budget.

    Args:
        chunks: List of SearchResult or dict objects with chunk_text and optional quality_score.
        max_tokens: Maximum token budget for the context.
        text_attr: Attribute name for the chunk text.
        id_attr: Attribute name for the chunk ID.

    Returns:
        Formatted context string like: "[1] chunk text [2] chunk text ..."
    """
    if not chunks:
        return ""

    items: list[ContextItem] = []
    for c in chunks:
        text = getattr(c, text_attr, None) if hasattr(c, text_attr) else c.get(text_attr, "") if isinstance(c, dict) else ""
        if not text:
            continue
        chunk_id = getattr(c, id_attr, None) if hasattr(c, id_attr) else c.get(id_attr) if isinstance(c, dict) else None
        priority = _get_priority(c)
        token_count = _estimate_tokens(text)
        items.append(ContextItem(text=text, priority=priority, token_count=token_count, chunk_id=chunk_id))

    # Sort by priority descending
    items.sort(key=lambda x: x.priority, reverse=True)

    # Truncate to fit budget
    total_tokens = 0
    selected: list[ContextItem] = []
    for item in items:
        if total_tokens + item.token_count > max_tokens:
            break
        selected.append(item)
        total_tokens += item.token_count

    # Format as numbered context
    parts = []
    for i, item in enumerate(selected, 1):
        parts.append(f"[{i}] {item.text}")

    result = "\n\n".join(parts)
    logger.debug(
        "Built context: %d/%d chunks, %d/%d tokens",
        len(selected),
        len(items),
        total_tokens,
        max_tokens,
    )
    return result


def build_context_from_dicts(
    chunks: list[dict],
    max_tokens: int = 3000,
) -> str:
    """Convenience wrapper for list[dict] input."""
    return build_context(chunks, max_tokens, text_attr="chunk_text", id_attr="chunk_id")
