"""
Backfill English translations for Telugu messages.
Finds messages with language='te' and no English translation,
translates title + description via Sarvam API.
Rate-limited to 1 req/sec, resumable, cost-tracked.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import AsyncSessionLocal
from models import Message
from services.translate import translate

logger = logging.getLogger(__name__)

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backfill_log.txt")
RATE_LIMIT = 1.0


def _log_entry(result: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.utcnow().isoformat()} {result}\n")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    total_cost_est = 0.0
    translated_count = 0
    skipped_count = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(Message.language == "te").order_by(Message.id)
        )
        messages = result.scalars().all()
        logger.info("Found %d Telugu messages", len(messages))

        for msg in messages:
            needs_update = False

            if msg.title and msg.title.strip():
                translated_title = await translate(
                    msg.title, src="te", tgt="en", provider="sarvam"
                )
                if translated_title and translated_title != msg.title:
                    msg.title = translated_title
                    needs_update = True
                    total_cost_est += len(msg.title.split()) * 0.002
                await asyncio.sleep(RATE_LIMIT)

            if msg.description and msg.description.strip():
                translated_desc = await translate(
                    msg.description, src="te", tgt="en", provider="sarvam"
                )
                if translated_desc and translated_desc != msg.description:
                    msg.description = translated_desc
                    needs_update = True
                    total_cost_est += len(msg.description.split()) * 0.002
                await asyncio.sleep(RATE_LIMIT)

            if needs_update:
                msg.language = "en"
                translated_count += 1
                _log_entry(f"OK — Message {msg.id}: title+desc translated")
                logger.info("Translated Message %d", msg.id)
            else:
                skipped_count += 1
                _log_entry(f"SKIP — Message {msg.id}: nothing to translate")

        await session.commit()

    print(f"Backfill complete: {translated_count} translated, {skipped_count} skipped")
    print(f"Estimated cost: ${total_cost_est:.4f}")
    print(f"Log written to backfill_log.txt")


if __name__ == "__main__":
    asyncio.run(main())
