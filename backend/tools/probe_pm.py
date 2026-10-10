import json, requests
G = "https://gamma-api.polymarket.com"
def get(p, q):
    r = requests.get(G + p, params=q, timeout=30); print("GET", r.url, r.status_code); return r.json()
for tag in ["fed", "fed-rates", "economy", "inflation", "recession", "economic-policy"]:
    ev = get("/events", {"tag_slug": tag, "closed": "false", "limit": 40, "order": "volume", "ascending": "false"})
    print(tag, len(ev) if isinstance(ev, list) else ev)
    for e in (ev if isinstance(ev, list) else [])[:25]:
        print("  ", e.get("slug"), "|", e.get("title"), "| end", e.get("endDate"), "| vol", round(float(e.get("volume") or 0)), "| n", len(e.get("markets") or []))
for q in ["fed decision", "recession", "cpi", "inflation"]:
    try:
        r = get("/public-search", {"q": q, "limit_per_type": 10, "events_status": "active"})
        for e in (r.get("events") or [])[:10]:
            print("  S", q, "|", e.get("slug"), "|", e.get("title"), "| end", e.get("endDate"))
    except Exception as ex:
        print("search err", ex)
ev = get("/events", {"tag_slug": "fed", "closed": "false", "limit": 5, "order": "endDate", "ascending": "true"})
if ev:
    e = ev[0]; print(json.dumps({k: e.get(k) for k in ("slug","title","endDate")}))
    for m in e.get("markets", []):
        print("   m", m.get("question"), m.get("groupItemTitle"), m.get("outcomes"), m.get("outcomePrices"), m.get("closed"), m.get("active"))
