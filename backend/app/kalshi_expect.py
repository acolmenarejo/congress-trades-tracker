"""What Kalshi's money expects on questions Polymarket has no liquid market
for: next jobs report, unemployment, GDP, monthly CPI, core CPI, PCE, the Fed
rate after each of the next two meetings, a recession in 2027, where the
S&P 500 ends the year and how far oil can spike or fall by December.

Checked 2026-10-10 (backend/tools probes): these series carry real volume
(S&P year-end 7.5M, WTI high 9M, recession 2027 0.66M, CPI 1.2M contracts),
unlike Polymarket's thin versions. Kalshi trades are anonymous and small
(largest in 72 h across these markets: $20k), so there is no "suspicious
bet" angle here: the value is the prices themselves and how they move.

Fetched hourly from polymarket.yml next to app/polymarket_macro.py. Each
reading is stored as a KS_* series in MacroPoint (one value per day) and
the event titles in TelegramState[META_KEY]; app/macro.py turns them into
the "Lo que descuenta Kalshi" block and the early-warning statuses.
"""
import json
import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from .models import MacroPoint, TelegramState
from .polymarket import _get
from .polymarket_macro import KALSHI, _ks_prob

logger = logging.getLogger(__name__)

META_KEY = "kalshi_expect"

_NUM = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _num(text: str) -> float | None:
    m = _NUM.search((text or "").replace("$", ""))
    return float(m.group().replace(",", "")) if m else None


def _events(series: str) -> list[dict]:
    r = _get(f"{KALSHI}/events", {"series_ticker": series, "status": "open", "with_nested_markets": "true", "limit": 20})
    evs = [e for e in r.get("events") or [] if e.get("markets")]
    return sorted(evs, key=lambda e: min(m.get("close_time") or "9" for m in e["markets"]))


def _above_curve(e: dict) -> list[tuple[float, float]]:
    """(threshold, P(value above it)) from an "Above X" ladder, sorted by
    threshold and forced non-increasing (bid/ask mids can cross)."""
    pts = []
    for m in e.get("markets") or []:
        x, p = _num(m.get("yes_sub_title") or ""), _ks_prob(m)
        if x is not None and p is not None:
            pts.append((x, p))
    pts.sort()
    out, floor = [], 1.0
    for x, p in pts:
        floor = min(floor, p)
        out.append((x, floor))
    return out


def _median(curve: list[tuple[float, float]]) -> float | None:
    """Value where P(above) crosses 50%, linearly interpolated."""
    for (x0, p0), (x1, p1) in zip(curve, curve[1:]):
        if p0 >= 0.5 >= p1:
            return x0 if p0 == p1 else x0 + (p0 - 0.5) / (p0 - p1) * (x1 - x0)
    return None


def _p_above(curve: list[tuple[float, float]], x: float) -> float | None:
    for (x0, p0), (x1, p1) in zip(curve, curve[1:]):
        if x0 <= x <= x1:
            return p0 + (x - x0) / (x1 - x0) * (p1 - p0) if x1 != x0 else p0
    return None


def _ranges(e: dict) -> list[tuple[float, float, float]]:
    """(low, high, prob) buckets from "7,800 to 7,999.99" / "X or below" /
    "X or above" markets, normalised to sum 1."""
    rows = []
    for m in e.get("markets") or []:
        t, p = (m.get("yes_sub_title") or ""), _ks_prob(m)
        nums = [float(n.replace(",", "")) for n in _NUM.findall(t.replace("$", ""))]
        if p is None or not nums:
            continue
        if "below" in t:
            rows.append((float("-inf"), nums[0], p))
        elif "above" in t:
            rows.append((nums[0], float("inf"), p))
        elif len(nums) >= 2:
            rows.append((nums[0], nums[1], p))
    total = sum(r[2] for r in rows)
    return sorted((lo, hi, p / total) for lo, hi, p in rows) if total else []


def _range_median(rows) -> float | None:
    acc = 0.0
    for lo, hi, p in rows:
        if acc + p >= 0.5 and p:
            if lo == float("-inf") or hi == float("inf"):
                return hi if lo == float("-inf") else lo
            return lo + (0.5 - acc) / p * (hi - lo)
        acc += p
    return None


def _range_p_below(rows, x: float) -> float:
    acc = 0.0
    for lo, hi, p in rows:
        if hi <= x:
            acc += p
        elif lo < x:
            acc += p * (x - lo) / (hi - lo) if hi != float("inf") and lo != float("-inf") else 0
    return acc


def fetch(db: Session, spx_now: float | None = None) -> dict[str, float]:
    values: dict[str, float] = {}
    meta: dict = {}
    year = date.today().year

    def first(series):
        evs = _events(series)
        return evs[0] if evs else None

    def note(key, e):
        meta[key] = {"title": e.get("title"), "ticker": e.get("event_ticker"), "series": e.get("series_ticker")}

    ladders = [  # key, series, how many upcoming events
        ("PAYROLLS", "KXPAYROLLS"), ("U3", "KXU3"), ("GDP", "KXGDP"), ("CPI", "KXCPI"),
        ("CORECPI", "KXCPICOREYOY"), ("PCE", "KXPCEHEAD"),
    ]
    for key, series in ladders:
        try:
            e = first(series)
            med = _median(_above_curve(e)) if e else None
            if med is not None:
                values[f"KS_{key}_MED"] = med
                note(key, e)
                if key == "PAYROLLS":
                    p0 = _p_above(_above_curve(e), 0)
                    if p0 is not None:
                        values["KS_PAYROLLS_NEG"] = 1 - p0
        except Exception:
            logger.exception("kalshi_expect: %s failed", series)

    try:  # Fed funds after each of the next two meetings
        for i, e in enumerate(_events("KXFED")[:2], 1):
            med = _median(_above_curve(e))
            if med is not None:
                values[f"KS_FED{i}_MED"] = med
                note(f"FED{i}", e)
    except Exception:
        logger.exception("kalshi_expect: KXFED failed")

    try:  # recession next year (this year's is already in polymarket_macro)
        for e in _events("KXRECSSNBER"):
            if (e.get("event_ticker") or "").endswith(str(year + 1)[-2:]):
                p = _ks_prob(e["markets"][0])
                if p is not None:
                    values["KS_RECESSION_NEXT"] = p
                    note("RECESSION_NEXT", e)
    except Exception:
        logger.exception("kalshi_expect: recession failed")

    try:  # S&P 500 year-end distribution
        for e in _events("KXINXY"):
            if str(year)[-2:] + "DEC31" in (e.get("event_ticker") or ""):
                rows = _ranges(e)
                med = _range_median(rows)
                if med is not None:
                    values["KS_SPX_MED"] = med
                    note("SPX", e)
                    if spx_now:
                        values["KS_SPX_DROP10"] = _range_p_below(rows, spx_now * 0.9)
    except Exception:
        logger.exception("kalshi_expect: S&P failed")

    try:  # oil tails by year end
        for series, key, level in (("KXWTIMAX", "WTI_HIGH", 120), ("KXWTIMIN", "WTI_LOW", 65)):
            evs = [e for e in _events(series) if "DEC31" in (e.get("event_ticker") or "")]
            if not evs:
                continue
            pts = {}  # "$120.01 or above" for highs, "64.99 or below" for lows
            for m in evs[0].get("markets") or []:
                x, p = _num(m.get("yes_sub_title") or ""), _ks_prob(m)
                if x is not None and p is not None:
                    pts[round(x)] = p
            near = min(pts, key=lambda x: abs(x - level)) if pts else None
            if near is not None and abs(near - level) <= 3:
                values[f"KS_{key}"] = pts[near]
                meta[key] = {"title": evs[0].get("title"), "ticker": evs[0].get("event_ticker"),
                             "series": series, "level": near}
    except Exception:
        logger.exception("kalshi_expect: oil failed")

    today = date.today()
    for sid, v in values.items():
        db.merge(MacroPoint(series=sid, date=today, value=v))
    db.merge(TelegramState(key=META_KEY, value=json.dumps(meta)))
    db.commit()
    logger.info("kalshi_expect: %s", values)
    return values


def load_meta(db: Session) -> dict:
    st = db.get(TelegramState, META_KEY)
    try:
        return json.loads(st.value) if st and st.value else {}
    except ValueError:
        return {}
