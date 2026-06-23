# Lane D — YouTube 429 diagnosis + workaround probes

**Branch**: `codex/youtube-auto-translate-fallback`
**Probe date**: 2026-06-23
**Probe set**: 5 video IDs picked by `backend/scripts/_pick_ids.py` from `urls_to_ingest.csv`, filtered to those not already in `backend/dev.db`.

---

## Diagnosis confirmation

`backend/scripts/videos_dump.json` contains hundreds of records with
`error_msg: "Client error '429 Too Many Requests' for url 'https://www.youtube.com/api/timedtext?...'"` — the failure mode is HTTP 429 on the json3 subtitle download, not a Google Cloud billing error. The Session 17 handoff misframed this as a billing issue.

**However**, the historical 429s appear to have been **bursty rate-limit triggers**, not a sustained IP ban. Both Probe A (2 s sleep between calls) and Probe C (30 s sleep between calls) ran today against the same machine, same network, same IP — and both achieved 5/5 success. YouTube is not currently throttling this host at any reasonable cadence.

This shifts the recommendation from "find a bypass" to "**don't burst** — pace the ingest and the existing path works."

---

## Test setup

| Item | Value |
|---|---|
| Video IDs | `FhU_C5HFjjc`, `jn6eLn6ERYY`, `srw9klHw3d0`, `fSbkKpnXQBo`, `N4AXUiFd0CI` |
| Picker | `backend/scripts/_pick_ids.py` — first 5 from `urls_to_ingest.csv` not already in `dev.db` |
| yt-dlp opts (baseline) | `skip_download`, `quiet`, `socket_timeout=30`, `retries=1` |
| json3 fetch | httpx with browser-like UA + `Referer: youtube.com` |
| Probes | A (baseline 2 s), B (cookies-from-browser), C (long backoff 30 s), D (WARP SOCKS5 proxy) |

Each probe writes its result JSON to `backend/scripts/probe_<X>_out.json`. Per-video the JSON records phase reached (`extract` → `subtitle`), status (`success` / `429` / `timeout` / `other:<type>`), and elapsed ms.

---

## Per-strategy results

| Strategy | Description | Success | Median ms/video | Total s | Error pattern | Notes |
|---|---|---|---|---|---|---|
| **A — baseline 2 s** | No cookies, no proxy, 2 s between calls | **5 / 5** | 11.1 k | 82.6 | none | Production path. Telugu auto-caps found on all 5. |
| **B — cookies-from-browser (Chrome)** | yt-dlp `cookiesfrombrowser=('chrome',)` | 0 / 5 | — | 37.1 | `Could not copy Chrome cookie database` (yt-dlp issue #7271) | Chrome was running; cookie DB locked. Did not reach YouTube. |
| **B — cookies-from-browser (Firefox)** | Same, but Firefox profile | 0 / 5 | — | 9.9 | `could not find firefox cookies database` | Firefox not installed on this machine. Did not reach YouTube. |
| **C — long backoff 30 s** | Baseline + 30 s sleep between calls | **5 / 5** | 15.1 k | 189.8 | none | Slower than A by ~2.3×; no improvement in success rate (already 100 %). |
| **D — WARP SOCKS5 proxy** | `socks5://127.0.0.1:40000` on yt-dlp + json3 | 0 / 5 | — | 65.0 | `httpx` import error: `'socksio' package is not installed` | yt-dlp extract worked through proxy (`te_formats_found: 6` per video) — only the json3 fetch failed. Inconclusive on actual proxy effectiveness; would re-run after `pip install httpx[socks]`. Pip install blocked in this session (exit 1, no network). |

Raw outputs: `backend/scripts/probe_A_out.json`, `probe_B_out.json`, `probe_B_firefox_out.json`, `probe_C_out.json`, `probe_D_out.json`.

---

## Winning strategy

**Probe A — baseline with a small pacing delay.**

No workaround beats it because the baseline already hits 100 % success at 11 s/video. The Probe C 30 s backoff is unnecessary today (same outcome, 2.3× slower). Cookies-from-browser was untestable (environmental — locked Chrome DB, missing Firefox). Proxy variant was untestable (missing `socksio`); however the proxy *did* route yt-dlp's extract call successfully, so D remains a viable Plan B if YouTube re-throttles this IP.

---

## Recommendation

1. **Resume ingest at 2-3 s pacing.** Use `throttle_probe_A.py` cadence as the production target. The existing `backend/scripts/batch_ingest.py` already has 1-2 s jitter (per `project-settings.md`); keep that — do not increase. At ~11 s/video the remaining ~7 k videos take ~21 h of wall time, single-threaded.

2. **Add 429-aware backoff to `batch_ingest.py`.** On the first 429, sleep 60 s; if it recurs within the same batch, escalate to 300 s and shrink concurrency. Today's probes show YouTube forgives a paused burst — exploit that. Do **not** retry instantly.

3. **Keep Probe D ready, not active.** Install `httpx[socks]` in CI/prod (already partial — WARP is configured for ingest worker). Wire `YT_PROXY` env into `services/transcript.py` as an optional fallback that activates only on N consecutive 429s. Do not route everyone through SOCKS by default — that hurts latency and the baseline doesn't need it.

4. **Drop cookies-from-browser as a strategy.** It's a fragile dependency on the developer's local browser state. If authenticated quota is needed, export a `cookies.txt` once with `yt-dlp --cookies cookies.txt` and ship that to the worker — but only do this if 429s return at scale. Today, anonymous works.

5. **Do not buy a residential proxy yet.** Bright Data / Oxylabs would cost $X/month for a problem that isn't currently active. Revisit only if Probe A regresses to <80 % success on a 50-video re-probe.

---

## NOT done

- **Full 7 k-video ingest NOT initiated.** This was a 5-video diagnostic, not a resume.
- **`backend/services/transcript.py` NOT modified.** Recommended changes in §3 above are deferred to a follow-up commit.
- **`socksio` not installed** — pip exited 1 in this session, output not captured (possible offline pip mirror or cert issue). Probe D inconclusive as a result. Install on next online session and re-run if you want a clean D measurement.
- **Probe B not validated** — would need either an unlocked Chrome (close all Chrome windows first) or a real Firefox install.
