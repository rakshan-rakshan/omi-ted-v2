"""Pick fresh video IDs not in dev.db. Throwaway helper."""
import csv
import os
import sqlite3

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dev.db")
csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls_to_ingest.csv")

conn = sqlite3.connect(db)
have = {r[0] for r in conn.execute("SELECT youtube_id FROM videos")}
print(f"DB has {len(have)} videos already")
conn.close()

picks: list[str] = []
with open(csv_path, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        yid = (row.get("youtube_id") or "").strip()
        if yid and yid not in have:
            picks.append(yid)
        if len(picks) >= 10:
            break
print("Fresh IDs:", picks)
