# Deploy runbook — Hetzner box (backend + Postgres) + Vercel (frontend)

> Alternative to the Railway path in [`DEPLOY.md`](DEPLOY.md). Use this one for a
> self-hosted box + Vercel (sidesteps the Railway region/routing issues noted there).

Target: your existing CX/CPX-class box (16 GB, ~3 GB free, shared with other projects)
runs **Postgres + backend**; **Vercel** serves the Next.js frontend.

```
Browser ──> Vercel (Next.js)  ──/api/v1/* rewrite (server-side)──>  https://api.yourdomain.com
                                                                          │  (Caddy, TLS)
                                                          box ┌───────────▼───────────┐
                                                              │ backend :8000 (uvicorn)│
                                                              │ postgres+pgvector      │  (private)
                                                              └────────────────────────┘
```

Files live in `deploy/`: `docker-compose.prod.yml`, `Caddyfile`, `.env.prod.example`, `migrate_sqlite_to_pg.py`.

---

## 0. Prereqs
- **DNS**: an A record `api.yourdomain.com` → your box's public IP.
- **Docker + Compose v2** on the box (`docker --version`; if other projects run there it's likely installed).
- **~3 GB RAM free** and ~10 GB disk (torch image ~2.5 GB + model cache ~1 GB + PG data).
- A translation key: `OPENROUTER_API_KEY` (free models).

> Because the box is **shared**, this stack is fully containerized and self-scoped: Postgres is private (no published port), the backend binds only `127.0.0.1:8000`, and it uses its own named volumes. It won't touch your other services — just avoid a port clash on `8000` (change the host side of `ports:` if taken).

## 1. Get the code + secrets onto the box
```bash
git clone <your repo> omi-ted-v2 && cd omi-ted-v2
cp deploy/.env.prod.example deploy/.env
# edit deploy/.env: set PG_PASSWORD, OPENROUTER_API_KEY, ALLOWED_ORIGINS=https://<your>.vercel.app
```

## 2. Bring up Postgres + backend
```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.prod.yml logs -f backend
```
First boot: builds the image, runs `alembic upgrade head` (creates schema, `CREATE EXTENSION vector`, HNSW index), downloads the ~1 GB embedding model into the `modelcache` volume, then starts uvicorn with **one worker**. Wait for `Application startup complete`, then:
```bash
curl -s localhost:8000/health          # -> {"status":"ok","service":"omi-ted-v2"}
```

## 3. Migrate your data (188 MB SQLite → Postgres)
Do this from a **snapshot** so you're not reading a live DB while the local backend writes to it.
```bash
# On the machine that has dev.db (stop local translation runs first):
cp backend/dev.db /tmp/dev.snapshot.db
scp /tmp/dev.snapshot.db  user@box:/tmp/dev.db

# On the box — run the migrator inside the backend container (it has all deps + DATABASE_URL):
docker compose -f deploy/docker-compose.prod.yml cp deploy/migrate_sqlite_to_pg.py backend:/tmp/migrate.py
docker compose -f deploy/docker-compose.prod.yml cp /tmp/dev.db backend:/tmp/dev.db
docker compose -f deploy/docker-compose.prod.yml exec backend python /tmp/migrate.py --source /tmp/dev.db --wipe
```
It copies all 13 tables in FK order, converts the `chunks.embedding` JSON → native pgvector, and resets id sequences. Expect `segments 289379` etc. Verify:
```bash
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  psql -U omitred -c "select count(*) from segments; select count(*) from glossary;"
```
> ⚠️ Dry-run first: this script hasn't been through CI. Point it at a throwaway PG once and confirm counts before trusting `--wipe` on the real one.

## 4. TLS reverse proxy
**If the box has no reverse proxy yet:** edit `deploy/Caddyfile` (set your domain), then:
```bash
caddy run --config deploy/Caddyfile      # or install caddy as a systemd service
curl -s https://api.yourdomain.com/health
```
**If it already runs nginx/Traefik/Caddy:** don't start a second one — add a vhost there for `api.yourdomain.com` → `127.0.0.1:8000` with TLS.

## 5. ⚠️ Secure the public backend (do this before real use)
The backend has **no built-in auth**. Once `api.yourdomain.com` is public, anyone can hit `/api/v1/*` — read your dataset, trigger runs, edit segments. Options, easiest → best:
- **A. Obscurity + accept it** (weakest): only for a short-lived test. The data (your review work) is exposed.
- **B. Shared-secret header (recommended).** Put a random `BACKEND_API_KEY` in `deploy/.env` and Vercel, uncomment the `X-Backend-Key` gate in `deploy/Caddyfile`, and have the frontend send it. Because the Vercel→backend hop is **server-side**, add the header in a Next.js proxy route (`app/api/[...path]/route.ts`) reading `process.env.BACKEND_API_KEY` — the secret never reaches the browser. *(I can write this ~30-line route + swap out the `next.config.js` rewrite for it — ask.)*
- **C. Full auth** (later): real login on the app.

## 6. Vercel (frontend)
1. Import the repo → **Root Directory = `frontend`** (Framework auto-detects Next.js 14).
2. Environment variables:
   - `BACKEND_URL = https://api.yourdomain.com`  ← `next.config.js` rewrites `/api/*` here (server-side).
   - `NEXT_PUBLIC_API_BASE = /api/v1`  (the axios client base).
   - `BACKEND_API_KEY = <same as box>` (only if you did §5-B with a proxy route).
3. Deploy. Set `ALLOWED_ORIGINS` in `deploy/.env` to the resulting `*.vercel.app` URL and `docker compose … up -d` to reload.

## 7. Verify end-to-end
- `https://<your>.vercel.app` loads.
- Open the editor for a video (e.g. `/editor/J8m-aLryDOk`) — segments load = Vercel → backend → Postgres works.
- Save an edit; re-open — it persisted.

---

## Ops
- **Backups (do this — the reviewed dataset is irreplaceable):**
  ```bash
  docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
    pg_dump -U omitred omitred | gzip > omitred-$(date +%F).sql.gz
  ```
  Put it on a cron; keep copies off-box.
- **Logs:** `docker compose -f deploy/docker-compose.prod.yml logs -f backend`
- **Restart / update:** `git pull && docker compose -f deploy/docker-compose.prod.yml up -d --build` (alembic auto-migrates on boot).
- **Swap file** (cheap OOM insurance during builds): `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` (+ add to `/etc/fstab`).

## App-specific gotchas
- **`--workers 1` is required**, not optional — 2 workers load the 1.3 GB embedder twice and blow past 3 GB. (The prod compose overrides the Dockerfile's `--workers 2`.)
- **Embedder dim must be 768** (`intfloat/multilingual-e5-base`) — matches `chunks.embedding Vector(768)` and the HNSW index. Don't set the 384-dim MiniLM from `.env.example`.
- **RAG uses Ollama** in `config.yaml` (`ollama_base_url: localhost:11434`) — that won't exist on the box. Your **core path (translate / edit / export) is unaffected** (OpenRouter + in-process sentence-transformers). Only RAG Q&A synthesis/rerank would need Ollama installed or repointing — ignore unless you use RAG in prod.
- **No CORS headache:** the browser talks only to Vercel; Vercel proxies to the backend server-side. `ALLOWED_ORIGINS` is defense-in-depth, not load-bearing.
- **CPU-only torch (optional):** the image pulls full CUDA torch (~2.5 GB) but you only do CPU inference. Pin the CPU wheel in `requirements.txt` to shrink the image and speed builds. *(Ask and I'll do it.)*
