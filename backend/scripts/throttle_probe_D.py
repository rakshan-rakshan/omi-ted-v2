"""
Probe D — WARP SOCKS5 proxy on ALL stages (yt-dlp extract + json3 fetch).

Session 17 fixed a misdiagnosis by removing the proxy from yt-dlp options
because caption *detection* failed. This probe tests whether the session
17 change can be reverted now that the underlying ingest flow is different:
yt-dlp uses YT_PROXY env via httpx-style URL.

Requires WARP/SOCKS5 listening on 127.0.0.1:40000.

Run: `python backend/scripts/throttle_probe_D.py`
"""
from __future__ import annotations

import json
import os
import sys

PROXY = "socks5://127.0.0.1:40000"

# Clear prior, then apply only YT_PROXY (transcript.py honors this name).
for k in ("HTTP_PROXY", "HTTPS_PROXY", "YT_PROXY", "YTDLP_COOKIES_FILE"):
    os.environ.pop(k, None)
os.environ["YT_PROXY"] = PROXY

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from throttle_probe_common import base_ydl_opts, run_probe


if __name__ == "__main__":
    opts = base_ydl_opts()
    opts["proxy"] = PROXY  # apply to yt-dlp directly too
    report = run_probe(
        "D_warp_socks5",
        ydl_opts=opts,
        json3_proxy=PROXY,
        between_calls_sleep=2.0,
    )
    print(json.dumps(report, indent=2))
