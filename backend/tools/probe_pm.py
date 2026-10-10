import json, requests
K = "https://api.elections.kalshi.com/trade-api/v2"
def get(p, q=None):
    r = requests.get(K + p, params=q or {}, timeout=30); print("GET", r.url, r.status_code); return r.json() if r.ok else {}
s = get("/series", {"category": "Economics"})
for x in (s.get("series") or [])[:400]:
    t = x.get("ticker", ""); title = x.get("title", "")
    if any(w in (t + title).lower() for w in ("fed", "recess", "cpi", "inflation", "rate", "gdp")):
        print("S", t, "|", title, "|", x.get("frequency"))
for st in ["KXFEDDECISION", "KXFED", "KXRECSSNBER", "KXCPIYOY", "KXFEDHIKE"]:
    ev = get("/events", {"series_ticker": st, "status": "open", "with_nested_markets": "true", "limit": 3})
    for e in (ev.get("events") or [])[:2]:
        print("E", st, e.get("event_ticker"), "|", e.get("title"), "|", e.get("sub_title"))
        for m in (e.get("markets") or [])[:12]:
            print("   M", m.get("ticker"), "|", m.get("yes_sub_title") or m.get("subtitle"), "| bid", m.get("yes_bid"), "ask", m.get("yes_ask"), "last", m.get("last_price"), "| bid$", m.get("yes_bid_dollars"), "| vol", m.get("volume"), "| close", m.get("close_time"))
tr = get("/markets/trades", {"limit": 5})
print(json.dumps((tr.get("trades") or [])[:2], indent=1))
