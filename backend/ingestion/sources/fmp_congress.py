"""Financial Modeling Prep — live Senate + House STOCK Act disclosures.

Free tier: 250 requests/day, but `page` is locked to 0 on the free plan, so
each call only returns the ~100 most recent disclosures per chamber. That's
fine for us: this is our *live/recent* feed, filling exactly the gap left by
the dead official mirrors (see senate_stock_watcher.py / house_stock_watcher.py
for the historical/backfill sources). Every ingestion run re-fetches the
latest 100 per chamber; dedup by unique_id makes re-fetching harmless.

Requires FMP_API_KEY (free signup at financialmodelingprep.com). If the env
var is missing, or FMP ever gates these endpoints behind a paid plan, this
adapter logs a warning and returns an empty list rather than failing the run.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://financialmodelingprep.com/stable"
SOURCE_NAME = "fmp_congress"

_ENDPOINTS = {
    "senate": "senate-latest",
    "house": "house-latest",
}


def _api_key() -> str | None:
    return os.environ.get("FMP_API_KEY")


def _state_from_district(district: str | None, chamber: str) -> tuple[str | None, str | None]:
    if not district:
        return None, None
    if chamber == "senate":
        return district.strip() or None, None
    return district[:2] or None, district


def _fetch_chamber(chamber: str, api_key: str, timeout: int) -> list[dict]:
    url = f"{BASE_URL}/{_ENDPOINTS[chamber]}"
    try:
        resp = requests.get(url, params={"apikey": api_key, "page": 0}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("fmp_congress: failed to fetch %s feed", chamber)
        return []

    if isinstance(data, dict) and ("Error Message" in data or "message" in data):
        logger.warning("fmp_congress: %s endpoint returned an error/plan-limit response: %r", chamber, data)
        return []
    if not isinstance(data, list):
        logger.warning("fmp_congress: unexpected %s response shape: %r", chamber, type(data))
        return []

    out = []
    for row in data:
        try:
            state, district = _state_from_district(row.get("district"), chamber)
            out.append(
                {
                    "member_name": f"{row.get('firstName', '')} {row.get('lastName', '')}".strip(),
                    "chamber": chamber,
                    "party": None,
                    "state": state,
                    "district": district,
                    "bioguide_id": row.get("senateID"),
                    "ticker": row.get("symbol"),
                    "asset_name": row.get("assetDescription"),
                    "asset_type": row.get("assetType"),
                    "transaction_type": row.get("type"),
                    "owner": row.get("owner"),
                    "amount_raw": row.get("amount"),
                    "transaction_date_raw": row.get("transactionDate"),
                    "disclosure_date_raw": row.get("disclosureDate"),
                    "source": SOURCE_NAME,
                    "filing_url": row.get("link"),
                }
            )
        except Exception:
            logger.warning("fmp_congress: skipping malformed %s row: %r", chamber, row)
    return out


def fetch_raw_trades(timeout: int = 20) -> list[dict]:
    api_key = _api_key()
    if not api_key:
        logger.info("fmp_congress: FMP_API_KEY not set, skipping source")
        return []

    return _fetch_chamber("senate", api_key, timeout) + _fetch_chamber("house", api_key, timeout)
