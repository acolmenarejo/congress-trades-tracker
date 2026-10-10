"""Thin entrypoint — real logic lives in app/polymarket.py (see that file's
docstring for why, and for what this actually detects/doesn't detect).

Usage:
    python scan_whale_bets.py            # since the last trade seen
    python scan_whale_bets.py --hours 72 # backfill; stored for the web, no Telegram
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import PolymarketAlert  # noqa: E402
from app import polymarket_macro  # noqa: E402
from app.polymarket import notify, scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        hours = int(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 0
        scan(db, backfill_hours=hours)
        if hours:
            # Old bets are not news: record them for the web without alerting.
            db.query(PolymarketAlert).filter(PolymarketAlert.notified.is_(False)).update({"notified": True})
            db.commit()
        else:
            notify(db)
        try:
            polymarket_macro.fetch(db)  # odds for the Macro page cross-check
        except Exception:
            logging.exception("polymarket_macro failed")
    finally:
        db.close()
