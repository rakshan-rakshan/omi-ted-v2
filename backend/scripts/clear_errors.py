import sqlite3, os

db = os.path.join(r"D:\Projects-D\omi-ted-v2\backend", "dev.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# Delete all pending/fetching videos and their jobs
c.execute("DELETE FROM jobs WHERE video_id IN (SELECT id FROM videos WHERE status IN ('pending', 'fetching'))")
c.execute("DELETE FROM videos WHERE status IN ('pending', 'fetching')")
conn.commit()

c.execute("SELECT status, COUNT(*) FROM videos GROUP BY status")
total = 0
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")
    total += row[1]
print(f"  Total: {total}")
conn.close()
