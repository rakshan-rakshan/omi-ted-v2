"""
Shared helpers for throttle probes A/B/C/D.
Each probe overrides _build_opts() to swap a single strategy variable.

NOT for production use. Probes hit YouTube directly and write a JSON report
to stdout. Read with `python throttle_probe_X.py > report_X.json`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator

import httpx
import yt_dlp

# 5 unseen IDs picked by _pick_ids.py against current dev.db
PROBE_IDS = [
    "FhU_C5HFjjc",
    "jn6eLn6ERYY",
    "srw9klHw3d0",
    "fSbkKpnXQBo",
    "N4AXUiFd0CI",
]


def base_ydl_opts() -> dict:
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignore_no_formats_error": True,
        "socket_timeout": 30,
        "retries": 1,
        "fragment_retries": 1,
        "extractor_retries": 1,
    }


def pick_json3(formats: list[dict]) -> str | None:
    for fmt in formats:
        if fmt.get("ext") == "json3":
            return fmt.get("url")
    return None


def classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg:
        return "429"
    if "ipblocked" in msg or "ip is blocked" in msg or "your ip" in msg:
        return "ip_block"
    if "timed out" in msg or "timeout" in msg:
        return "timeout"
    if "no captions" in msg or "no subtitles" in msg:
        return "no_captions"
    if "private" in msg:
        return "private"
    if "unavailable" in msg:
        return "unavailable"
    return f"other:{type(exc).__name__}"


def run_probe(
    strategy_name: str,
    ydl_opts: dict,
    *,
    json3_proxy: str | None = None,
    json3_cookies_file: str | None = None,
    between_calls_sleep: float = 0.0,
) -> dict:
    """
    Run the same 5 IDs through one strategy. Captures per-ID: phase reached,
    status (success/429/timeout/other), elapsed_ms. Returns aggregate report.
    """
    results: list[dict] = []
    start = time.time()

    for idx, vid in enumerate(PROBE_IDS):
        if idx > 0 and between_calls_sleep:
            time.sleep(between_calls_sleep)

        per: dict = {"video_id": vid, "phase": "extract", "ok": False}
        t0 = time.time()

        # Phase 1: yt-dlp extract_info (where most 429s happen)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={vid}",
                    download=False,
                ) or {}
        except Exception as exc:
            per["status"] = classify_error(exc)
            per["error"] = str(exc)[:200]
            per["elapsed_ms"] = int((time.time() - t0) * 1000)
            results.append(per)
            continue

        auto_caps = info.get("automatic_captions") or {}
        manual_subs = info.get("subtitles") or {}
        te_formats = auto_caps.get("te") or manual_subs.get("te") or []
        te_url = pick_json3(te_formats) if te_formats else None

        per["te_formats_found"] = len(te_formats)
        per["te_url_found"] = bool(te_url)
        per["title"] = info.get("title")
        per["duration_s"] = info.get("duration")

        if not te_url:
            per["status"] = "no_te_url"
            per["elapsed_ms"] = int((time.time() - t0) * 1000)
            results.append(per)
            continue

        # Phase 2: download the actual json3 subtitle
        per["phase"] = "subtitle"
        try:
            client_kwargs: dict = {
                "timeout": 30,
                "follow_redirects": True,
                "headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.youtube.com/",
                },
            }
            if json3_proxy:
                client_kwargs["proxy"] = json3_proxy

            with httpx.Client(**client_kwargs) as client:
                resp = client.get(te_url)
                resp.raise_for_status()
                data = resp.json()
                segs = data.get("events", []) or []
                per["segments_returned"] = len(segs)
                per["ok"] = bool(segs)
                per["status"] = "success" if segs else "empty_subtitle"
        except Exception as exc:
            per["status"] = classify_error(exc)
            per["error"] = str(exc)[:200]

        per["elapsed_ms"] = int((time.time() - t0) * 1000)
        results.append(per)

    total_ms = int((time.time() - start) * 1000)
    successes = sum(1 for r in results if r["ok"])
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "strategy": strategy_name,
        "total_ids": len(PROBE_IDS),
        "successes": successes,
        "status_counts": counts,
        "total_elapsed_s": round(total_ms / 1000, 1),
        "per_video": results,
    }
    return report
