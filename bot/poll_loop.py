"""Dev-only convenience: poll Telegram in a loop instead of running commands.py
once per cron tick. NOT what runs in production (see .github/workflows/) —
just for interactive testing so replies feel instant.
"""
import time

from commands import process_updates

if __name__ == "__main__":
    print("Polling Telegram every 5s (Ctrl+C to stop)...", flush=True)
    while True:
        process_updates()
        time.sleep(5)
