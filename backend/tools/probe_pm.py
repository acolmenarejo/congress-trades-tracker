import sys, time
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, "backend")
from app import polymarket as pm
now = datetime.now(timezone.utc)
trades = pm._recent_big_trades(int(time.time()) - 24 * 3600)
print("trades", len(trades))
texts = {t["conditionId"]: f"{t.get('title', '')} {t.get('slug', '')} {t.get('eventSlug', '')}" for t in trades}
print("classes", Counter(pm.classify(x) for x in texts.values()))
keep = sorted(c for c, x in texts.items() if pm.classify(x))
print("sample kept", [texts[c][:80] for c in keep[:15]])
print("sample skipped", [x[:80] for x in texts.values() if not pm.classify(x)][:15])
m = pm._markets(keep)
print("markets found", len(m), "of", len(keep))
rows = []
for t in trades:
    if t["conditionId"] not in keep: continue
    price = float(t["price"]); usd = float(t["size"]) * price
    mk = m.get(t["conditionId"], {})
    h = pm._hours_to_end(mk, now); liq = float(mk.get("liquidity") or 0) or None
    s, _ = pm.score_trade(usd, price, h, None, liq)
    rows.append((s, usd, price, h, t.get("title", "")[:70], t.get("outcome")))
rows.sort(reverse=True)
print("base score dist", Counter(int(r[0] // 10) * 10 for r in rows))
for r in rows[:25]: print(f"{r[0]:5.1f} ${r[1]:>10,.0f} @{r[2]:.2f} h={r[3] and round(r[3])} {r[4]} -> {r[5]}")
w = {}
for r in rows[:10]: pass
print("price dist", Counter(round(r[2], 1) for r in rows))
