"""Thin entrypoint — real logic in app/insiders.py. Runs from insiders.yml
with --force (the workflow schedule does the throttling; without --force,
scan() skips if the last scan was < 30 min ago).

Usage:
    python scan_insiders.py [--force]
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
from app.insiders import notify, scan  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        scan(db, force="--force" in sys.argv)
        notify(db)
    finally:
        db.close()
