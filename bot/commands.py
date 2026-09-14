"""Standalone entrypoint for local dev / the GitHub Actions fallback cron.
The real logic lives in backend/app/bot_commands.py (also used by the
/internal/poll endpoint on Vercel, which is the reliable low-latency path —
see that module's docstring and the README).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from app.bot_commands import process_updates  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    process_updates()
