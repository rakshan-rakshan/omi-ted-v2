"""
Build a compact glossary "hint" for the translation prompt.

The post-hoc GlossaryApplier fixes residual Telugu in the English output; this
instead steers the model *before* it translates. We inject only the terms whose
Telugu form actually appears in the segment being translated, so the added prompt
is tiny (usually a handful of lines), and we prioritise names/places/theology.
"""
from __future__ import annotations

# Lower number = higher priority when capping.
_PRIORITY = {"name": 0, "place": 1, "theology": 2, "general": 3}


def select_glossary_for_text(
    text: str,
    terms: list[tuple[str, str, str]],
    cap: int = 40,
) -> list[tuple[str, str, str]]:
    """Return the (te_term, en_term, category) entries whose te_term occurs in *text*.

    Prioritised name > place > theology > general, then by longer Telugu term first
    (more specific), capped at *cap*.
    """
    if not text or not terms:
        return []
    matched = [(te, en, cat) for (te, en, cat) in terms if te and te in text]
    matched.sort(key=lambda t: (_PRIORITY.get(t[2], 3), -len(t[0])))
    return matched[:cap]


def format_hint(matched: list[tuple[str, str, str]]) -> str:
    """Render matched terms as a prompt suffix. Empty string when nothing matched."""
    if not matched:
        return ""
    lines = "\n".join(f"{te} = {en}" for te, en, _ in matched)
    return (
        "\n\nUse these canonical English translations for the following Telugu terms "
        "where they appear (keep Biblical names and places exact):\n" + lines
    )


def hint_for_text(text: str, terms: list[tuple[str, str, str]], cap: int = 40) -> str:
    """Convenience: select + format in one call."""
    return format_hint(select_glossary_for_text(text, terms, cap))
