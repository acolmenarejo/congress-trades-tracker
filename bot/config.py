import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# Default watchlist for every new subscriber (match_key computed the same way
# ingestion/normalize.py does: first-initial + last-name, lowercase).
DEFAULT_WATCHED_MEMBERS = [
    ("npelosi", "Nancy Pelosi"),
    ("jgottheimer", "Josh Gottheimer"),
    ("rkhanna", "Ro Khanna"),
    ("dcrenshaw", "Dan Crenshaw"),
    ("mmullin", "Markwayne Mullin"),
]
