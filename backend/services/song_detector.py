"""
Detect song/prayer segments by heuristics.
Called during ingest to set segment.content_type.
"""
from dataclasses import dataclass
from typing import List

# Telugu prayer/song indicators — add more as found in real data
_PRAYER_OPENERS = [
    "ప్రార్థన", "దేవా", "ప్రభూ", "దేవుడా", "తండ్రీ", "యేసయ్యా",
    "స్తుతి", "కృతజ్ఞత", "ప్రియ",
]
_SONG_MARKERS = ["♫", "♪", "సంగీతం", "పాట", "గానం"]


def classify_segment(text: str, word_count: int, prev_type: str | None = None) -> str:
    """Return 'song', 'prayer', or 'sermon' based on text heuristics."""
    if not text or not text.strip():
        return "unknown"
    text_lower = text.strip().lower()
    words = text_lower.split()
    
    # Song: very short segments that repeat patterns (handled by consecutive check)
    if any(m in text_lower for m in _SONG_MARKERS):
        return "song"
    
    # Prayer: starts with prayer opener
    first_word = words[0] if words else ""
    if first_word in _PRAYER_OPENERS:
        return "prayer"
    
    return "sermon"


def detect_song_run(types: List[str], min_run: int = 3) -> List[str]:
    """
    If N consecutive segments are 'song', keep them. Short isolated
    'song' segments that are actually just short sermon phrases get
    reclassified as 'sermon'.
    """
    n = len(types)
    result = types[:]
    for i in range(n):
        if types[i] == "song":
            left = sum(1 for j in range(max(0, i - min_run + 1), i) if types[j] == "song")
            right = sum(1 for j in range(i + 1, min(n, i + min_run)) if types[j] == "song")
            if left + right < min_run - 1:
                result[i] = "sermon"
    return result


def classify_segments(segments_data: list) -> list:
    """
    Batch classify all segments for a video.
    segments_data is a list of dicts with keys: 'index', 'text'
    Returns list of content_type strings in same order.
    """
    types = []
    prev = None
    for seg in segments_data:
        wc = len(seg.get("text", "").split())
        t = classify_segment(seg.get("text", ""), wc, prev)
        types.append(t)
        prev = t
    return detect_song_run(types)
