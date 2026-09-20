"""Thin entrypoint — real logic lives in app/polymarket.py (see that file's
docstring for why, and for what this actually detects/doesn't detect).

Usage:
    python scan_whale_bets.py
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
from app.polymarket import scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        scan(db)
    finally:
        db.close()
