from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ChunkResult:
    message_id: int
    chunk_index: int
    chunk_text: str
    segment_ids: list[int] = field(default_factory=list)
    language_code: str = "en"
    token_count: int = 0
    start_time: float = 0.0  # earliest source-segment start (seconds)


def estimate_tokens(text: str) -> int:
    return len(text.split())


async def chunk_segments(
    message_id: int,
    segments: list[dict],
    *,
    target_words: int = 250,
    min_words: int = 80,
    max_words: int = 500,
) -> list[ChunkResult]:
    """
    Merge consecutive segments into semantic chunks.
    
    segments: list of dicts with keys: id, text (English), segment_index
    Returns: list of ChunkResult
    
    Algorithm:
    1. Start accumulating from first segment
    2. If accumulated text >= target_words, check if next segment starts with 
       a sentence boundary (capital letter). If yes, flush chunk here.
    3. Never exceed max_words - force split at nearest sentence boundary.
    4. Never go below min_words - keep merging.
    """
    if not segments:
        return []
    
    chunks: list[ChunkResult] = []
    current_text_parts: list[str] = []
    current_seg_ids: list[int] = []
    current_start_times: list[float] = []
    current_words = 0

    def flush():
        nonlocal current_text_parts, current_seg_ids, current_start_times, current_words
        if not current_text_parts:
            return
        text = " ".join(current_text_parts)
        tokens = estimate_tokens(text)
        chunks.append(ChunkResult(
            message_id=message_id,
            chunk_index=len(chunks),
            chunk_text=text,
            segment_ids=current_seg_ids,
            token_count=tokens,
            start_time=min(current_start_times) if current_start_times else 0.0,
        ))
        current_text_parts = []
        current_seg_ids = []
        current_start_times = []
        current_words = 0

    for seg in segments:
        seg_text = (seg.get("text") or "").strip()
        if not seg_text:
            continue
        seg_words = estimate_tokens(seg_text)

        if current_words + seg_words > max_words and current_words >= min_words:
            flush()

        if current_words >= target_words and current_words >= min_words:
            if seg_text and seg_text[0].isupper():
                flush()

        current_text_parts.append(seg_text)
        current_seg_ids.append(seg.get("id", 0))
        current_start_times.append(float(seg.get("start_time", 0.0) or 0.0))
        current_words += seg_words

    flush()
    
    return chunks
