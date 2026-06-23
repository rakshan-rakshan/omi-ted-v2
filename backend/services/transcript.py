"""
Transcript fetch service — pure I/O, no DB.

Priority order for fetching Telugu captions:
  1. youtube-transcript-api  (no cookies, fastest, works on cloud IPs)
  2. yt-dlp without cookies   (fallback, also works on Railway IPs)
  3. Clear error to caller if both fail or no Telugu captions exist.

Cookie file is optional (YTDLP_COOKIES_FILE env var) — ignored on Railway.

Cloud-deploy hardening:
  - YT_PROXY (or HTTPS_PROXY/HTTP_PROXY) env var routes youtube traffic
    through a rotating proxy (Webshare, Bright Data, etc). Recommended on
    Railway — Railway egress IPs occasionally hit YouTube 429/529.
  - Automatic retry with jittered exponential backoff for 429/503/529 + net.
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass, field
from functools import partial

import httpx
import yt_dlp

# Proxy: prefer YT_PROXY, fall back to HTTPS_PROXY/HTTP_PROXY.
_PROXY: str | None = (
    os.environ.get("YT_PROXY")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("HTTP_PROXY")
    or None
)

# Retry config for 429 / 503 / 529 / network failures
_MAX_RETRIES = int(os.environ.get("YT_MAX_RETRIES", "4"))
_BASE_BACKOFF = float(os.environ.get("YT_BASE_BACKOFF", "2.0"))  # seconds

_YDL_OPTS: dict = {
    "skip_download": True,
    "quiet": True,
    "no_warnings": True,
    "ignore_no_formats_error": True,
    "retries": _MAX_RETRIES,
    "fragment_retries": _MAX_RETRIES,
    "extractor_retries": _MAX_RETRIES,
    "socket_timeout": 30,
}


def _retryable(exc: Exception) -> bool:
    """True if we should retry this error."""
    msg = str(exc).lower()
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 425, 429, 500, 502, 503, 504, 529}
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    return any(s in msg for s in ("429", "503", "529", "timed out", "connection reset", "rate limit"))


async def _backoff_sleep(attempt: int) -> None:
    """Jittered exponential backoff between attempts."""
    delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1.0)
    await asyncio.sleep(min(delay, 30.0))


@dataclass
class SegmentData:
    segment_index: int
    start_time: float
    duration: float
    te_original: str
    en_auto: str | None = None


@dataclass
class VideoData:
    title: str | None
    channel: str | None
    duration_s: int | None
    segments: list[SegmentData] = field(default_factory=list)
    has_te: bool = False


# ---------------------------------------------------------------------------
# Sentence merger (unchanged — the smart chunker from session 11)
# ---------------------------------------------------------------------------

def merge_into_sentences(
    raw: list[dict],
    pause_threshold: float = 1.2,
    max_chars: int = 200,
) -> list[dict]:
    """
    Merge raw YouTube subtitle events (1-3 words each) into natural speech
    units — the way a speaker actually pauses between thoughts.
    """
    if not raw:
        return []

    SENTENCE_ENDERS = frozenset(".?!|")

    merged: list[dict] = []
    chunk_start: float = raw[0]["start_time"]
    chunk_text: str = raw[0]["text"]
    chunk_end: float = raw[0]["start_time"] + raw[0]["duration"]

    for evt in raw[1:]:
        gap = evt["start_time"] - chunk_end
        last_char = chunk_text.rstrip()[-1] if chunk_text.strip() else ""

        natural_pause = gap > pause_threshold
        ends_sentence = last_char in SENTENCE_ENDERS
        too_long = len(chunk_text) > max_chars

        if natural_pause or ends_sentence or too_long:
            merged.append({
                "start_time": chunk_start,
                "duration":   max(chunk_end - chunk_start, 0.1),
                "text":       chunk_text.strip(),
            })
            chunk_start = evt["start_time"]
            chunk_text  = evt["text"]
            chunk_end   = evt["start_time"] + evt["duration"]
        else:
            sep = " " if not chunk_text.endswith(" ") else ""
            chunk_text = chunk_text + sep + evt["text"].lstrip()
            chunk_end  = evt["start_time"] + evt["duration"]

    if chunk_text.strip():
        merged.append({
            "start_time": chunk_start,
            "duration":   max(chunk_end - chunk_start, 0.1),
            "text":       chunk_text.strip(),
        })

    return merged


# ---------------------------------------------------------------------------
# Strategy 1: youtube-transcript-api (no cookies, pure HTTP)
# ---------------------------------------------------------------------------

def _ytapi_fetch(youtube_id: str) -> tuple[list[dict], list[dict]] | None:
    """
    Try youtube-transcript-api. Returns (te_raw, en_raw) or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None  # library not installed

    try:
        ytt = YouTubeTranscriptApi()
        transcript_list = ytt.list(youtube_id)
    except Exception:
        return None

    def _normalize(raw) -> list[dict]:
        rows: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                rows.append({
                    "start_time": item["start"],
                    "duration": item.get("duration", 0),
                    "text": item["text"],
                })
            else:
                rows.append({
                    "start_time": item.start,
                    "duration": getattr(item, "duration", 0),
                    "text": item.text,
                })
        return rows

    # Fetch Telugu
    te_raw: list[dict] = []
    te_transcript = None
    try:
        te_transcript = transcript_list.find_transcript(["te"])
        raw = te_transcript.fetch()
        te_raw = _normalize(raw)
    except Exception:
        pass

    # Fetch English (optional). If no native English captions exist, ask
    # YouTube for its free Telugu -> English caption translation.
    en_raw: list[dict] = []
    try:
        en_transcript = transcript_list.find_transcript(["en"])
        raw = en_transcript.fetch()
    except Exception:
        try:
            raw = te_transcript.translate("en").fetch() if te_transcript else []
        except Exception:
            raw = []

    if raw:
        en_raw = _normalize(raw)

    return te_raw, en_raw


# ---------------------------------------------------------------------------
# Strategy 2: yt-dlp (no cookies required, Railway IPs work fine)
# ---------------------------------------------------------------------------

def _pick_json3(formats: list[dict]) -> str | None:
    for fmt in formats:
        if fmt.get("ext") == "json3":
            return fmt.get("url")
    return None


def _parse_json3(data: dict) -> list[dict]:
    segments: list[dict] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        segments.append({
            "start_time": event.get("tStartMs", 0) / 1000.0,
            "duration":   event.get("dDurationMs", 0) / 1000.0,
            "text":       text,
        })
    return segments


def _load_cookies(cookies_file: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    try:
        with open(cookies_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
    except Exception:
        pass
    return cookies


async def _download_subtitle(url: str, cookies_file: str | None = None, required: bool = True) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.youtube.com/",
    }
    cookies = _load_cookies(cookies_file) if cookies_file else {}

    client_kwargs: dict = {
        "timeout": 30,
        "follow_redirects": True,
        "headers": headers,
        "cookies": cookies,
    }
    if _PROXY:
        # httpx >= 0.28 uses 'proxy' (singular)
        client_kwargs["proxy"] = _PROXY

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            return _parse_json3(resp.json())
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES and _retryable(exc):
                await _backoff_sleep(attempt)
                continue
            break
    if required and last_exc is not None:
        raise last_exc
    return []


def _ydl_extract(youtube_id: str, cookies_file: str | None) -> dict:
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    opts = {**_YDL_OPTS}
    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


async def _ytdlp_fetch(youtube_id: str) -> tuple[str | None, str | None, dict]:
    """
    Returns (te_url, en_url, info_dict) via yt-dlp.
    cookies_file is used if YTDLP_COOKIES_FILE is set, otherwise no cookies.
    Retries with backoff on rate-limit / network errors.
    """
    cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip() or None
    loop = asyncio.get_running_loop()

    info: dict = {}
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            info = await loop.run_in_executor(
                None, partial(_ydl_extract, youtube_id, cookies_file)
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES and _retryable(exc):
                await _backoff_sleep(attempt)
                continue
            raise

    if not info:
        return None, None, {}

    auto_caps   = info.get("automatic_captions") or {}
    manual_subs = info.get("subtitles") or {}

    te_formats = auto_caps.get("te") or manual_subs.get("te") or []
    en_formats = auto_caps.get("en") or manual_subs.get("en") or []

    te_url = _pick_json3(te_formats) if te_formats else None
    en_url = _pick_json3(en_formats) if en_formats else None
    return te_url, en_url, info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_video(youtube_id: str, skip_songs: bool = False, skip_en: bool = False) -> VideoData:
    """
    Fetch metadata + Telugu (+ English if available) auto-captions.

    Raises ValueError with a clear message if:
      - Video has no Telugu captions
      - Both fetch strategies fail
      - skip_songs is True and video has 3 or fewer segments (likely a song)
    """
    # ── Strategy 1: youtube-transcript-api ───────────────────────────────
    loop = asyncio.get_running_loop()
    ytapi_result = await loop.run_in_executor(None, _ytapi_fetch, youtube_id)

    title: str | None = None
    channel: str | None = None
    duration_s: int | None = None
    te_raw: list[dict] = []
    en_raw: list[dict] = []

    if ytapi_result is not None:
        te_raw, en_raw = ytapi_result

    # ── Strategy 2: yt-dlp (also gets metadata) ───────────────────────────
    if not te_raw or not en_raw:
        try:
            te_url, en_url, info = await _ytdlp_fetch(youtube_id)
            title      = info.get("title") or title
            channel    = info.get("uploader") or info.get("channel") or channel
            duration_s = info.get("duration") or duration_s

            cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip() or None
            if not te_raw and te_url:
                te_raw = await _download_subtitle(te_url, cookies_file, required=True)
            if not en_raw and en_url and not skip_en:
                en_raw = await _download_subtitle(en_url, cookies_file, required=False)
        except Exception as exc:
            if not te_raw:
                raise ValueError(
                    f"Could not fetch captions for '{youtube_id}'. "
                    f"Both youtube-transcript-api and yt-dlp failed: {exc}"
                ) from exc

    if not te_raw:
        raise ValueError(
            f"No Telugu captions found for video '{youtube_id}'. "
            "Check that the video has Telugu auto-captions enabled on YouTube."
        )

    # ── Merge bubble captions into sentences ──────────────────────────────
    te_chunks = merge_into_sentences(te_raw, pause_threshold=1.2, max_chars=200)
    en_chunks = merge_into_sentences(en_raw, pause_threshold=1.2, max_chars=300) if en_raw else []

    en_lookup: list[tuple[float, str]] = [(c["start_time"], c["text"]) for c in en_chunks]

    def _find_en(te_start: float) -> str | None:
        if not en_lookup:
            return None
        best_text, best_dist = None, float("inf")
        for en_start, en_text in en_lookup:
            dist = abs(en_start - te_start)
            if dist < best_dist:
                best_dist, best_text = dist, en_text
        return best_text if best_dist <= 2.0 else None

    segments = [
        SegmentData(
            segment_index=idx,
            start_time=chunk["start_time"],
            duration=chunk["duration"],
            te_original=chunk["text"],
            en_auto=_find_en(chunk["start_time"]),
        )
        for idx, chunk in enumerate(te_chunks)
    ]

    if skip_songs and len(segments) <= 3:
        raise ValueError(
            f"Video '{youtube_id}' appears to be a song ({len(segments)} segments). Skipped."
        )

    return VideoData(
        title=title,
        channel=channel,
        duration_s=duration_s,
        segments=segments,
        has_te=True,
    )
