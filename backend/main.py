"""FastAPI entry point. Routers are mounted under /api/v1."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).parent / ".env")

from routers import health, ingest, videos, export, batch, documents, stats, settings_api, glossary, search, eval

app = FastAPI(
    title="OMI-TED v2",
    description="Telugu Christian theology translation engine.",
    version="0.1.0",
)


@app.on_event("startup")
async def _preload_reranker():
    """Preload the cross-encoder reranker in background — non-blocking."""
    import threading
    def _load():
        from services.model_router import model_router
        model_router._ensure_reranker()
    threading.Thread(target=_load, daemon=True).start()

# Allow localhost dev + any Railway/Vercel deployment.
_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router,       prefix="/api/v1/ingest", tags=["ingest"])
app.include_router(videos.router,       prefix="/api/v1",        tags=["videos"])
app.include_router(export.router,       prefix="/api/v1",        tags=["export"])
app.include_router(batch.router,        prefix="/api/v1",        tags=["batch"])
app.include_router(documents.router,                                tags=["documents"])
app.include_router(stats.router,        prefix="/api/v1",        tags=["stats"])
app.include_router(settings_api.router, prefix="/api/v1",        tags=["settings"])
app.include_router(glossary.router,     prefix="/api/v1",        tags=["glossary"])
app.include_router(search.router,                                     tags=["search"])
app.include_router(eval.router,                                       tags=["eval"])

