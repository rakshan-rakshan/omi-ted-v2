"""
Scan Ophir Ministries channel + YVTV playlist via YouTube Data API v3.
Outputs urls_to_ingest.csv with deduplicated video entries.
"""
from __future__ import annotations

import asyncio
import csv
import os
import random
import sys
from dataclasses import dataclass, field

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_KEY = "AIzaSyAzkgvfDiPxP7VAtdQ7BPLIzmCSBeYoxGc"
BASE_URL = "https://www.googleapis.com/youtube/v3"

OPHIR_HANDLE = "@ophirministries"
YVTV_PLAYLIST_ID = "PLU79vgVw3ZVLuyMXyG-68Ww0lE7Xip00Y"

MAX_RETRIES = 4
BASE_BACKOFF = 2.0
MAX_PAGE_SIZE = 50


@dataclass
class VideoEntry:
    youtube_id: str
    source: str
    title: str


def _backoff_sleep(attempt: int) -> float:
    delay = BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1.0)
    return min(delay, 30.0)


def _is_retryable(status: int) -> bool:
    return status in {408, 429, 500, 502, 503, 504}


async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 403:
                body = resp.json()
                if any(e.get("reason") == "quotaExceeded" for e in body.get("error", {}).get("errors", [])):
                    raise RuntimeError("YouTube API quota exceeded")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if attempt < MAX_RETRIES and _is_retryable(exc.response.status_code):
                await asyncio.sleep(_backoff_sleep(attempt))
                continue
            raise
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt < MAX_RETRIES:
                await asyncio.sleep(_backoff_sleep(attempt))
                continue
            raise


async def _paginate_all(client: httpx.AsyncClient, endpoint: str, params: dict, items_key: str) -> list[dict]:
    all_items: list[dict] = []
    page_token: str | None = None
    while True:
        p = {**params}
        if page_token:
            p["pageToken"] = page_token
        data = await _get_json(client, f"{BASE_URL}/{endpoint}", p)
        all_items.extend(data.get(items_key, []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return all_items


async def _get_channel_uploads(client: httpx.AsyncClient) -> list[VideoEntry]:
    channel_data = await _get_json(client, f"{BASE_URL}/channels", {
        "part": "contentDetails",
        "forHandle": OPHIR_HANDLE,
        "key": API_KEY,
    })
    items = channel_data.get("items", [])
    if not items:
        print(f"WARNING: No channel found for {OPHIR_HANDLE}", file=sys.stderr)
        return []
    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_items = await _paginate_all(client, "playlistItems", {
        "part": "snippet",
        "playlistId": uploads_playlist_id,
        "maxResults": MAX_PAGE_SIZE,
        "key": API_KEY,
    }, "items")

    videos: list[VideoEntry] = []
    for item in playlist_items:
        rid = item["snippet"]["resourceId"]
        if rid.get("kind") == "youtube#video":
            videos.append(VideoEntry(
                youtube_id=rid["videoId"],
                source="channel",
                title=item["snippet"]["title"],
            ))
    return videos


async def _get_playlist_videos(client: httpx.AsyncClient) -> list[VideoEntry]:
    playlist_items = await _paginate_all(client, "playlistItems", {
        "part": "snippet",
        "playlistId": YVTV_PLAYLIST_ID,
        "maxResults": MAX_PAGE_SIZE,
        "key": API_KEY,
    }, "items")

    videos: list[VideoEntry] = []
    for item in playlist_items:
        rid = item["snippet"]["resourceId"]
        if rid.get("kind") == "youtube#video":
            videos.append(VideoEntry(
                youtube_id=rid["videoId"],
                source="playlist",
                title=item["snippet"]["title"],
            ))
    return videos


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        ophir_videos = await _get_channel_uploads(client)
        yvtv_videos = await _get_playlist_videos(client)

    seen: set[str] = set()
    all_entries: list[VideoEntry] = []

    for v in ophir_videos:
        if v.youtube_id not in seen:
            all_entries.append(v)
            seen.add(v.youtube_id)

    for v in yvtv_videos:
        if v.youtube_id not in seen:
            all_entries.append(v)
            seen.add(v.youtube_id)

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls_to_ingest.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["youtube_id", "source", "title"])
        for entry in all_entries:
            writer.writerow([entry.youtube_id, entry.source, entry.title])

    print(f"Found {len(ophir_videos)} Ophir + {len(yvtv_videos)} YVTV = {len(all_entries)} total videos")
    print(f"CSV written to urls_to_ingest.csv with {len(all_entries)} entries")


if __name__ == "__main__":
    asyncio.run(main())
