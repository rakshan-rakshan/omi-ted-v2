import os, sqlite3

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dev.db")
conn = sqlite3.connect(db)

tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables:", tables)

for t in tables:
    c = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {c} rows")

print("\n--- videos columns ---")
for c in conn.execute("PRAGMA table_info(videos)"):
    print(f"  {c[1]}: type={c[2]} nullable={c[3]} default={c[4]}")

print("\n--- indices ---")
for i in conn.execute("SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='videos'"):
    print(f"  {i[1]}: sql={i[4][:100]}")

conn.close()
