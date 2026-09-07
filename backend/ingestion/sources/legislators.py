"""Reference data (not trades): current members of Congress, for enriching
Member rows with party/state/chamber/committees that none of the trade feeds
provide. Source: unitedstates/congress-legislators, a well-maintained public-domain
dataset (YAML, no key needed).
"""
import logging

import requests
import yaml

from ingestion import normalize

logger = logging.getLogger(__name__)

LEGISLATORS_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators"
    "/main/legislators-current.yaml"
)
COMMITTEE_MEMBERSHIP_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators"
    "/main/committee-membership-current.yaml"
)
COMMITTEES_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators"
    "/main/committees-current.yaml"
)

_PARTY_MAP = {"Democrat": "D", "Republican": "R", "Independent": "I"}
_CHAMBER_MAP = {"rep": "house", "sen": "senate"}


def _fetch_yaml(url: str, timeout: int = 30):
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return yaml.safe_load(resp.text)


def _committee_names_by_thomas_id(timeout: int = 30) -> dict:
    try:
        committees = _fetch_yaml(COMMITTEES_URL, timeout=timeout)
    except Exception:
        logger.warning("legislators: failed to fetch committees list, skipping committee names")
        return {}
    return {c["thomas_id"]: c["name"] for c in committees if c.get("thomas_id")}


def fetch_enrichment(timeout: int = 30) -> dict:
    """Returns {bioguide_id: {name, party, state, chamber, committees}} plus a
    parallel lookup keyed by our own match_key for trades without a bioguide id."""
    try:
        legislators = _fetch_yaml(LEGISLATORS_URL, timeout=timeout)
    except Exception:
        logger.exception("legislators: failed to fetch legislators-current.yaml")
        return {"by_bioguide": {}, "by_match_key": {}}

    committee_names = _committee_names_by_thomas_id(timeout=timeout)
    try:
        memberships = _fetch_yaml(COMMITTEE_MEMBERSHIP_URL, timeout=timeout)
    except Exception:
        logger.warning("legislators: failed to fetch committee memberships")
        memberships = {}

    committees_by_bioguide: dict[str, list[str]] = {}
    for thomas_id, members in (memberships or {}).items():
        name = committee_names.get(thomas_id, thomas_id)
        for m in members:
            bioguide = m.get("bioguide")
            if bioguide:
                committees_by_bioguide.setdefault(bioguide, []).append(name)

    by_bioguide = {}
    by_match_key = {}
    for legislator in legislators:
        bioguide = legislator.get("id", {}).get("bioguide")
        terms = legislator.get("terms") or []
        if not terms or not bioguide:
            continue
        last_term = terms[-1]
        full_name = legislator.get("name", {}).get("official_full") or (
            f"{legislator['name'].get('first', '')} {legislator['name'].get('last', '')}"
        )
        entry = {
            "name": full_name,
            "party": _PARTY_MAP.get(last_term.get("party"), None),
            "state": last_term.get("state"),
            "chamber": _CHAMBER_MAP.get(last_term.get("type")),
            "committees": ", ".join(committees_by_bioguide.get(bioguide, [])) or None,
        }
        by_bioguide[bioguide] = entry
        by_match_key[normalize.member_match_key(full_name)] = entry

    logger.info("legislators: loaded %d current members", len(by_bioguide))
    return {"by_bioguide": by_bioguide, "by_match_key": by_match_key}
