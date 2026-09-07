"""Daily OHLC price fetching, backed by PriceCache in SQLite.

Uses Yahoo Finance's chart API directly with a browser User-Agent — the
`yfinance` library's default session gets rate-limited (HTTP 429) from some
networks, but a plain request with a browser UA works reliably, so we skip
the library and talk to the endpoint ourselves.
"""
import logging
import time
from datetime import date, datetime, timedelta

import requests
from sqlalchemy.orm import Session

from app.models import PriceCache

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"

SP500_TICKER = "SPY"


def _fetch_from_yahoo(ticker: str, start: date, end: date) -> list[dict]:
    period1 = int(datetime.combine(start, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time()).timestamp())
    try:
        resp = requests.get(
            _CHART_URL.format(ticker=ticker),
            params={"period1": period1, "period2": period2, "interval": "1d"},
            headers={"User-Agent": _UA},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("prices: failed to fetch %s from Yahoo", ticker)
        return []

    result = (data.get("chart") or {}).get("result")
    if not result:
        return []
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators") or {}).get("quote", [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        close = (quote.get("close") or [])[i] if i < len(quote.get("close", [])) else None
        if close is None:
            continue
        rows.append(
            {
                "date": datetime.utcfromtimestamp(ts).date(),
                "open": (quote.get("open") or [None] * len(timestamps))[i],
                "high": (quote.get("high") or [None] * len(timestamps))[i],
                "low": (quote.get("low") or [None] * len(timestamps))[i],
                "close": close,
                "volume": (quote.get("volume") or [None] * len(timestamps))[i],
            }
        )
    return rows


def get_price_series(db: Session, ticker: str, start: date, end: date, max_age_days: int = 1) -> list[dict]:
    """Returns daily OHLC rows for `ticker` covering [start, end], using the
    cache when it's fresh enough, otherwise refetching the whole range."""
    cached = (
        db.query(PriceCache)
        .filter(PriceCache.ticker == ticker, PriceCache.date >= start, PriceCache.date <= end)
        .order_by(PriceCache.date)
        .all()
    )
    is_fresh = cached and (end - cached[-1].date).days <= max_age_days
    covers_start = cached and cached[0].date <= start + timedelta(days=5)

    if cached and is_fresh and covers_start:
        return [
            {"date": r.date, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume}
            for r in cached
        ]

    fresh_rows = _fetch_from_yahoo(ticker, start, end)
    throttle()  # only sleep when we actually hit the network
    if not fresh_rows:
        # Fall back to whatever we already had cached, better than nothing.
        return [
            {"date": r.date, "open": r.open, "high": r.high, "low": r.low, "close": r.close, "volume": r.volume}
            for r in cached
        ]

    for row in fresh_rows:
        existing = db.query(PriceCache).filter_by(ticker=ticker, date=row["date"]).one_or_none()
        if existing is None:
            db.add(PriceCache(ticker=ticker, **row))
        else:
            for k, v in row.items():
                if k != "date":
                    setattr(existing, k, v)
    db.commit()
    return fresh_rows


def price_on_or_after(series: list[dict], target: date) -> float | None:
    """First close price on or after `target` (fills for weekends/holidays)."""
    for row in series:
        if row["date"] >= target:
            return row["close"]
    return None


def price_on_or_before(series: list[dict], target: date) -> float | None:
    """Last close price on or before `target` — used to approximate 'current
    price' when the series doesn't extend to today (e.g. delisted ticker)."""
    result = None
    for row in series:
        if row["date"] > target:
            break
        result = row["close"]
    return result


def throttle():
    """Be polite to Yahoo's free endpoint between tickers."""
    time.sleep(0.3)
