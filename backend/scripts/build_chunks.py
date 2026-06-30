"""
Build chunks from fetched videos.
Queries videos with status 'fetched', creates Message rows, segments → chunks.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, ".")

from database import AsyncSessionLocal
from models import Chunk, Message, Segment, Video
from services.chunking import chunk_segments

logger = logging.getLogger(__name__)


async def build_all_chunks() -> int:
    total_chunks = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Video).where(Video.status == "fetched").order_by(Video.id)
        )
        videos = result.scalars().all()
        logger.info("Found %d fetched videos", len(videos))

        for video in videos:
            msg_result = await session.execute(
                select(Message).where(Message.video_id == video.id)
            )
            message = msg_result.scalar_one_or_none()

            if message is None:
                message = Message(
                    video_id=video.id,
                    title=video.title or f"Video {video.youtube_id}",
                    message_type="sermon",
                    language="te",
                )
                session.add(message)
                await session.flush()
                logger.info("Created Message %d for video %s", message.id, video.youtube_id)

            seg_result = await session.execute(
                select(Segment)
                .where(Segment.video_id == video.id)
                .order_by(Segment.segment_index)
            )
            segments = seg_result.scalars().all()

            seg_dicts = [
                {
                    "id": s.id,
                    "text": s.en_final or s.en_auto or "",
                    "segment_index": s.segment_index,
                    "start_time": s.start_time,
                }
                for s in segments
                if s.en_final or s.en_auto
            ]

            if not seg_dicts:
                logger.warning("No English text for video %s, skipping", video.youtube_id)
                continue

            existing = await session.execute(
                select(Chunk).where(Chunk.message_id == message.id)
            )
            if existing.scalars().first() is not None:
                logger.info(
                    "Chunks already exist for message %d, skipping", message.id
                )
                continue

            chunks = await chunk_segments(message.id, seg_dicts)
            for c in chunks:
                session.add(Chunk(
                    message_id=c.message_id,
                    chunk_index=c.chunk_index,
                    chunk_text=c.chunk_text,
                    language_code=c.language_code,
                    token_count=c.token_count,
                    start_time=c.start_time,
                ))

            total_chunks += len(chunks)
            logger.info(
                "Built %d chunks for video %s (msg %d)",
                len(chunks), video.youtube_id, message.id,
            )

        await session.commit()

    return total_chunks


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    count = await build_all_chunks()
    logger.info("Done. Created %d chunks total.", count)


if __name__ == "__main__":
    asyncio.run(main())
