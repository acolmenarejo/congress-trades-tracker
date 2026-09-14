import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "congress_trades.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# /internal/trigger-poll relays an external pinger's ping into a GitHub
# Actions `workflow_dispatch` call. GitHub Actions' own `schedule:` trigger is
# unreliable at 5-minute granularity in practice (observed multi-hour gaps
# between runs), but workflow_dispatch fires immediately - and the actual
# bot state (subscribers, watches, offset) has to keep being written by that
# GitHub Actions run, not by this endpoint: Vercel's filesystem is read-only
# in production, so this process could never persist an updated offset and
# would just replay the same Telegram messages forever.
CRON_SECRET = os.environ.get("CRON_SECRET")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "acolmenarejo/congress-trades-tracker")

DEFAULT_WATCHED_MEMBERS = [
    ("npelosi", "Nancy Pelosi"),
    ("jgottheimer", "Josh Gottheimer"),
    ("rkhanna", "Ro Khanna"),
    ("dcrenshaw", "Dan Crenshaw"),
    ("mmullin", "Markwayne Mullin"),
]
