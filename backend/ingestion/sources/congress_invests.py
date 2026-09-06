"""CongressInvests.com — free aggregator of both chambers (100 req/day, no key).

STATUS: as of this writing the host times out from our sandbox/dev network
(TCP connect timeout, not a 4xx/5xx — looks like a network-level block rather
than the service being down, since the domain resolves via Cloudflare). It may
still be reachable from GitHub Actions runners or Railway/Fly, which sit on
different egress ranges. This adapter is defensive: any failure (timeout,
non-200, unexpected shape) is caught, logged, and results in an empty list so
the rest of the pipeline (House + Senate sources) keeps working.

We haven't been able to confirm the exact response schema by hand (the site
was unreachable during development), so field mapping below is best-effort
across a few plausible key names. If/when this adapter actually gets a live
response for the first time, log the raw payload once and adjust
`_map_row` to match reality.
"""
import logging

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://congressinvests.com/api/trades"
SOURCE_NAME = "congress_invests"


def _first(row: dict, *keys):
    for k in keys:
        if row.get(k) not in (None, ""):
            return row.get(k)
    return None


def _map_row(row: dict) -> dict:
    chamber_raw = (_first(row, "chamber", "office") or "").lower()
    chamber = "senate" if "sen" in chamber_raw else ("house" if "house" in chamber_raw or "rep" in chamber_raw else None)
    return {
        "member_name": _first(row, "member", "name", "politician", "representative", "senator"),
        "chamber": chamber,
        "party": _first(row, "party"),
        "state": _first(row, "state"),
        "district": _first(row, "district"),
        "ticker": _first(row, "ticker", "symbol"),
        "asset_name": _first(row, "asset_name", "asset_description", "asset"),
        "asset_type": _first(row, "asset_type"),
        "transaction_type": _first(row, "transaction_type", "type"),
        "owner": _first(row, "owner"),
        "amount_raw": _first(row, "amount", "amount_range"),
        "transaction_date_raw": _first(row, "transaction_date", "traded"),
        "disclosure_date_raw": _first(row, "disclosure_date", "filed", "published"),
        "source": SOURCE_NAME,
        "filing_url": _first(row, "filing_url", "url", "source_url"),
    }


def fetch_raw_trades(timeout: int = 20) -> list[dict]:
    try:
        resp = requests.get(BASE_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("congress_invests: unreachable or failed (%s) — skipping source", exc)
        return []

    rows = data if isinstance(data, list) else data.get("trades") or data.get("data") or []
    out = []
    for row in rows:
        try:
            out.append(_map_row(row))
        except Exception:
            logger.warning("congress_invests: skipping malformed row: %r", row)
    return out
