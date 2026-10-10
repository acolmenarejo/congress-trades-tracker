import json, os, shutil, sys
sys.path.insert(0, "backend")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
from app.database import init_db, SessionLocal
from app import macro, polymarket_macro
init_db(); db = SessionLocal()
macro.refresh(db)
print(polymarket_macro.fetch(db))
print(json.dumps(polymarket_macro.load_meta(db), ensure_ascii=False, indent=1))
snap = macro.snapshot(db)
print(json.dumps(snap["polymarket"], ensure_ascii=False, indent=1))
print("\n".join(macro.digest_lines(db)))
