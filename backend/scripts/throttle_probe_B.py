"""
Probe B — yt-dlp cookies-from-browser.

Authenticates via the user's logged-in Chrome (falls back to Firefox).
Anonymous YouTube hits are aggressively throttled; cookied requests share the
user's session quota, which is far more lenient.

Run: `python backend/scripts/throttle_probe_B.py`
"""
from __future__ import annotations

import json
import os
import sys

# Same env hygiene as Probe A
for k in ("HTTP_PROXY", "HTTPS_PROXY", "YT_PROXY", "YTDLP_COOKIES_FILE"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from throttle_probe_common import base_ydl_opts, run_probe


def make_opts() -> dict:
    opts = base_ydl_opts()
    # Try Chrome first; if that fails the script will re-run with Firefox.
    opts["cookiesfrombrowser"] = ("chrome",)
    return opts


if __name__ == "__main__":
    browser = os.environ.get("PROBE_BROWSER", "chrome")
    opts = base_ydl_opts()
    opts["cookiesfrombrowser"] = (browser,)
    try:
        report = run_probe(
            f"B_cookies_{browser}",
            ydl_opts=opts,
            json3_proxy=None,
            between_calls_sleep=2.0,
        )
        print(json.dumps(report, indent=2))
    except Exception as exc:
        # If browser cookies are locked / unreadable, return a structured error
        print(json.dumps({
            "strategy": f"B_cookies_{browser}",
            "fatal_error": str(exc)[:300],
            "hint": "Try PROBE_BROWSER=firefox or close Chrome and rerun.",
        }, indent=2))
        sys.exit(2)
