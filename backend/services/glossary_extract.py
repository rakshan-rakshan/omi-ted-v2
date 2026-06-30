"""
Extract candidate glossary terms from one video's text.

Two sources, combined per the requested `methods`:
- heuristic: scripture-reference book names (proper nouns, with English meaning) +
  frequent Telugu words (stopword-filtered; meanings left blank for the user to fill).
- llm: a single OpenRouter call returning {te_term, meanings[], category} candidates.

Returns a deduped, ranked candidate list for the UI to review and bulk-save. Nothing
is persisted here — saving goes through POST /api/v1/glossary/bulk.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter

from config import settings
from services.model_router import model_router
from services.scripture_refs import TELUGU_BOOKS

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"theology", "name", "place", "general"}

# Common Telugu function words to exclude from frequency candidates.
_STOPWORDS = {
    "మరియు", "ఈ", "ఆ", "నేను", "మీరు", "అది", "ఇది", "అతను", "ఆయన", "మనం",
    "మన", "నా", "మీ", "ఒక", "కూడా", "అని", "అన్ని", "ఉంది", "ఉన్నాడు", "ఉన్నది",
    "గురించి", "కోసం", "నుండి", "వరకు", "అయితే", "కానీ", "ఎందుకంటే", "ఎలా",
    "ఏమి", "ఏది", "ఎవరు", "ఎక్కడ", "ఎప్పుడు", "చాలా", "ఇప్పుడు", "అప్పుడు",
}

_TE_WORD = re.compile(r"[ఀ-౿]{3,}")


def _heuristic_candidates(te_text: str, max_terms: int = 25) -> list[dict]:
    cands: dict[str, dict] = {}

    # 1. Scripture book names actually cited (abbr followed by chapter:verse).
    for te_abbr, en_book in TELUGU_BOOKS.items():
        if re.search(re.escape(te_abbr) + r"\s*\d{1,3}\s*:", te_text):
            cands[te_abbr] = {
                "te_term": te_abbr, "meanings": [en_book],
                "category": "name", "source": "scripture",
            }

    # 2. Frequent Telugu words (meanings blank — user/LLM supplies).
    words = [w for w in _TE_WORD.findall(te_text) if w not in _STOPWORDS]
    freq = Counter(words)
    for word, count in freq.most_common(max_terms * 3):
        if count < 3:
            break
        if word in cands:
            continue
        cands[word] = {
            "te_term": word, "meanings": [],
            "category": "general", "source": "frequency", "count": count,
        }
        if len(cands) >= max_terms + len(cands):
            pass
    return list(cands.values())


def _parse_terms_json(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        data = json.loads(raw[start:end])
        terms = data.get("terms")
        return terms if isinstance(terms, list) else []
    except (json.JSONDecodeError, AttributeError):
        return []


async def _llm_candidates(te_text: str, en_text: str, max_terms: int = 30) -> list[dict]:
    sys_prompt = (
        "You build a glossary for translating Telugu Christian sermons into English. "
        "Extract the most important recurring terms: theological vocabulary, proper nouns "
        "(people, places, Bible books), and key concepts. For each, give the Telugu term, "
        "one or more English meanings (most accurate first), and a category from: "
        "theology, name, place, general. Preserve Biblical names exactly. "
        f"Return AT MOST {max_terms} terms as ONLY JSON: "
        '{"terms":[{"te_term":"...","meanings":["..."],"category":"theology"}]}'
    )
    user = f"Telugu text:\n{te_text[:6000]}\n\nEnglish reference:\n{en_text[:4000]}"
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]

    raw = await model_router._chat_openrouter(
        messages, settings.models.openrouter_model, max_tokens=2000
    )
    out: list[dict] = []
    for t in _parse_terms_json(raw):
        te = str(t.get("te_term", "")).strip()
        meanings = [str(m).strip() for m in (t.get("meanings") or []) if str(m).strip()]
        category = t.get("category", "general")
        if category not in VALID_CATEGORIES:
            category = "general"
        if te and meanings:
            out.append({"te_term": te, "meanings": meanings, "category": category, "source": "llm"})
    return out


def _merge(*lists: list[dict]) -> list[dict]:
    by_term: dict[str, dict] = {}
    for lst in lists:
        for c in lst:
            te = c["te_term"]
            if te in by_term:
                existing = by_term[te]
                for m in c.get("meanings", []):
                    if m not in existing["meanings"]:
                        existing["meanings"].append(m)
                if existing["category"] == "general" and c.get("category") != "general":
                    existing["category"] = c["category"]
                existing["sources"] = sorted(set(existing["sources"]) | {c.get("source", "")})
                existing["count"] = max(existing.get("count", 0), c.get("count", 0))
            else:
                by_term[te] = {
                    "te_term": te,
                    "meanings": list(c.get("meanings", [])),
                    "category": c.get("category", "general"),
                    "sources": [c.get("source", "")],
                    "count": c.get("count", 0),
                }
    return list(by_term.values())


async def extract_glossary(te_text: str, en_text: str, methods: set[str]) -> list[dict]:
    """Return ranked candidate terms. methods ⊆ {'llm','heuristic'}."""
    parts: list[list[dict]] = []
    if "heuristic" in methods:
        parts.append(_heuristic_candidates(te_text))
    if "llm" in methods:
        try:
            parts.append(await _llm_candidates(te_text, en_text))
        except Exception as exc:  # provider error — degrade to heuristic only
            logger.warning("LLM glossary extraction failed: %s", exc)
    merged = _merge(*parts)
    # Rank: terms that already have meanings first, then by source breadth, then frequency.
    merged.sort(
        key=lambda c: (bool(c["meanings"]), len(c["sources"]), c.get("count", 0)),
        reverse=True,
    )
    return merged
