"""Thin entrypoint — real logic in app/setups.py. Runs daily after the US
close via setups.yml.

Usage:
    python scan_setups.py
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
from app.setups import scan_and_alert  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        logging.info("setups: %s", scan_and_alert(db))
    finally:
        db.close()
