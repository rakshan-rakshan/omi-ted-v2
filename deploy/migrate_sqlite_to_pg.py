"""
Migrate omi-ted-v2 data from SQLite (dev.db) -> Postgres + pgvector.

Run this AFTER the Postgres schema exists. The backend container runs
`alembic upgrade head` on boot, which also does `CREATE EXTENSION vector` and
builds the HNSW index (migration 002). This script copies ROWS only.

WHY a Python script and not pg_dump: the `chunks.embedding` column is JSON text
in SQLite but a native pgvector column in Postgres. Copying through SQLAlchemy
converts it automatically; a raw SQL dump would corrupt it. This also resets the
Postgres id sequences so future inserts don't collide with copied PKs.

Usage (inside the backend container — it has all deps and the Postgres URL):
    docker compose -f deploy/docker-compose.prod.yml cp /path/dev.db backend:/tmp/dev.db
    docker compose -f deploy/docker-compose.prod.yml exec backend \
        python /app/../deploy/migrate_sqlite_to_pg.py --source /tmp/dev.db --wipe
    # (or copy this file into the image / mount it; see DEPLOY.md)

Flags:
    --source PATH   SQLite file to read from (required).
    --wipe          TRUNCATE all target tables first (RESTART IDENTITY CASCADE).
                    Without it, aborts if any target table already has rows.
    --batch N       Rows per insert batch (default 5000).

ALWAYS dry-run against a scratch Postgres first — this has not been run in CI.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

# Make backend/ importable regardless of CWD so we get Base.metadata + models.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from database import Base  # noqa: E402
import models  # noqa: F401,E402  -- registers all tables on Base.metadata


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Path to the SQLite dev.db")
    ap.add_argument("--wipe", action="store_true", help="TRUNCATE target tables first")
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    if not os.path.exists(args.source):
        sys.exit(f"source not found: {args.source}")

    src_url = f"sqlite+aiosqlite:///{os.path.abspath(args.source)}"
    dst_url = os.environ.get("DATABASE_URL", "")
    if dst_url.startswith("postgresql://"):
        dst_url = dst_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "postgresql" not in dst_url:
        sys.exit(f"DATABASE_URL must point at Postgres, got: {dst_url!r}")

    src = create_async_engine(src_url)
    dst = create_async_engine(dst_url)
    tables = list(Base.metadata.sorted_tables)  # FK-safe: parents before children

    # Preflight / wipe.
    async with dst.begin() as dconn:
        if args.wipe:
            names = ", ".join(t.name for t in tables)
            await dconn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
            print(f"wiped {len(tables)} target tables")
        else:
            for t in tables:
                n = (await dconn.execute(select(func.count()).select_from(t))).scalar_one()
                if n:
                    sys.exit(f"target table {t.name} has {n} rows; pass --wipe to overwrite")

    total_all = 0
    for t in tables:
        async with src.connect() as sconn, dst.begin() as dconn:
            total = (await sconn.execute(select(func.count()).select_from(t))).scalar_one()
            if not total:
                print(f"  {t.name:22} 0")
                continue

            copied: int = 0
            batch: list[dict] = []
            result = await sconn.stream(select(t))
            async for row in result:
                batch.append(dict(row._mapping))
                if len(batch) >= args.batch:
                    await dconn.execute(insert(t), batch)
                    copied += len(batch)
                    batch = []
            if batch:
                await dconn.execute(insert(t), batch)
                copied += len(batch)

            # Reset the id sequence so the next INSERT doesn't collide with copied PKs.
            if "id" in t.c:
                await dconn.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence(:tbl, 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {t.name}), 1))"
                    ),
                    {"tbl": t.name},
                )
            print(f"  {t.name:22} {copied}")
            total_all += copied

    await src.dispose()
    await dst.dispose()
    print(f"DONE — {total_all} rows migrated to Postgres.")


if __name__ == "__main__":
    asyncio.run(main())
