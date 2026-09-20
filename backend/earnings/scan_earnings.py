"""Thin entrypoint — real logic lives in app/earnings.py.

Fetches earnings history for tickers that appear in recent trades and
don't have any cached data yet. Capped per run (MAX_NEW_TICKERS_PER_RUN) to
stay well within FMP's free-tier daily request budget, which is shared with
ingestion/sources/fmp_congress.py's own daily runs.

Usage:
    python scan_earnings.py
"""
import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from app.database import SessionLocal, init_db  # noqa: E402
from app.earnings import fetch_and_cache_earnings, has_cached_earnings  # noqa: E402
from app.models import Trade  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("scan_earnings")

LOOKBACK_DAYS = 730  # same window the ranking/return calc cares about
MAX_NEW_TICKERS_PER_RUN = 40


def run() -> dict:
    init_db()
    db = SessionLocal()
    stats = {"tickers_checked": 0, "tickers_fetched": 0, "rows_added": 0}
    try:
        cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
        tickers = [
            t
            for (t,) in db.query(Trade.ticker)
            .filter(Trade.transaction_date >= cutoff, Trade.ticker.isnot(None))
            .distinct()
            .all()
        ]
        stats["tickers_checked"] = len(tickers)

        for ticker in tickers:
            if stats["tickers_fetched"] >= MAX_NEW_TICKERS_PER_RUN:
                break
            if has_cached_earnings(db, ticker):
                continue
            added = fetch_and_cache_earnings(db, ticker)
            stats["tickers_fetched"] += 1
            stats["rows_added"] += added
            logger.info("earnings: %s -> %d dates", ticker, added)
    finally:
        db.close()

    logger.info(
        "DONE tickers_checked=%d tickers_fetched=%d rows_added=%d",
        stats["tickers_checked"], stats["tickers_fetched"], stats["rows_added"],
    )
    return stats


if __name__ == "__main__":
    run()
