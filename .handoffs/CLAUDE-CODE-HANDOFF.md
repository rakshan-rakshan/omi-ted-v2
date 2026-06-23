# CLAUDE CODE HANDOFF — OMI-TED v2

*Written by opencode (mimo-v2.5 + deepseek) for Claude Code to pick up.*

---

## Who Built What

This codebase was built by **opencode** using two models:
- **mimo-v2.5-free** (opencode/mimo-v2.5-free) — architecture decisions, complex service design, RAG pipeline, multi-step orchestration
- **deepseek-v4-flash-free** (opencode/deepseek-v4-flash-free) — transcript proxy fixes, React state sync, batch scripting, frontend debugging

**Claude Code (Sonnet 4.6)** built the original scaffold (Session 0) — repo structure, `project-settings.md`, `CLAUDE.md`, migration template, and handoff infrastructure.

---

## Current State (as of 2026-06-23)

### What's Built and Working
| Module | Status | Notes |
|--------|--------|-------|
| M0 — Repo scaffold | DONE | Backend + frontend + Alembic + Docker |
| M1 — Transcript Ingest | DONE | yt-dlp (no proxy) + httpx download + SQLite/PG |
| M2 — DB + Migrations | DONE | 3 migrations, SQLite local / PG prod |
| M3 — Parallel Editor UI | DONE | 3-column table, inline edit, auto-save, review flags |
| M4 — JSONL Export | DONE | Filtered export by quality/reviewed/content_type |
| M5 — LLM Router | DONE | Sarvam + Google + OpenRouter + local adapters |
| M6 — Batch Import | DONE | Excel upload, background queue, rate-limited |
| RAG Search | DONE | Hybrid search (BM25 + embeddings), 3 vector backends |
| RAG Ask | DONE | Multi-step RAG pipeline: rewrite → parallel search → merge → rerank → context budget → synthesize |
| Eval System | DONE | Gold set scoring, RAGAS metrics |
| Documents Router | NEW (untracked) | Document management |
| Search UI Page | NEW (untracked) | Frontend search interface |
| Upload Page | NEW (untracked) | File upload interface |

### What's Not Done
- M7 — Fine-tune pipeline (Phase 2, needs 500+ reviewed segments)
- YouTube channel scan + bulk ingest (paused at 74/7,139 — Google Cloud billing issue)
- Production deployment (Railway + Vercel — deferred until local pipeline validated)
- Sentry + PostHog monitoring

### Uncommitted Work (30+ files)
There is significant uncommitted work in the repo — new RAG services, batch scripts, frontend pages, and a migration. **Do not delete these.** They represent sessions 16–17 of work.

**Branch**: `codex/youtube-auto-translate-fallback` (2 commits ahead of origin, not pushed)

---

## Architecture Summary

```
Backend:  FastAPI (Python 3.11+) — port 3001
Frontend: Next.js 14 (App Router) — port 3000
DB:       SQLite (local) / PostgreSQL (prod via Railway)
Queue:    ARQ + Redis (Docker)
LLM:      Sarvam (Telugu translate) + Ollama (local OSS) + OpenRouter (fallback)
Vector:   ChromaDB / Qdrant / PGVector (swappable)
```

Key routing rule: `config.yaml` controls LLM provider. One function `translate(text, lang_pair)` — provider is a config swap, never a code change.

---

## The Proposal: Claude Code + opencode Tandem

If the code quality meets your standards, here's the working model:

### Roles
| Tool | Role | Responsibility |
|------|------|----------------|
| **Claude Code** | Architect | System design, complex multi-file reasoning, architecture decisions, code review, debugging hard issues |
| **opencode** | Builder | Implementation, boilerplate, scripting, frontend work, batch operations, anything that can be described in a prompt |

### How It Works
1. **Claude Code designs** — you plan the module, define interfaces, specify contracts
2. **opencode builds** — you hand off the spec, it writes the code, runs tests, commits
3. **Escalation** — when opencode gets stuck (complex reasoning, cross-file architectural issues, multi-system debugging), it calls Claude Code
4. **Review** — Claude Code reviews opencode's output periodically

### When to Escalate to Claude Code
- Task spans 3+ files with interdependent logic
- System-wide trade-offs (e.g., migration strategy, caching architecture)
- Performance debugging that requires profiling
- Security review
- Anything the `project-settings.md` says "switch to Opus for"

### When opencode Can Handle It Alone
- Single-file edits, boilerplate, formatting
- Script writing (batch jobs, utilities)
- Frontend component building
- Test writing
- Documentation updates
- Simple API route creation

---

## How to Pick Up

```powershell
cd D:\Projects-D\omi-ted-v2
git pull --rebase origin main
git checkout codex/youtube-auto-translate-fallback
```

Read these in order:
1. `project-settings.md` — architecture decisions, module order, model routing
2. `.handoffs/20260618-02-kawin.md` — latest session handoff
3. `.handoffs/20260617-01-kawin.md` — RAG pipeline session

Then:
```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 3001
# In another terminal:
cd frontend
npm run dev
```

Verify both are running before touching any code.

---

## Known Issues for Claude Code to Be Aware of

1. **WARP proxy**: SOCKS5 on port 40000. Used by httpx for subtitle download but NOT by yt-dlp (breaks caption detection). See `backend/services/transcript.py`.
2. **React useState sync**: Fixed with `useEffect` in `editor/[videoId]/page.tsx` — `useState` initializers don't re-run when props change after `mutate()`.
3. **Telugu FTS**: PostgreSQL full-text search uses `'simple'` config, not `'english'` — Telugu needs simple.
4. **Google Cloud billing**: Ingestion paused at 74/7,139 videos. Need billing resolved to resume.
5. **sentence-transformers**: First use downloads ~500MB model for cross-encoder reranker.

---

## Env Vars

Backend `.env`:
```
DATABASE_URL=sqlite+aiosqlite:///./dev.db
SARVAM_API_KEY=sk_0xhu1oyj_fZv4Ar69qAPEzDdEfyQRDO6L
LLM_PROVIDER=sarvam
HOST=0.0.0.0
DEBUG=true
```

Frontend `.env.local`:
```
NEXT_PUBLIC_API_BASE=http://localhost:3001
```

---

*The code is real. The pipeline works. If you're satisfied with what opencode and deepseek built, let's run this in tandem.*
