import json, os, shutil, sys, time
sys.path.insert(0, "backend")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
from app.database import init_db, SessionLocal
from app import macro, polymarket as pm, polymarket_macro
from app.models import PolymarketAlert, TelegramState
init_db(); db = SessionLocal()
t = pm._recent_big_trades(int(time.time()) - 3600)
print("trades >=2k last hour", len(t))
if t:
    x = t[0]; print("position sample", json.dumps(pm._position(x["proxyWallet"], x["conditionId"], x.get("outcomeIndex")))[:800])
db.merge(TelegramState(key=pm.STATE_KEY, value=str(int(time.time()) - 24 * 3600))); db.commit()
pm.MAX_PAGES = 20
t0 = time.time(); print(pm.scan(db), round(time.time() - t0), "s")
rows = db.query(PolymarketAlert).filter(PolymarketAlert.score.isnot(None)).order_by(PolymarketAlert.score.desc()).all()
for r in rows[:25]:
    print(f"{r.score:5.1f} {r.tag:11} ${r.size_usd:>10,.0f} @{r.price:.2f} h={r.hours_to_end and round(r.hours_to_end)} w={r.wallet_markets} alert={pm.should_alert(r)} | {r.market_question[:70]} -> {r.outcome} | {r.reasons}")
macro.refresh(db)
print(polymarket_macro.fetch(db))
print(json.dumps(polymarket_macro.load_meta(db).get("kalshi"), ensure_ascii=False))
v = macro.snapshot(db)["polymarket"]; v.pop("bets")
print(json.dumps(v, ensure_ascii=False, indent=1))
print("\n".join(macro.digest_lines(db)))
