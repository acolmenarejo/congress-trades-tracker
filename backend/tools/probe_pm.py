import os, shutil, sys, time
sys.path.insert(0, "backend")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
import json
from app.database import init_db, SessionLocal
from app import macro, polymarket as pm, digest
from app.models import PolymarketAlert, TelegramState
init_db(); db = SessionLocal()
print(macro.refresh(db))
s = macro._load(db)
for k, v in s.items(): print(k, v.last_date, v.last, "30d ago", v.ago(30))
snap = macro.snapshot(db)
for i in snap["indicators"]:
    i.pop("history"); print(json.dumps(i, ensure_ascii=False))
print(snap["regime"], snap["summary"])
db.merge(TelegramState(key=pm.STATE_KEY, value=str(int(time.time()) - 72 * 3600))); db.commit()
pm.MAX_PAGES = 20
print(pm.scan(db))
rows = db.query(PolymarketAlert).filter(PolymarketAlert.score.isnot(None)).order_by(PolymarketAlert.score.desc()).all()
for r in rows[:30]:
    print(f"{r.score:5.1f} {r.tag:11} ${r.size_usd:>10,.0f} @{r.price:.2f} h={r.hours_to_end and round(r.hours_to_end)} w={r.wallet_markets} alert={pm.should_alert(r)} | {r.market_question[:80]} -> {r.outcome}")
print(digest.build(db))
