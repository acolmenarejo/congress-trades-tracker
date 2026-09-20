"""Earnings-date cache, backed by FMP (financialmodelingprep.com — same key
as backend/ingestion/sources/fmp_congress.py). One request per ticker gets
its full earnings history (FMP returns decades of quarters), so this is a
fetch-once-per-ticker cache, not a daily-refresh one — new quarters get
appended over time but that's a minor gap, not a correctness issue for
"was this trade near an earnings date" questions about the past.

FMP_API_KEY is only read here, by the batch script
(backend/earnings/scan_earnings.py via GitHub Actions) — the live API
(app/main.py, on Vercel) only ever reads the cache, same division as
prices.py / PriceCache.
"""
import logging
import os
from datetime import date as date_type

import requests
from sqlalchemy.orm import Session

from .models import EarningsCache, EarningsSkip

logger = logging.getLogger("earnings")

FMP_BASE = "https://financialmodelingprep.com/stable"


def _api_key() -> str | None:
    return os.environ.get("FMP_API_KEY")


def has_cached_earnings(db: Session, ticker: str) -> bool:
    """True if we already have data OR already know we can't get any (FMP's
    free plan 402s most tickers outside a curated large-cap list) — either
    way, scan_earnings.py shouldn't spend its daily budget on it again."""
    if db.query(EarningsCache).filter_by(ticker=ticker).first() is not None:
        return True
    return db.query(EarningsSkip).filter_by(ticker=ticker).first() is not None


def fetch_and_cache_earnings(db: Session, ticker: str) -> int:
    """Fetches once and upserts. Returns rows added. No-ops (and returns 0,
    recording a skip so this ticker isn't retried) if FMP_API_KEY isn't set,
    the request fails (most commonly HTTP 402 — this ticker isn't on FMP's
    free-plan symbol list), or it returns no rows."""
    key = _api_key()
    if not key:
        logger.warning("earnings: FMP_API_KEY not set, skipping")
        return 0
    try:
        resp = requests.get(f"{FMP_BASE}/earnings", params={"symbol": ticker, "apikey": key}, timeout=20)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.info("earnings: no access to %s (likely outside FMP's free-plan symbol list)", ticker)
        db.merge(EarningsSkip(ticker=ticker))
        db.commit()
        return 0
    if not isinstance(rows, list) or not rows:
        db.merge(EarningsSkip(ticker=ticker))
        db.commit()
        return 0

    added = 0
    for row in rows:
        date_str = row.get("date")
        if not date_str:
            continue
        try:
            parsed = date_type.fromisoformat(date_str)
        except ValueError:
            continue
        exists = db.query(EarningsCache).filter_by(ticker=ticker, date=parsed).one_or_none()
        if exists:
            continue
        db.add(EarningsCache(ticker=ticker, date=parsed))
        added += 1
    db.commit()
    return added


def get_earnings_dates(db: Session, ticker: str) -> list[str]:
    rows = db.query(EarningsCache).filter_by(ticker=ticker).order_by(EarningsCache.date).all()
    return [r.date.isoformat() for r in rows]
