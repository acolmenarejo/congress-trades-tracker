"""Senate trade disclosures.

Two data paths, combined:

1. Bulk historical backfill from timothycarambat/senate-stock-watcher-data
   (GitHub-hosted JSON). NOTE: that project stopped scraping in March 2021,
   so this only ever returns trades up to that date. It has no
   `disclosure_date` field, so disclosure_lag_days will be null for these rows.

2. Best-effort "recent" per-day reports from the same repo's `data/` folder,
   which *do* include `date_recieved` (disclosure date) and a bioguide id.
   These files are named `transaction_report_for_MM_DD_YYYY.json`. We probe
   the last N days; because the repo is dead, none will exist today, but the
   code is ready to pick data back up if the repo (or a fork) resumes, and it
   costs nothing extra (404s are cheap and skipped silently).

If a live, actively-maintained Senate feed becomes reachable (efdsearch.senate.gov
itself blocks non-browser traffic with Akamai bot protection from most cloud/CI
IP ranges, so it is not used directly here), swap/extend this module.
"""
import logging
from datetime import date, timedelta

import requests

logger = logging.getLogger(__name__)

AGGREGATE_URL = (
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data"
    "/master/aggregate/all_transactions.json"
)
DAILY_URL_TMPL = (
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data"
    "/master/data/transaction_report_for_{date_str}.json"
)

SOURCE_NAME = "senate_stock_watcher"


def _row_from_aggregate(row: dict) -> dict:
    return {
        "member_name": row.get("senator"),
        "chamber": "senate",
        "party": None,
        "state": None,
        "district": None,
        "ticker": row.get("ticker"),
        "asset_name": row.get("asset_description"),
        "asset_type": row.get("asset_type"),
        "transaction_type": row.get("type"),
        "owner": row.get("owner"),
        "amount_raw": row.get("amount"),
        "transaction_date_raw": row.get("transaction_date"),
        "disclosure_date_raw": None,
        "source": SOURCE_NAME,
        "filing_url": row.get("ptr_link"),
    }


def fetch_bulk_historical(timeout: int = 60) -> list[dict]:
    try:
        resp = requests.get(AGGREGATE_URL, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.exception("senate_stock_watcher: failed to fetch aggregate feed")
        return []

    out = []
    for row in rows:
        if not row.get("ticker") or row.get("ticker") == "N/A":
            continue  # PDF-only filings with no structured data
        try:
            out.append(_row_from_aggregate(row))
        except Exception:
            logger.warning("senate_stock_watcher: skipping malformed row: %r", row)
    return out


def fetch_recent_daily_reports(lookback_days: int = 10, timeout: int = 15) -> list[dict]:
    out = []
    today = date.today()
    for i in range(lookback_days):
        day = today - timedelta(days=i)
        date_str = day.strftime("%m_%d_%Y")
        url = DAILY_URL_TMPL.format(date_str=date_str)
        try:
            resp = requests.get(url, timeout=timeout)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        try:
            filings = resp.json()
        except ValueError:
            continue
        for filing in filings:
            senator = f"{filing.get('first_name', '')} {filing.get('last_name', '')}".strip()
            disclosure_date_raw = filing.get("date_recieved")
            for tx in filing.get("transactions", []):
                try:
                    out.append(
                        {
                            "member_name": senator,
                            "chamber": "senate",
                            "party": None,
                            "state": None,
                            "district": None,
                            "ticker": tx.get("ticker"),
                            "asset_name": tx.get("asset_description"),
                            "asset_type": tx.get("asset_type"),
                            "transaction_type": tx.get("type"),
                            "owner": tx.get("owner"),
                            "amount_raw": tx.get("amount"),
                            "transaction_date_raw": tx.get("transaction_date"),
                            "disclosure_date_raw": disclosure_date_raw,
                            "source": SOURCE_NAME,
                            "filing_url": filing.get("ptr_link"),
                        }
                    )
                except Exception:
                    logger.warning("senate_stock_watcher: skipping malformed tx: %r", tx)
    return out


def fetch_raw_trades() -> list[dict]:
    return fetch_bulk_historical() + fetch_recent_daily_reports()
