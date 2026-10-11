"""Kalshi markets on a company's next reported numbers: operating KPIs
(cards in force, deliveries, hours engaged, headcount...) and what will be
said on the earnings call. Polymarket only asks "will EPS beat?", with almost
no money behind it.

Kalshi names these series after the stock ticker: KX{T} (quarter KPI),
KX{T}A (annual KPI) and KXEARNINGSMENTION{T} (earnings call). We only look at
tickers people in this app are buying (Congress in the last year, insiders in
the last 180 days), so a run is one /series listing plus one /events call per
matched series. Result in TelegramState[STORE_KEY] as {ticker: [event...]};
GET /tickers/{t}/kalshi and the ticker page read it.

Money per company is small ($5k-$95k), and an event stays open for months
after its number is out: those read 99%/1% everywhere and are dropped.
"""
import json
import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .kalshi_expect import _NUM, _get_slow
from .models import InsiderTrade, TelegramState, Trade
from .polymarket_macro import KALSHI, _ks_prob

logger = logging.getLogger(__name__)

STORE_KEY = "kalshi_company"
_KPI_TAGS = {"KPIs", "Headcount"}


def _f(m: dict, k: str) -> float | None:
    try:
        v = m.get(k)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def all_series() -> dict[str, dict]:
    out, cursor = {}, None
    for _ in range(30):
        r = _get_slow(f"{KALSHI}/series", {"limit": 1000, **({"cursor": cursor} if cursor else {})})
        for s in r.get("series") or []:
            out[s["ticker"]] = s
        cursor = r.get("cursor")
        if not cursor:
            break
    return out


def universe(db: Session) -> set[str]:
    today = date.today()
    t1 = {t for (t,) in db.query(Trade.ticker).filter(Trade.transaction_date >= today - timedelta(days=365)).distinct() if t}
    t2 = {t for (t,) in db.query(InsiderTrade.ticker).filter(InsiderTrade.transaction_date >= today - timedelta(days=180)).distinct() if t}
    return {t.upper() for t in t1 | t2 if t.isalpha() and len(t) <= 5}


def match_series(tickers: set[str], series: dict[str, dict]) -> list[tuple[str, str, str]]:
    """(stock ticker, series ticker, 'kpi' | 'mention')."""
    out = []
    for t in sorted(tickers):
        for st, kind in ((f"KX{t}", "kpi"), (f"KX{t}A", "kpi"), (f"KXEARNINGSMENTION{t}", "mention")):
            s = series.get(st)
            tags = set(s.get("tags") or []) if s else set()
            if s and ((kind == "kpi" and tags & _KPI_TAGS) or (kind == "mention" and "Earnings" in tags)):
                out.append((t, st, kind))
    return out


def _scale(m: dict) -> tuple[float, str]:
    """'Above 156 million' with floor_strike 156000000 -> (1e6, 'million')."""
    sub = (m.get("yes_sub_title") or "").replace("$", "")
    n, fs = _NUM.search(sub), _f(m, "floor_strike")
    if not n or not fs:
        return 1.0, ""
    shown = float(n.group().replace(",", ""))
    unit = sub[n.end():].strip().split(" ")[0] if sub[n.end():].strip() else ""
    return (fs / shown if shown else 1.0), unit


def _market(m: dict) -> dict:
    p = _ks_prob(m)
    bid, ask = _f(m, "yes_bid_dollars"), _f(m, "yes_ask_dollars")
    return {"ticker": m.get("ticker"), "label": m.get("yes_sub_title"), "p": p,
            "prev": _f(m, "previous_price_dollars"), "last": _f(m, "last_price_dollars"),
            "spread": (ask - bid) if bid is not None and ask is not None else None,
            "oi": _f(m, "open_interest_fp") or 0.0, "strike": _f(m, "floor_strike"),
            "close": m.get("close_time")}


def decided(markets: list[dict]) -> bool:
    ps = [x["p"] for x in markets if x["p"] is not None and x["oi"] > 0]
    return bool(ps) and all(p >= 0.95 or p <= 0.05 for p in ps)


def summarise_kpi(e: dict, markets: list[dict]) -> dict:
    """Median of the 'Above X' ladder and where it sits against the middle
    of Kalshi's own strike range (which is usually set around consensus)."""
    ladder = sorted((x for x in markets if x["strike"] is not None and x["p"] is not None), key=lambda x: x["strike"])
    out = {"median": None, "median_label": None, "lean": None, "lean_text": None}
    if len(ladder) < 3:
        return out
    floor, curve = 1.0, []
    for x in ladder:
        floor = min(floor, x["p"])
        curve.append((x["strike"], floor))
    med = None
    for (x0, p0), (x1, p1) in zip(curve, curve[1:]):
        if p0 >= 0.5 >= p1:
            med = x0 if p0 == p1 else x0 + (p0 - 0.5) / (p0 - p1) * (x1 - x0)
            break
    raw = next((m for m in e.get("markets") or [] if _f(m, "floor_strike")), {})
    scale, unit = _scale(raw)
    pre = "$" if "$" in (raw.get("yes_sub_title") or "") else ""
    if med is not None:
        v = med / scale
        num = f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}".rstrip("0").rstrip(".")
        out["median"] = med
        out["median_label"] = f"{pre}{num}" + ("" if not unit else unit if unit == "%" else f" {unit}")
    # Only a clear-cut "bad number": a growth figure (same-store sales,
    # attendance...) the market thinks is more likely to shrink than grow.
    # Levels (cards, deliveries) have no reference here to call them bad;
    # Kalshi's strike ranges are not centred on consensus (tried: it flagged
    # a quarter of all companies).
    zero = next((x for x in curve if x[0] == 0), None)
    if zero and zero[1] < 0.5:
        out["lean"], out["lean_text"] = "weak", f"El mercado solo da un {zero[1] * 100:.0f}% a que crezca: espera caída."
    return out


def _event(e: dict, kind: str) -> dict | None:
    markets = [_market(m) for m in e.get("markets") or []]
    if not markets or decided(markets):
        return None
    oi = sum(x["oi"] for x in markets)
    if oi < 100:
        return None
    ev = {"event": e.get("event_ticker"), "series": e.get("series_ticker"), "kind": kind,
          "title": e.get("title"), "sub_title": e.get("sub_title"), "oi": round(oi),
          "url": f"https://kalshi.com/markets/{(e.get('series_ticker') or '').lower()}"}
    if kind == "kpi":
        ev.update(summarise_kpi(e, markets))
        keep = sorted((x for x in markets if x["p"] is not None and 0.03 <= x["p"] <= 0.97), key=lambda x: x["strike"] or 0)
    else:
        keep = sorted((x for x in markets if x["p"] is not None), key=lambda x: -x["oi"])[:10]
    ev["markets"] = [{k: x[k] for k in ("ticker", "label", "p", "prev", "last", "spread", "oi", "close")} for x in keep]
    return ev


def fetch(db: Session, series: dict[str, dict] | None = None) -> dict[str, list[dict]]:
    series = series if series is not None else all_series()
    store: dict[str, list[dict]] = {}
    for t, st, kind in match_series(universe(db), series):
        try:
            r = _get_slow(f"{KALSHI}/events", {"series_ticker": st, "status": "open", "with_nested_markets": "true", "limit": 20})
        except Exception:
            logger.exception("kalshi_company: %s failed", st)
            continue
        for e in r.get("events") or []:
            ev = _event(e, kind)
            if ev:
                store.setdefault(t, []).append(ev)
    for evs in store.values():
        evs.sort(key=lambda e: (e["kind"] != "kpi", -e["oi"]))
    db.merge(TelegramState(key=STORE_KEY, value=json.dumps(store)))
    db.commit()
    logger.info("kalshi_company: %d tickers, %d events", len(store), sum(len(v) for v in store.values()))
    return store


def load(db: Session) -> dict[str, list[dict]]:
    st = db.get(TelegramState, STORE_KEY)
    try:
        return json.loads(st.value) if st and st.value else {}
    except ValueError:
        return {}
