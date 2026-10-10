import os, shutil, sys, time
import requests
sys.path.insert(0, "backend")
def t(name, url, **kw):
    t0 = time.time()
    try:
        r = requests.get(url, timeout=40, **kw); print(name, r.status_code, round(time.time() - t0, 1), "s", r.text[:300].replace("\n", " | "))
    except Exception as e:
        print(name, "ERR", round(time.time() - t0, 1), type(e).__name__)
t("fred plain", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
t("fred cosd", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL&cosd=2026-01-01")
t("fred ua", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WTREGEN&cosd=2026-08-01", headers={"User-Agent": "Mozilla/5.0"})
t("fred ua2", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WRESBAL&cosd=2026-08-01", headers={"User-Agent": "congress-trades-tracker/1.0"})
t("fred rrp", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RRPONTSYD&cosd=2026-09-01")
t("fred hy", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2026-09-01")
t("nyfed sofr", "https://markets.newyorkfed.org/api/rates/secured/sofr/last/3.json")
t("nyfed effr", "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/3.json")
t("nyfed rrp", "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=2026-10-01")
t("treasury", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv")
t("fiscaldata tga", "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance?sort=-record_date&page[size]=3")
shutil.copy("backend/data/congress_trades.db", "/tmp/t.db")
os.environ["DATABASE_URL"] = "sqlite:////tmp/t.db"
from app.database import init_db, SessionLocal
from app import polymarket as pm
from app.models import PolymarketAlert, TelegramState
init_db(); db = SessionLocal()
db.merge(TelegramState(key=pm.STATE_KEY, value=str(int(time.time()) - 72 * 3600))); db.commit()
pm.MAX_PAGES = 20; pm.STORE_MIN_SCORE = 0
print(pm.scan(db))
rows = db.query(PolymarketAlert).filter(PolymarketAlert.score.isnot(None)).order_by(PolymarketAlert.score.desc()).all()
for r in rows[:30]:
    print(f"{r.score:5.1f} {r.tag:11} ${r.size_usd:>10,.0f} @{r.price:.2f} h={r.hours_to_end and round(r.hours_to_end)} w={r.wallet_markets} | {r.market_question[:80]} -> {r.outcome}")
