"""House trade disclosures.

The original housestockwatcher.com project/API is offline (DNS no longer
resolves as of 2026). We use a community-maintained, actively-updated mirror
of the same dataset that publishes the identical normalized JSON format:
https://github.com/TattooedHead/house-stock-watcher-data

If that mirror ever goes down too, swap FEED_URL for another source that
serves the same {"transaction_date","disclosure_date","ticker",...} shape.
"""
import logging

import requests

logger = logging.getLogger(__name__)

FEED_URL = (
    "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data"
    "/main/data/all_transactions.json"
)

SOURCE_NAME = "house_stock_watcher"


def fetch_raw_trades(timeout: int = 60) -> list[dict]:
    try:
        resp = requests.get(FEED_URL, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        logger.exception("house_stock_watcher: failed to fetch feed")
        return []

    out = []
    for row in rows:
        try:
            out.append(
                {
                    "member_name": row.get("representative"),
                    "chamber": "house",
                    "party": None,
                    "state": (row.get("district") or "")[:2] or None,
                    "district": row.get("district"),
                    "ticker": row.get("ticker"),
                    "asset_name": row.get("asset_description"),
                    "asset_type": row.get("asset_type"),
                    "transaction_type": row.get("type"),
                    "owner": row.get("owner"),
                    "amount_raw": row.get("amount"),
                    "transaction_date_raw": row.get("transaction_date"),
                    "disclosure_date_raw": row.get("disclosure_date"),
                    "source": SOURCE_NAME,
                    "filing_url": row.get("source_url"),
                }
            )
        except Exception:
            logger.warning("house_stock_watcher: skipping malformed row: %r", row)
    return out
