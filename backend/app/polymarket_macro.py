"""What prediction markets expect on macro questions (next Fed decision, a
Fed hike this year, US recession, next CPI print), to cross-check against
what the bond market says on the Macro page (app/macro.py), and Polymarket
against Kalshi (the regulated US exchange, public market data, no key).

Fetched hourly from polymarket.yml (gamma-api, no key). Probabilities go
into MacroPoint as series PM_* / KS_* (one value per day, the latest of the day),
and the market titles/links into TelegramState[META_KEY] as JSON. Events are
found by title pattern rather than fixed slugs, since Polymarket opens a
new event per meeting/month.
"""
import json
import logging
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from .models import MacroPoint, TelegramState
from .polymarket import GAMMA_BASE, _get

logger = logging.getLogger(__name__)

META_KEY = "polymarket_macro"
TAGS = ("fed", "economy", "inflation")

FED_NEXT = re.compile(r"^Fed Decision in \w+\?$", re.I)
FED_HIKE_YEAR = re.compile(r"^Another Fed rate hike in \d{4}\?$", re.I)
RECESSION = re.compile(r"^US recession by end of \d{4}\?$", re.I)
CPI = re.compile(r"^\w+ Inflation US - Annual$", re.I)


def _yes(m: dict) -> float | None:
    try:
        outcomes = json.loads(m.get("outcomes") or "[]")
        prices = json.loads(m.get("outcomePrices") or "[]")
        return float(prices[outcomes.index("Yes")]) if "Yes" in outcomes else float(prices[0])
    except (ValueError, IndexError, TypeError):
        return None


def _label(m: dict) -> str:
    return (m.get("groupItemTitle") or m.get("question") or "").strip()


def _soonest(events: list[dict], pattern: re.Pattern, now: datetime) -> dict | None:
    future = []
    for e in events:
        if not pattern.match((e.get("title") or "").strip()):
            continue
        try:
            end = datetime.fromisoformat((e.get("endDate") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if end > now:
            future.append((end, e))
    return min(future, key=lambda x: x[0])[1] if future else None


def _open_markets(e: dict) -> list[dict]:
    return [m for m in e.get("markets") or [] if not m.get("closed")]


def fed_split(e: dict) -> dict:
    """Probabilities of cut / hold / hike from a 'Fed Decision in X?' event."""
    out = {"cut": 0.0, "hold": 0.0, "hike": 0.0}
    for m in _open_markets(e):
        p, lab = _yes(m), _label(m).lower()
        if p is None:
            continue
        if re.search(r"decrease|cut", lab):
            out["cut"] += p
        elif re.search(r"increase|hike", lab):
            out["hike"] += p
        elif "no change" in lab:
            out["hold"] += p
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total else {}


def cpi_buckets(e: dict) -> list[dict]:
    rows = []
    for m in _open_markets(e):
        p = _yes(m)
        if p is not None:
            rows.append({"label": _label(m), "p": p})
    total = sum(r["p"] for r in rows)
    return sorted(({"label": r["label"], "p": r["p"] / total} for r in rows), key=lambda r: -r["p"]) if total else []


def fetch(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    events: dict[str, dict] = {}
    for tag in TAGS:
        try:
            for e in _get(f"{GAMMA_BASE}/events", {"tag_slug": tag, "closed": "false", "limit": 100}):
                events[e.get("slug")] = e
        except Exception:
            logger.exception("polymarket_macro: tag %s failed", tag)
    evs = list(events.values())
    meta: dict = {"updated": now.isoformat()}
    values: dict[str, float] = {}

    e = _soonest(evs, FED_NEXT, now)
    if e:
        split = fed_split(e)
        if split:
            values.update({"PM_FED_CUT": split["cut"], "PM_FED_HOLD": split["hold"], "PM_FED_HIKE": split["hike"]})
            meta["fed_next"] = {"title": e["title"], "slug": e["slug"], "end": e.get("endDate")}
    e = _soonest(evs, FED_HIKE_YEAR, now)
    if e and _open_markets(e) and _yes(_open_markets(e)[0]) is not None:
        values["PM_FED_HIKE_YEAR"] = _yes(_open_markets(e)[0])
        meta["fed_hike_year"] = {"title": e["title"], "slug": e["slug"]}
    e = _soonest(evs, RECESSION, now)
    if e and _open_markets(e) and _yes(_open_markets(e)[0]) is not None:
        values["PM_RECESSION"] = _yes(_open_markets(e)[0])
        meta["recession"] = {"title": e["title"], "slug": e["slug"]}
    e = _soonest(evs, CPI, now)
    if e:
        buckets = cpi_buckets(e)
        if buckets:
            meta["cpi"] = {"title": e["title"], "slug": e["slug"], "buckets": buckets[:4]}

    values.update(kalshi(meta))

    today = date.today()
    for sid, v in values.items():
        db.merge(MacroPoint(series=sid, date=today, value=v))
    db.merge(TelegramState(key=META_KEY, value=json.dumps(meta)))
    db.commit()
    logger.info("polymarket_macro: %s", values)
    return values


KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _ks_prob(m: dict) -> float | None:
    """Mid of bid/ask when both exist, else last trade, else bid."""
    def f(k):
        try:
            v = m.get(k)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    bid, ask, last = f("yes_bid_dollars"), f("yes_ask_dollars"), f("last_price_dollars")
    if bid is not None and ask is not None and ask > 0:
        return (bid + ask) / 2
    return last if last is not None else bid


def _ks_events(series: str) -> list[dict]:
    r = _get(f"{KALSHI}/events", {"series_ticker": series, "status": "open", "with_nested_markets": "true", "limit": 20})
    evs = r.get("events") or []
    return sorted(evs, key=lambda e: min((m.get("close_time") or "9") for m in e.get("markets") or [{}]))


def kalshi(meta: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    ks: dict = {}
    year = date.today().year
    try:
        evs = _ks_events("KXFEDDECISION")
        if evs:
            e, split = evs[0], {"cut": 0.0, "hold": 0.0, "hike": 0.0}
            for m in e.get("markets") or []:
                p, lab = _ks_prob(m), (m.get("yes_sub_title") or "").lower()
                if p is None:
                    continue
                key = "cut" if "cut" in lab else "hike" if "hike" in lab else "hold" if "maintain" in lab else None
                if key:
                    split[key] += p
            total = sum(split.values())
            if total:
                values.update({f"KS_FED_{k.upper()}": v / total for k, v in split.items()})
                ks["fed_next"] = {"title": e.get("title"), "ticker": e.get("event_ticker")}
    except Exception:
        logger.exception("kalshi: fed decision failed")
    try:
        for e in _ks_events("KXFEDHIKE"):
            for m in e.get("markets") or []:
                if (m.get("yes_sub_title") or "").strip() == f"Before {year + 1}" and _ks_prob(m) is not None:
                    values["KS_FED_HIKE_YEAR"] = _ks_prob(m)
                    ks["fed_hike_year"] = {"title": f"{e.get('title')} ({m.get('yes_sub_title')})", "ticker": e.get("event_ticker")}
    except Exception:
        logger.exception("kalshi: fed hike failed")
    try:
        for e in _ks_events("KXRECSSNBER"):
            if str(year)[-2:] == (e.get("event_ticker") or "")[-2:] and e.get("markets"):
                p = _ks_prob(e["markets"][0])
                if p is not None:
                    values["KS_RECESSION"] = p
                    ks["recession"] = {"title": e.get("title"), "ticker": e.get("event_ticker")}
    except Exception:
        logger.exception("kalshi: recession failed")
    try:
        evs = _ks_events("KXCPIYOY")
        if evs:
            e = evs[0]
            above = []
            for m in e.get("markets") or []:
                mt = re.search(r"([\d.]+)%", m.get("yes_sub_title") or "")
                if mt and _ks_prob(m) is not None:
                    above.append((float(mt.group(1)), _ks_prob(m)))
            above.sort()
            # "Above x" thresholds → probability the print lands on each 0.1 step
            buckets = [{"label": f"{hi:.1f}%", "p": max(0.0, above[i - 1][1] - p)}
                       for i, (hi, p) in enumerate(above) if i > 0]
            total = sum(b["p"] for b in buckets)
            if total:
                ks["cpi"] = {"title": e.get("title"), "ticker": e.get("event_ticker"),
                             "buckets": sorted(({"label": b["label"], "p": b["p"] / total} for b in buckets),
                                               key=lambda b: -b["p"])[:4]}
    except Exception:
        logger.exception("kalshi: cpi failed")
    meta["kalshi"] = ks
    return values


def load_meta(db: Session) -> dict:
    st = db.get(TelegramState, META_KEY)
    try:
        return json.loads(st.value) if st and st.value else {}
    except ValueError:
        return {}
