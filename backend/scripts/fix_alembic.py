import sqlite3
conn = sqlite3.connect("dev.db")
conn.execute("DELETE FROM alembic_version")
conn.execute("INSERT INTO alembic_version(version_num) VALUES (?)", ("003",))
conn.commit()
print(conn.execute("SELECT version_num FROM alembic_version").fetchone()[0])
conn.close()
