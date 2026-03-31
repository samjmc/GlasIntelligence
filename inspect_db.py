import sqlite3
import json

for platform in ["twitter", "reddit"]:
    db_path = f"backend/uploads/simulations/sim_1c08c314bad7/{platform}_simulation.db"
    try:
        db = sqlite3.connect(db_path)
        cur = db.cursor()
        tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"\n=== {platform} ===")
        print(f"Tables: {[t[0] for t in tables]}")
        for t in tables[:8]:
            cols = cur.execute(f"PRAGMA table_info({t[0]})").fetchall()
            count = cur.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
            print(f"  {t[0]}: {count} rows, cols={[c[1] for c in cols[:8]]}")
            if count > 0:
                row = cur.execute(f"SELECT * FROM {t[0]} LIMIT 1").fetchone()
                print(f"    sample: {row[:5] if row else 'empty'}...")
        db.close()
    except Exception as e:
        print(f"{platform} error: {e}")
