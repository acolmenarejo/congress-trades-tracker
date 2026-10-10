"""What Polymarket bettors expect on macro questions (next Fed decision, a
Fed hike this year, US recession, next CPI print), to cross-check against
what the bond market says on the Macro page (app/macro.py).

Fetched hourly from polymarket.yml (gamma-api, no key). Probabilities go
into MacroPoint as series PM_* (one value per day, the latest of the day),
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

    today = date.today()
    for sid, v in values.items():
        db.merge(MacroPoint(series=sid, date=today, value=v))
    db.merge(TelegramState(key=META_KEY, value=json.dumps(meta)))
    db.commit()
    logger.info("polymarket_macro: %s", values)
    return values


def load_meta(db: Session) -> dict:
    st = db.get(TelegramState, META_KEY)
    try:
        return json.loads(st.value) if st and st.value else {}
    except ValueError:
        return {}
