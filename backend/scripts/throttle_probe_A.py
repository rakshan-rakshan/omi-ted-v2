"""
Probe A — baseline.

Current production fetch path: no cookies, no proxy, default yt-dlp opts.
Mirrors transcript.py with YT_PROXY/YTDLP_COOKIES_FILE unset.

Run: `python backend/scripts/throttle_probe_A.py`
"""
from __future__ import annotations

import json
import os
import sys

# Ensure baseline: clear any inherited proxy env
for k in ("HTTP_PROXY", "HTTPS_PROXY", "YT_PROXY", "YTDLP_COOKIES_FILE"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from throttle_probe_common import base_ydl_opts, run_probe

if __name__ == "__main__":
    report = run_probe(
        "A_baseline",
        ydl_opts=base_ydl_opts(),
        json3_proxy=None,
        between_calls_sleep=2.0,  # gentle default
    )
    print(json.dumps(report, indent=2))
