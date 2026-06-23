"""
Probe C — long backoff baseline.

Same code path as A, but with 30s between calls (instead of 2s). Tests whether
YouTube's rate limit window resets quickly enough that a slow trickle of
unauthenticated requests can sustain progress. Cheap signal; doesn't prove
sustainability over hours.

Run: `python backend/scripts/throttle_probe_C.py`
"""
from __future__ import annotations

import json
import os
import sys

for k in ("HTTP_PROXY", "HTTPS_PROXY", "YT_PROXY", "YTDLP_COOKIES_FILE"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from throttle_probe_common import base_ydl_opts, run_probe

if __name__ == "__main__":
    report = run_probe(
        "C_long_backoff_30s",
        ydl_opts=base_ydl_opts(),
        json3_proxy=None,
        between_calls_sleep=30.0,
    )
    print(json.dumps(report, indent=2))
