"""Polymarket "whale bet on an uncertain outcome" scanner.

Not affiliated with Congress trades — this is a separate personal signal: a
single, unusually large trade on a political/policy prediction market whose
outcome isn't yet public knowledge (price not already near 0 or 1). A big
one-sided bet on real uncertainty is either high conviction or someone
knows something. It is deliberately NOT attributed to any identity —
Polymarket wallets are pseudonymous on-chain addresses with no public link
to a real person, so this only ever surfaces "wallet 0x1234... bet $80k",
never a name. Read-only public APIs, no key needed:
https://docs.polymarket.com/api-reference/introduction
"""
import logging
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from .models import PolymarketAlert

logger = logging.getLogger("polymarket")

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

# Curated, conservative set of tags relevant to policy/political outcomes —
# deliberately excludes sports/entertainment/crypto-price markets that
# dominate Polymarket's overall volume and would drown out the signal.
WATCHED_TAGS = [
    "politics", "elections", "congress", "house-races", "geopolitics",
    "scotus", "government-shutdown", "tariffs", "federal-government",
]

MIN_LIQUIDITY_USD = 20_000       # ignore illiquid/joke markets
MIN_TRADE_USD = 5_000            # floor for "large" in absolute terms
MIN_PCT_OF_LIQUIDITY = 0.05      # a single trade >= 5% of the market's liquidity
UNCERTAINTY_BAND = (0.08, 0.92)  # price must reflect real uncertainty, not consensus


def _get(url: str, params: dict):
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _extract_price(m: dict) -> float | None:
    """The Gamma API is observed to sometimes omit outcomePrices from a
    market object (payload shape seems to vary, possibly by response size /
    CDN caching) — fall back to other price fields it more reliably
    includes rather than silently dropping the market."""
    prices = m.get("outcomePrices")
    try:
        if prices:
            return float(prices[0])
    except (TypeError, ValueError, IndexError):
        pass
    last_trade = m.get("lastTradePrice")
    if last_trade is not None:
        try:
            return float(last_trade)
        except (TypeError, ValueError):
            pass
    bid, ask = m.get("bestBid"), m.get("bestAsk")
    if bid is not None and ask is not None:
        try:
            return (float(bid) + float(ask)) / 2
        except (TypeError, ValueError):
            pass
    return None


def _fetch_watched_markets() -> list[dict]:
    """One dict per sub-market across every watched tag, deduped by
    conditionId, restricted to active + liquid + genuinely uncertain."""
    markets: dict[str, dict] = {}
    for tag in WATCHED_TAGS:
        try:
            events = _get(f"{GAMMA_BASE}/events", {"tag_slug": tag, "limit": 50, "closed": "false"})
        except Exception:
            logger.exception("polymarket: failed fetching tag %s", tag)
            continue
        for event in events:
            for m in event.get("markets", []) or []:
                condition_id = m.get("conditionId")
                if not condition_id or condition_id in markets:
                    continue
                try:
                    liquidity = float(m.get("liquidity") or 0)
                except (TypeError, ValueError):
                    liquidity = 0
                if liquidity < MIN_LIQUIDITY_USD:
                    continue
                price_yes = _extract_price(m)
                if price_yes is None or not (UNCERTAINTY_BAND[0] <= price_yes <= UNCERTAINTY_BAND[1]):
                    continue
                markets[condition_id] = {
                    "condition_id": condition_id,
                    "question": m.get("question"),
                    "event_title": event.get("title"),
                    "event_slug": event.get("slug"),
                    "market_slug": m.get("slug"),
                    "liquidity": liquidity,
                    "tag": tag,
                }
    return list(markets.values())


def scan(db: Session) -> dict:
    stats = {"markets_scanned": 0, "alerts_found": 0}
    markets = _fetch_watched_markets()
    stats["markets_scanned"] = len(markets)

    for market in markets:
        try:
            trades = _get(f"{DATA_BASE}/trades", {"market": market["condition_id"], "limit": 50})
        except Exception:
            logger.exception("polymarket: failed fetching trades for %s", market["condition_id"])
            continue

        for t in trades:
            try:
                size_usd = float(t.get("size") or 0) * float(t.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if size_usd < MIN_TRADE_USD:
                continue
            pct = size_usd / market["liquidity"] if market["liquidity"] else 0
            if pct < MIN_PCT_OF_LIQUIDITY:
                continue

            tx_hash = t.get("transactionHash")
            if not tx_hash or db.query(PolymarketAlert).filter_by(tx_hash=tx_hash).one_or_none():
                continue

            timestamp = t.get("timestamp")
            db.add(
                PolymarketAlert(
                    tx_hash=tx_hash,
                    event_title=market["event_title"] or "",
                    market_question=market["question"] or "",
                    outcome=t.get("outcome"),
                    side=t.get("side"),
                    price=t.get("price"),
                    size_usd=size_usd,
                    liquidity_usd=market["liquidity"],
                    pct_of_liquidity=pct,
                    wallet=t.get("proxyWallet"),
                    tag=market["tag"],
                    event_slug=market["event_slug"],
                    market_slug=market["market_slug"],
                    trade_timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else None,
                )
            )
            stats["alerts_found"] += 1

    db.commit()
    logger.info("polymarket: scanned=%d alerts=%d", stats["markets_scanned"], stats["alerts_found"])
    return stats
