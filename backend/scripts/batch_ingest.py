"""
Batch ingest: sends a batch, waits for all jobs to finish, then sends next.
Never overloads the backend or YouTube rate limits.
"""
from __future__ import annotations

import asyncio
import csv
import os
import httpx

BASE = "http://localhost:3001/api/v1"
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls_to_ingest.csv")
BATCH_SIZE = 3  # match backend semaphore
JOB_POLL_INTERVAL = 5
JOB_POLL_TIMEOUT = 120  # max wait per batch


def read_csv() -> list[str]:
    ids: list[str] = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yt_id = row.get("youtube_id", "").strip()
            if yt_id:
                ids.append(yt_id)
    return ids


async def wait_jobs(client: httpx.AsyncClient, job_ids: list[int]) -> dict[str, int]:
    """Poll until all jobs are done/failed. Returns status counts."""
    pending = set(job_ids)
    counts = {"done": 0, "failed": 0, "timeout": 0}

    elapsed = 0
    while pending and elapsed < JOB_POLL_TIMEOUT:
        await asyncio.sleep(JOB_POLL_INTERVAL)
        elapsed += JOB_POLL_INTERVAL

        for jid in list(pending):
            try:
                resp = await client.get(f"{BASE}/ingest/jobs/{jid}", timeout=10)
                resp.raise_for_status()
                status = resp.json().get("status", "")
                if status in ("done", "failed"):
                    pending.discard(jid)
                    counts[status] = counts.get(status, 0) + 1
            except Exception:
                pass  # will retry next poll

    counts["timeout"] = len(pending)
    return counts


async def main() -> None:
    all_ids = read_csv()
    print(f"CSV: {len(all_ids)} IDs", flush=True)

    batches = [all_ids[i : i + BATCH_SIZE] for i in range(0, len(all_ids), BATCH_SIZE)]
    print(f"{len(batches)} batches of {BATCH_SIZE}\n", flush=True)

    total_done = 0
    total_failed = 0
    total_timeout = 0
    total_skipped = 0

    async with httpx.AsyncClient(timeout=60) as client:
        for idx, batch in enumerate(batches, 1):
            try:
                resp = await client.post(
                    f"{BASE}/ingest/batch",
                    json={"youtube_ids": batch},
                )
                resp.raise_for_status()
                data = resp.json()
                queued = data.get("queued", 0)
                already = data.get("already_fetched", 0)
                total_skipped += already

                if queued == 0:
                    continue

                job_ids = [j["job_id"] for j in data.get("jobs", []) if j.get("job_id", -1) > 0]

                # Wait for this batch to finish before sending next
                counts = await wait_jobs(client, job_ids)
                total_done += counts["done"]
                total_failed += counts["failed"]
                total_timeout += counts["timeout"]

                print(
                    f"Batch {idx}/{len(batches)}: queued={queued} "
                    f"| done={counts['done']} fail={counts['failed']} "
                    f"timeout={counts['timeout']} "
                    f"| total: {total_done}D {total_failed}F {total_timeout}T {total_skipped}S",
                    flush=True,
                )

            except Exception as exc:
                total_failed += len(batch)
                print(f"Batch {idx}/{len(batches)}: ERROR {exc}", flush=True)
                await asyncio.sleep(10)

    print(f"\n=== DONE ===", flush=True)
    print(f"Done: {total_done} | Failed: {total_failed} | Timeout: {total_timeout} | Skipped: {total_skipped}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
