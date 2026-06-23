"""
Re-embed all chunks that already have embeddings.
Loads existing chunks with non-null embeddings, regenerates them,
and updates in batch. Resumable — skips chunks where dimension already matches.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import AsyncSessionLocal
from models import Chunk
from services.embeddings import embed_chunks, embed_dim

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


async def reembed_all() -> int:
    target_dim = embed_dim()
    updated = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chunk).where(Chunk.embedding.isnot(None)).order_by(Chunk.id)
        )
        chunks = result.scalars().all()
        logger.info("Found %d chunks with existing embeddings", len(chunks))

        to_reembed: list[Chunk] = []
        for c in chunks:
            emb = c.embedding
            if isinstance(emb, str):
                emb = json.loads(emb)
            if emb is not None and len(emb) == target_dim:
                continue
            to_reembed.append(c)

        logger.info(
            "Skipping %d chunks (already %d-dim), re-embedding %d chunks",
            len(chunks) - len(to_reembed), target_dim, len(to_reembed),
        )

        for i in range(0, len(to_reembed), BATCH_SIZE):
            batch = to_reembed[i:i + BATCH_SIZE]
            texts = [c.chunk_text for c in batch]

            try:
                embeddings = await embed_chunks(texts)
            except Exception as e:
                logger.error("Embedding batch %d failed: %s", i // BATCH_SIZE, e)
                continue

            for chunk, emb in zip(batch, embeddings):
                chunk.embedding = emb

            await session.flush()
            updated += len(batch)
            logger.info(
                "Re-embedded batch %d/%d (%d chunks)",
                i // BATCH_SIZE + 1,
                (len(to_reembed) + BATCH_SIZE - 1) // BATCH_SIZE,
                len(batch),
            )

        await session.commit()

    return updated


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    count = await reembed_all()
    logger.info("Done. Re-embedded %d chunks.", count)


if __name__ == "__main__":
    asyncio.run(main())
