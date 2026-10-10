import json, os, shutil, sys
sys.path.insert(0, "backend")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
from app.database import init_db, SessionLocal
from app import macro, digest
init_db(); db = SessionLocal()
print(macro.refresh(db))
snap = macro.snapshot(db)
for i in snap["indicators"]:
    i["history"] = len(i["history"]); print(json.dumps(i, ensure_ascii=False))
print(snap["regime"], snap["summary"])
print("\n".join(macro.digest_lines(db)))
print(os.path.getsize("/tmp/t.db") - os.path.getsize("backend/data/congress_trades.db"), "bytes added")
