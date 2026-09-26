import logging
import os
import shutil
import threading
import time

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from .config import DATABASE_URL, DB_PATH, GITHUB_REPO

logger = logging.getLogger(__name__)

# On Vercel the bundled DB is a snapshot from the last manual `vercel deploy`,
# while GitHub Actions keeps committing fresh data to the repo — so the site
# silently froze at deploy time. Instead, serve a copy in /tmp (the only
# writable path there) that is re-pulled from the public repo whenever it's
# older than LIVE_DB_TTL_SECONDS. The bundled file is only the fallback.
LIVE_DB = bool(os.environ.get("VERCEL")) and "DATABASE_URL" not in os.environ
LIVE_DB_PATH = os.environ.get("LIVE_DB_PATH", "/tmp/congress_trades.db")
LIVE_DB_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/master/backend/data/congress_trades.db"
)
LIVE_DB_TTL_SECONDS = 30 * 60

_refresh_lock = threading.Lock()
_last_check = 0.0
_etag: str | None = None


def ensure_fresh_db() -> None:
    """Download the latest DB into /tmp if our copy is missing or stale. Cheap
    when nothing changed (conditional GET → 304). Never raises: on any failure
    it keeps the current /tmp copy, or seeds it from the bundled snapshot."""
    global _last_check, _etag
    if not LIVE_DB or time.time() - _last_check < LIVE_DB_TTL_SECONDS:
        return
    with _refresh_lock:
        if time.time() - _last_check < LIVE_DB_TTL_SECONDS:
            return
        have_copy = os.path.exists(LIVE_DB_PATH)
        try:
            headers = {"If-None-Match": _etag} if (_etag and have_copy) else {}
            resp = requests.get(LIVE_DB_URL, headers=headers, timeout=20)
            if resp.status_code == 200 and resp.content[:16] == b"SQLite format 3\x00":
                tmp = LIVE_DB_PATH + ".part"
                with open(tmp, "wb") as f:
                    f.write(resp.content)
                # Atomic swap: sessions already open keep reading the old file.
                os.replace(tmp, LIVE_DB_PATH)
                _etag = resp.headers.get("ETag")
                logger.info("live db: refreshed from GitHub (%d bytes)", len(resp.content))
            elif resp.status_code != 304:
                logger.warning("live db: unexpected response %s from GitHub", resp.status_code)
        except Exception:
            logger.exception("live db: refresh from GitHub failed")
        if not os.path.exists(LIVE_DB_PATH):
            shutil.copyfile(DB_PATH, LIVE_DB_PATH)
            logger.warning("live db: using the bundled snapshot")
        _last_check = time.time()


if LIVE_DB:
    # NullPool: every session opens the file fresh, so it sees the swapped-in
    # copy instead of a pooled connection pinned to the old one.
    engine = create_engine(
        f"sqlite:///{LIVE_DB_PATH}", connect_args={"check_same_thread": False}, poolclass=NullPool
    )
else:
    connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    ensure_fresh_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401

    # Must run before create_all, or SQLite would create an empty file at
    # LIVE_DB_PATH and we'd serve that.
    ensure_fresh_db()
    Base.metadata.create_all(bind=engine)
