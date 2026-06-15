"""
Embed all chunks that don't have embeddings yet.
Loads embedder, processes in batches of 64, updates rows.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

from sqlalchemy import select, update

sys.path.insert(0, ".")

from database import AsyncSessionLocal, Vector
from models import Chunk
from services.embeddings import embed_chunks

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


async def embed_missing_chunks() -> int:
    total_embedded = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chunk).where(Chunk.embedding.is_(None)).order_by(Chunk.id)
        )
        chunks = result.scalars().all()
        logger.info("Found %d chunks without embeddings", len(chunks))

        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts = [c.chunk_text for c in batch]

            try:
                embeddings = await embed_chunks(texts)
            except Exception as e:
                logger.error("Embedding batch %d failed: %s", i // BATCH_SIZE, e)
                continue

            for chunk, emb in zip(batch, embeddings):
                chunk.embedding = emb

            await session.flush()
            total_embedded += len(batch)
            logger.info(
                "Embedded batch %d/%d (%d chunks)",
                i // BATCH_SIZE + 1,
                (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE,
                len(batch),
            )

        await session.commit()

    return total_embedded


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    count = await embed_missing_chunks()
    logger.info("Done. Embedded %d chunks.", count)


if __name__ == "__main__":
    asyncio.run(main())
