# OMI-TED v2 — Cloud Deploy (Railway, always-on, auto-deploy)

> Prefer a self-hosted box + Vercel instead? See [`DEPLOY-HETZNER.md`](DEPLOY-HETZNER.md).

Goal: zero local dev. Push to `main` → Railway redeploys both services. No `uvicorn`, no `npm run dev` ever again.

Architecture on Railway, one project, three services:

```
[ omi-ted-v2 (project) ]
   ├── backend         (Dockerfile, port from $PORT, healthcheck /health)
   ├── frontend        (Dockerfile, port from $PORT, healthcheck /)
   └── postgres        (Railway managed plugin, exposes DATABASE_URL)
```

Frontend proxies `/api/*` to backend over Railway's private network. No CORS issues, no public backend URL needed for the frontend to talk to it.

> **Existing project state (session 13 baseline)**: project `capable-victory/production`, single backend service on legacy `us-west2` region, public proxy was not routing traffic, service slept after 7 min. Recommended fix below: re-create services in a modern region using these new Dockerfiles.

---

## One-time setup (~15 min)

### 1. Push the latest code

```bash
cd <project-root>
git pull --rebase origin main
git push origin main
```

### 2. Re-provision the Railway project (clean slate)

The existing `capable-victory` project is on legacy `us-west2`. Easier to start fresh than debug routing.

1. Go to https://railway.com/new
2. Click **Deploy from GitHub repo** → select `rakshan-rakshan/omi-ted-v2`
3. When Railway offers to auto-detect a service, **cancel** — we want manual control of three services.
4. In project Settings, set **Region** to `us-east4` or `eu-west1` (anything that isn't us-west2 Legacy).

### 3. Add the Postgres plugin

1. Project dashboard → **+ New** → **Database** → **PostgreSQL**
2. Wait ~30s. Railway provisions a managed Postgres and exposes `DATABASE_URL` as a shared variable.

### 4. Add the backend service

1. **+ New** → **GitHub Repo** → pick `omi-ted-v2`
2. Settings tab:
   - **Service name**: `backend`
   - **Root Directory**: `backend`
   - **Build**: Railway picks up `backend/railway.json` and uses the Dockerfile automatically.
   - **Watch Paths**: `backend/**` (frontend pushes won't redeploy backend)
3. Variables tab — paste these:
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SARVAM_API_KEY=<paste>
   OPENROUTER_API_KEY=<paste>
   GOOGLE_TRANSLATE_API_KEY=<paste>
   LLM_PROVIDER=sarvam
   ALLOWED_ORIGINS=https://<your-frontend-url>.up.railway.app
   YT_PROXY=                # optional — set if YouTube starts 429/529-ing
   ```
   `${{Postgres.DATABASE_URL}}` is a Railway reference variable — auto-resolves and stays in sync if Postgres URL rotates.
4. Networking tab → **Generate Domain** → note the URL (e.g. `omi-backend-production.up.railway.app`).
5. Deploy. Logs should show `alembic upgrade head` then uvicorn boot. Hit `https://<backend>/health` → `{"status":"ok"}`.

### 5. Add the frontend service

1. **+ New** → **GitHub Repo** → pick `omi-ted-v2` again
2. Settings tab:
   - **Service name**: `frontend`
   - **Root Directory**: `frontend`
   - **Watch Paths**: `frontend/**`
3. Variables tab:
   ```
   BACKEND_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:${{backend.PORT}}
   NEXT_PUBLIC_API_BASE=/api/v1
   ```
   Private-network reference means traffic never leaves Railway — no public-internet hop, no CORS.
4. Networking tab → **Generate Domain**. That's your live app URL.
5. Back to **backend** service → update `ALLOWED_ORIGINS` to the frontend domain you just generated.
6. Deploy. Open the frontend URL — header + amber banner should render.

### 6. Confirm auto-deploy

Already on by default. Check each service:
- Settings → Source → **Auto Deploy on Push** = ON
- Settings → Source → **Branch** = `main`

From now on: `git push origin main` → both services redeploy in parallel. Backend runs `alembic upgrade head` on every boot, so schema changes ship automatically.

---

## Daily flow (no more local)

```bash
git add -A
git commit -m "feat: <whatever>"
git push origin main
# Railway redeploys in ~90s. Watch logs in the dashboard.
```

The services run 24/7. There is no "start" or "stop". Free $5/mo credit covers light usage; upgrade to Hobby ($5/mo per service) for sustained always-on.

---

## YouTube 529 / rate-limit playbook

Symptom: ingest fails with `HTTP Error 529` or `Too Many Requests`.

Root cause: YouTube rate-limits Railway's egress IPs.

Fix order:

1. **Already in place** — the transcript service auto-retries with exponential backoff. Most 529s resolve in retry 2-3.
2. If still failing, set `YT_PROXY` on the backend service:
   - Get a Webshare residential rotating proxy (https://www.webshare.io/, $1/mo plan is enough)
   - Variable: `YT_PROXY=http://user:pass@p.webshare.io:80`
   - Redeploy. yt-dlp + httpx + youtube-transcript-api will all route through it.
3. As a last resort, mount cookies via a Railway variable — but cookies expire and need maintenance; prefer (2).

---

## Common deploy errors

| Symptom | Fix |
|---------|-----|
| `Application failed to respond` (502) | Service still booting. First boot runs `alembic upgrade head` (30-60s). Wait, refresh. |
| `relation "videos" does not exist` | Migrations didn't run. Check backend logs for `alembic upgrade head` errors — usually a missing `DATABASE_URL`. |
| Frontend `Network Error` on every API call | `BACKEND_URL` env wrong on frontend, or `ALLOWED_ORIGINS` doesn't include frontend domain on backend. |
| Build fails: `COPY backend/requirements.txt: not found` | Service Root Directory not set to `backend`. Fix in service Settings. |
| Healthcheck timeout | Bump `healthcheckTimeout` in `backend/railway.json` to 180. |
| URL unreachable but service shows Online (session 13 issue) | us-west2 Legacy region proxy bug. Re-create service in us-east4 or eu-west1. |

---

## Cost expectation

- Backend: ~256 MB RAM idle, ~512 MB during ingest → $3-5/mo
- Frontend: ~128 MB RAM, mostly idle → $1-2/mo
- Postgres: free tier 1 GB → $0 until exceeded
- **Total**: ~$5-8/mo on Hobby plan
