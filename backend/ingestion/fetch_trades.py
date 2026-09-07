"""Idempotent ingestion entrypoint.

Pulls trades from all configured sources, normalizes and deduplicates them,
and upserts into SQLite. Safe to run repeatedly (e.g. every few hours from
GitHub Actions) — existing rows are matched by `unique_id` and updated in
place rather than duplicated.

Usage:
    python fetch_trades.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Member, Trade  # noqa: E402

from ingestion import normalize  # noqa: E402
from ingestion.sources import (  # noqa: E402
    congress_invests,
    fmp_congress,
    house_stock_watcher,
    legislators,
    senate_stock_watcher,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fetch_trades")

# fmp_congress first: it's the freshest/live source (with bioguide ids), so it
# "wins" as the base row for recent trades. The historical mirrors only add
# older trades / fill gaps, they don't overwrite what fmp_congress already set.
SOURCES = [fmp_congress, house_stock_watcher, senate_stock_watcher, congress_invests]


def normalize_row(raw: dict) -> dict | None:
    match_key = normalize.member_match_key(raw.get("member_name"))
    member_name = normalize.clean_name(raw.get("member_name"))
    if not member_name or not raw.get("ticker"):
        return None

    ticker = normalize.strip_html(raw.get("ticker")).upper().strip()
    if not ticker or ticker in {"N/A", "--"}:
        return None

    transaction_type = normalize.normalize_transaction_type(raw.get("transaction_type"))
    transaction_date = normalize.parse_date(raw.get("transaction_date_raw"))
    disclosure_date = normalize.parse_date(raw.get("disclosure_date_raw"))
    amount_low, amount_high = normalize.parse_amount_range(raw.get("amount_raw"))
    amount_mid = (
        (amount_low + amount_high) / 2
        if amount_low is not None and amount_high is not None
        else (amount_low if amount_low is not None else amount_high)
    )

    disclosure_lag_days = None
    if transaction_date and disclosure_date:
        disclosure_lag_days = (disclosure_date - transaction_date).days

    unique_id = normalize.make_unique_id(
        match_key, raw.get("chamber"), ticker, transaction_type, transaction_date, amount_low, amount_high
    )

    return {
        "unique_id": unique_id,
        "member_match_key": match_key,
        "member_name": member_name,
        "chamber": raw.get("chamber"),
        "party": normalize.normalize_party(raw.get("party")),
        "state": raw.get("state"),
        "ticker": ticker,
        "asset_name": normalize.clean_text(raw.get("asset_name")),
        "asset_type": raw.get("asset_type"),
        "transaction_type": transaction_type,
        "owner": raw.get("owner"),
        "amount_range_low": amount_low,
        "amount_range_high": amount_high,
        "amount_mid": amount_mid,
        "transaction_date": transaction_date,
        "disclosure_date": disclosure_date,
        "disclosure_lag_days": disclosure_lag_days,
        "source": raw.get("source"),
        "filing_url": raw.get("filing_url"),
        "district": raw.get("district"),
        "bioguide_id": raw.get("bioguide_id"),
    }


def upsert_member(db, row: dict, member_cache: dict) -> None:
    match_key = row["member_match_key"]
    member = member_cache.get(match_key)
    if member is None:
        member = db.query(Member).filter_by(match_key=match_key).one_or_none()
    if member is None:
        member = Member(
            match_key=match_key,
            name=row["member_name"],
            chamber=row["chamber"],
            party=row["party"],
            state=row["state"],
            district=row.get("district"),
            bioguide_id=row.get("bioguide_id"),
            committees=row.get("committees"),
        )
        db.add(member)
        member_cache[match_key] = member
    else:
        member_cache[match_key] = member
        # Fill in fields we didn't have before, and keep the longest known name.
        if row["chamber"] and not member.chamber:
            member.chamber = row["chamber"]
        if row["party"] and not member.party:
            member.party = row["party"]
        if row["state"] and not member.state:
            member.state = row["state"]
        if row.get("district") and not member.district:
            member.district = row["district"]
        if row.get("bioguide_id") and not member.bioguide_id:
            member.bioguide_id = row["bioguide_id"]
        if row.get("committees") and not member.committees:
            member.committees = row["committees"]
        if len(row["member_name"]) > len(member.name or ""):
            member.name = row["member_name"]


def apply_enrichment(row: dict, enrichment: dict) -> None:
    """Fill party/state/chamber from the reference legislators dataset when a
    trade source didn't provide them (party especially: none of the trade
    feeds include it). Mutates `row` in place, before it becomes a Member/Trade."""
    entry = enrichment["by_bioguide"].get(row.get("bioguide_id")) or enrichment[
        "by_match_key"
    ].get(row["member_match_key"])
    if not entry:
        return
    if entry["party"] and not row.get("party"):
        row["party"] = entry["party"]
    if entry["state"] and not row.get("state"):
        row["state"] = entry["state"]
    if entry["chamber"] and not row.get("chamber"):
        row["chamber"] = entry["chamber"]
    row["committees"] = entry["committees"]


def upsert_trade(db, row: dict, trade_cache: dict) -> bool:
    """Returns True if a new row was inserted, False if it already existed (and was refreshed)."""
    unique_id = row["unique_id"]
    existing = trade_cache.get(unique_id)
    if existing is None:
        existing = db.query(Trade).filter_by(unique_id=unique_id).one_or_none()

    if existing is None:
        trade_fields = {k: v for k, v in row.items() if k not in ("district", "bioguide_id", "committees")}
        trade = Trade(**trade_fields)
        db.add(trade)
        trade_cache[unique_id] = trade
        return True

    # Refresh fields that might improve over time (e.g. a later source fills disclosure_date).
    for field in ("disclosure_date", "disclosure_lag_days", "filing_url", "asset_name", "asset_type", "party", "state"):
        new_value = row.get(field)
        if new_value is not None and getattr(existing, field) is None:
            setattr(existing, field, new_value)
    trade_cache[unique_id] = existing
    return False


def backfill_enrichment(db, enrichment: dict) -> int:
    """One-time-ish catch-up: apply party/state/chamber/committees to Members
    and Trades already in the DB that predate this enrichment step (or whose
    trades haven't been re-fetched since). Cheap: one UPDATE per known member,
    only touching rows where the field is still NULL."""
    updated = 0
    all_entries = {**enrichment["by_match_key"]}
    # Also index by match_key derived from any bioguide-keyed entry, in case a
    # Member row only has a bioguide_id and no matching match_key entry.
    for member in db.query(Member).all():
        entry = enrichment["by_bioguide"].get(member.bioguide_id) or all_entries.get(member.match_key)
        if not entry:
            continue
        changed = False
        if entry["party"] and not member.party:
            member.party = entry["party"]
            changed = True
        if entry["state"] and not member.state:
            member.state = entry["state"]
            changed = True
        if entry["chamber"] and not member.chamber:
            member.chamber = entry["chamber"]
            changed = True
        if entry["committees"] and not member.committees:
            member.committees = entry["committees"]
            changed = True
        if changed:
            updated += 1
            db.query(Trade).filter(
                Trade.member_match_key == member.match_key, Trade.party.is_(None)
            ).update({"party": member.party}, synchronize_session=False)
            db.query(Trade).filter(
                Trade.member_match_key == member.match_key, Trade.state.is_(None)
            ).update({"state": member.state}, synchronize_session=False)
    db.commit()
    return updated


def run(sources=SOURCES) -> dict:
    init_db()
    db = SessionLocal()
    stats = {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "per_source": {}}
    member_cache: dict = {}
    trade_cache: dict = {}
    enrichment = legislators.fetch_enrichment()
    backfilled = backfill_enrichment(db, enrichment)
    if backfilled:
        logger.info("legislators: backfilled party/state/chamber for %d existing member(s)", backfilled)

    try:
        for source_mod in sources:
            source_name = getattr(source_mod, "SOURCE_NAME", source_mod.__name__)
            try:
                raw_rows = source_mod.fetch_raw_trades()
            except Exception:
                logger.exception("%s: fetch failed entirely, skipping source", source_name)
                raw_rows = []

            stats["per_source"][source_name] = {"fetched": len(raw_rows), "inserted": 0}
            stats["fetched"] += len(raw_rows)

            for raw in raw_rows:
                normalized = normalize_row(raw)
                if normalized is None:
                    stats["skipped"] += 1
                    continue
                apply_enrichment(normalized, enrichment)
                upsert_member(db, normalized, member_cache)
                inserted = upsert_trade(db, normalized, trade_cache)
                if inserted:
                    stats["inserted"] += 1
                    stats["per_source"][source_name]["inserted"] += 1
                else:
                    stats["updated"] += 1

            db.commit()
            logger.info(
                "%s: fetched=%d inserted=%d",
                source_name,
                len(raw_rows),
                stats["per_source"][source_name]["inserted"],
            )
    finally:
        db.close()

    logger.info(
        "DONE fetched=%d inserted=%d updated=%d skipped=%d",
        stats["fetched"], stats["inserted"], stats["updated"], stats["skipped"],
    )
    return stats


if __name__ == "__main__":
    run()
