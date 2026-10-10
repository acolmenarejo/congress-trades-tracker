"""Thin entrypoint — real logic lives in app/macro.py. Run by macro.yml.

Usage:
    python fetch_macro.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db  # noqa: E402
from app.macro import refresh  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        stats = refresh(db)
        if not any(stats.values()):
            sys.exit("macro: no series could be fetched")
    finally:
        db.close()
