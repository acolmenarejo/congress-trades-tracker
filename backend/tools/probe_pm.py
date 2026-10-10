import os, shutil, sys, time
sys.path.insert(0, "backend")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
from app.database import init_db, SessionLocal
from app import polymarket as pm
from app.models import PolymarketAlert, TelegramState
init_db(); db = SessionLocal()
db.merge(TelegramState(key=pm.STATE_KEY, value=str(int(time.time()) - 24 * 3600))); db.commit()
t0 = time.time(); print(pm.scan(db), "secs", round(time.time() - t0))
rows = db.query(PolymarketAlert).filter(PolymarketAlert.score.isnot(None)).order_by(PolymarketAlert.score.desc()).all()
from collections import Counter
print("by tag", Counter(r.tag for r in rows), "would alert", sum(pm.should_alert(r) for r in rows))
for r in rows[:40]:
    print(f"{r.score:5.1f} {r.tag:11} ${r.size_usd:>10,.0f} @{r.price:.2f} h={r.hours_to_end} w={r.wallet_markets} | {r.market_question[:90]} -> {r.outcome}")
for r in [r for r in rows if pm.should_alert(r)][:3]:
    print(pm.format_alert(r)); print("----")
