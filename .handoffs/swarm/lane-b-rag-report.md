# Lane B — RAG `/ask/advanced` Live Probe Report

**Branch**: `codex/youtube-auto-translate-fallback` @ `8d55a8e`
**Date**: 2026-06-23
**Runner**: Claude Sonnet 4.6 (Lane B fork)

---

## Setup state

- Backend: started cleanly on `127.0.0.1:3001` via `backend\venv\Scripts\python.exe -m uvicorn main:app`
- DB: SQLite `backend/dev.db` (~17 MB)
- Python: 3.12.10 inside venv
- Health endpoint `/health` → `{"status":"ok","service":"omi-ted-v2"}`

### `/api/v1/models/health` (after sending empty `X-Admin-Key`)
```json
{
  "ollama":     {"available": true,  "url": "http://localhost:11434"},
  "huggingface":{"available": false, "has_key": false},
  "openrouter": {"available": true,  "has_key": true},
  "reranker":   {"available": true, "model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "type": "local-sentence-transformers"}
}
```

### `/api/v1/stats`
- total_segments: **28,564**
- gold: 1 · silver: 606 · empty: 27,957 — translation coverage **~2.1%**

### Raw row counts (SELECT COUNT(*))
| table        | rows  |
|--------------|-------|
| videos       | 153   |
| segments     | 28564 |
| messages     | **0** |
| chunks       | **0** |
| jobs         | 71    |
| glossary     | 0     |
| query_logs   | 8     |

---

## Per-query results

### `/api/v1/search` (single hybrid search, top_k=5)
| query | status | latency_ms | results_n | notes |
|---|---|---|---|---|
| "What does the Bible say about God's love?" | 200 | 12625 | 0 | cold start (reranker model load) |
| "దేవుని ప్రేమ గురించి బైబిల్ ఏమి చెబుతుంది?" | 200 | 281 | 0 | warm |
| "Who is Jesus Christ?" | 200 | 219 | 0 | warm |

### `/api/v1/ask` (single-step RAG)
| query | status | latency_ms | sources_n | answer_preview |
|---|---|---|---|---|
| EN "God's love" | 200 | 406 | 0 | "I don't have enough context to answer that question." |
| TE "దేవుని ప్రేమ" | 200 | 188 | 0 | same fallback |
| EN "Jesus Christ" | 200 | 187 | 0 | same fallback |

### `/api/v1/ask/advanced` (multi-step RAG, all 5 queries)
| query | status | latency_ms | sources_n | error |
|---|---|---|---|---|
| EN "God's love" | — | 180031 | — | `ReadTimeout('timed out')` |
| TE "దేవుని ప్రేమ" | — | 180235 | — | `ReadTimeout('timed out')` |
| EN "Jesus Christ" | — | 181484 | — | `ReadTimeout('timed out')` |
| TE "ప్రార్థన ఎలా చేయాలి?" | — | 180094 | — | `ReadTimeout('timed out')` |
| EN "salvation through faith" | — | 184968 | — | `ReadTimeout('timed out')` |

**Client-side timeout was 180s — server never produced a response on any /ask/advanced call.**

---

## Bugs / issues (severity ordered)

### P0 — `/ask/advanced` hangs on every query (server-side, not client)
- **Symptom**: 5/5 calls timed out at 180s
- **Root cause**: `backend/services/rag_pipeline.py:138-144` fans out parallel `hybrid_search()` calls via `asyncio.gather()` reusing **a single `AsyncSession`**. SQLAlchemy async sessions explicitly forbid concurrent operations — each task raises:
  > `This session is provisioning a new connection; concurrent operations are not permitted (https://sqlalche.me/e/20/isce)`
- The uvicorn err log shows hundreds of these per query.
- The `return_exceptions=True` on gather means the function *should* still finish quickly with `valid_results=[]` and return the "no context" fallback — but it doesn't. Likely cause of the 180s hang: the per-task `Search task raised` logging is happening in the embedding fallback chain (Ollama → HF → OpenRouter), and one provider's connect-with-retries is blocking. Worth confirming with a stack dump.
- **Fix sketch**: Either (a) give each parallel search its own short-lived session via `async_sessionmaker`, or (b) sequentialize the search loop. Option (a) is faster but a bigger change.

### P0 — RAG corpus is empty (chunks=0, messages=0)
- 28,564 raw segments exist; **none have been chunked into the `chunks` table** that hybrid_search queries.
- Search returns `[]` on every query *not because search is broken, but because there is nothing to search.*
- The pipeline assumes `segments → messages → chunks (with embeddings)` has been run. It hasn't.
- **Fix**: locate/run the chunking + embedding pass (`backend/scripts/reembed_all.py` is a candidate). Without this the entire `/search` + `/ask` surface is non-functional regardless of Ollama state.

### P1 — Embedding provider chain reports failure despite Ollama "available"
- `/models/health` says Ollama is reachable, but the uvicorn log emits `All embedding providers failed for text length=42` repeatedly.
- Likely: Ollama is up but the `bge-m3` embedding model isn't pulled (`ollama pull bge-m3`). The health check probes the HTTP endpoint, not the model.
- **Fix**: add a model-presence check to `model_router.health_check()` (e.g. `GET /api/tags` and verify `embedding_model` is in the list).

### P1 — `_keyword_only` fallback filters by `language_code` of the *query*, not the corpus
- `hybrid_search.py:62`: `WHERE c.chunk_text LIKE :q AND c.language_code = :lang` where `lang` is detected from the **query text**.
- Corpus is Telugu; English queries get `lang='en'` and match nothing even if the corpus were populated.
- **Fix**: drop the `language_code` filter from `_keyword_only` (or invert it — query in EN should still match TE chunks if RAG is meant to be cross-lingual).

### P2 — `/api/v1/models/health` accepts empty `X-Admin-Key`
- `routers/search.py:222`: `if x_admin_key != getattr(settings, "admin_key", "")` — `settings.admin_key` is unset, so empty-string header matches empty-string default and authentication trivially passes.
- **Fix**: require both sides to be non-empty.

### P2 — Old SOCKS-proxy errors still pollute video rows
- `videos_head` shows ~10 recent ingest errors all of the form `Using SOCKS proxy, but the 'socksio' package is not installed.`
- Session-17 handoff says proxy was removed from yt-dlp, but `httpx` is still trying SOCKS for the caption download path.
- **Fix**: either `pip install httpx[socks]` or strip the SOCKS proxy from the httpx client used by the transcript service.

---

## Findings

1. **The new RAG v3 pipeline is structurally implemented and the new endpoints are wired (`/ask/advanced`, `/models/health`, `/models/reranker`), but end-to-end it does not function on this DB.** Two hard blockers: empty chunks table and the async-session concurrency bug.
2. **Reranker loads successfully** — `cross-encoder/ms-marco-MiniLM-L-6-v2` is downloaded and available. First search took 12.6s (cold-start model load); warm calls are ~200ms.
3. **`/ask` gracefully degrades** when search returns zero (replies "I don't have enough context"). `/ask/advanced` does NOT degrade gracefully — it hangs for 180s+.
4. **Latency profile**: `/ask` cold ~400ms, warm ~190ms. `/ask/advanced` cannot be measured until the concurrency bug is fixed.
5. **Telugu corpus is only 2.1% translated** (607 of 28,564 segments). Even with chunking + embeddings fixed, retrieval quality on EN questions will be poor until human translation coverage rises.

---

## Recommendations (concrete next steps)

1. **Fix the async-session concurrency bug first** — `rag_pipeline.py:138-144`. Smallest change: pass a `sessionmaker` instead of a `session` and create one short-lived session per parallel task. Without this, `/ask/advanced` is unusable.
2. **Run the chunking + embedding backfill** — `backend/scripts/reembed_all.py` looks like the right script; verify it populates `messages` + `chunks` from `segments`. Without this, nothing works.
3. **Pull `bge-m3` in Ollama** (`ollama pull bge-m3`) so embeddings actually succeed. Verify with `model_router.embed("test")` returning a non-None vector.
4. **Drop language_code gate in `_keyword_only`** so cross-lingual fallback works.
5. **Add a 30s server-side timeout to `multi_step_rag`** so a hung embedder doesn't strand a request for 3 minutes.
6. **Add a `models/health` model-presence probe** (not just reachability).
7. **After fixes, re-run this probe** — same 5 queries. Expected: latency <5s per query, sources_n > 0 on Telugu queries, graceful "no context" on truly unanswerable ones.

---

## Files referenced (no edits made)
- `backend/services/rag_pipeline.py` (lines 120–180) — concurrency bug
- `backend/services/hybrid_search.py` (lines 33–87) — language_code filter, missing chunks
- `backend/routers/search.py` (lines 216–225) — empty-admin-key bypass
- `backend/scripts/reembed_all.py` — likely backfill entry point (not run)
