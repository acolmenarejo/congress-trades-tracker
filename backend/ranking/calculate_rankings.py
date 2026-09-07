"""Fase 3: estimated-return ranking, recomputed on a schedule (not per-request).

For every member, for every purchase trade of a plain stock:
  - entry price = close on/after the transaction date (approximates the fill)
  - exit price  = close on/after the matching sale's date if one exists later
                  for the same member+ticker (FIFO, one sale closes the
                  earliest still-open purchase), otherwise the latest
                  available close ("still holding")
  - alpha = the member's return minus SPY's return over the same window

Scope: only trades from the last RANKING_LOOKBACK_DAYS are considered. Most
of our real/live data is recent anyway (see README on source coverage), and
including the full 2012-2021 historical backfill would multiply the number
of distinct tickers to price-fetch for comparatively little ranking value —
call this out if extending the ranking to "all-time" later.

Usage:
    python calculate_rankings.py
"""
import logging
import os
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import MemberRanking, Trade  # noqa: E402

from ranking import prices  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("calculate_rankings")

RANKING_LOOKBACK_DAYS = 730
BAD_TICKERS = {"N/A", "--", ""}


def _valid_ticker(t: str | None) -> bool:
    return bool(t) and t not in BAD_TICKERS and t.isalnum() and len(t) <= 6


def match_purchases_to_sales(trades: list[Trade]) -> list[dict]:
    """FIFO-match purchases to later sales of the same ticker. Returns one
    dict per purchase: {trade, exit_date, closed}."""
    by_ticker = defaultdict(list)
    for t in trades:
        if t.transaction_type in ("purchase", "sale") and _valid_ticker(t.ticker) and t.transaction_date:
            by_ticker[t.ticker].append(t)

    results = []
    for ticker, ticker_trades in by_ticker.items():
        ticker_trades.sort(key=lambda t: t.transaction_date)
        open_sales = [t for t in ticker_trades if t.transaction_type == "sale"]
        used_sale_ids = set()
        for t in ticker_trades:
            if t.transaction_type != "purchase":
                continue
            exit_date = None
            for s in open_sales:
                if s.id in used_sale_ids:
                    continue
                if s.transaction_date > t.transaction_date:
                    exit_date = s.transaction_date
                    used_sale_ids.add(s.id)
                    break
            results.append({"trade": t, "exit_date": exit_date, "closed": exit_date is not None})
    return results


def compute_member_metrics(db, member_purchases: list[dict], today: date) -> dict | None:
    trade_returns = []  # (return_pct, weight, alpha_pct, holding_days)

    price_series_cache: dict[str, list[dict]] = {}

    def get_series(ticker: str, start: date) -> list[dict]:
        if ticker not in price_series_cache:
            price_series_cache[ticker] = prices.get_price_series(db, ticker, start, today)
        return price_series_cache[ticker]

    spy_series = get_series(prices.SP500_TICKER, today - timedelta(days=RANKING_LOOKBACK_DAYS + 10))

    for item in member_purchases:
        t: Trade = item["trade"]
        series = get_series(t.ticker, t.transaction_date - timedelta(days=5))
        if not series:
            continue

        entry = prices.price_on_or_after(series, t.transaction_date)
        if entry is None:
            continue

        if item["closed"]:
            exit_price = prices.price_on_or_after(series, item["exit_date"]) or prices.price_on_or_before(
                series, today
            )
            exit_date = item["exit_date"]
        else:
            exit_price = prices.price_on_or_before(series, today)
            exit_date = today

        if exit_price is None or entry <= 0:
            continue

        return_pct = (exit_price / entry - 1) * 100
        weight = t.amount_mid or 1.0
        holding_days = max((exit_date - t.transaction_date).days, 1)

        spy_entry = prices.price_on_or_after(spy_series, t.transaction_date)
        spy_exit = prices.price_on_or_after(spy_series, exit_date) or prices.price_on_or_before(spy_series, today)
        alpha_pct = None
        if spy_entry and spy_exit and spy_entry > 0:
            spy_return = (spy_exit / spy_entry - 1) * 100
            alpha_pct = return_pct - spy_return

        trade_returns.append((return_pct, weight, alpha_pct, holding_days))

    if not trade_returns:
        return None

    total_weight = sum(w for _, w, _, _ in trade_returns)
    total_return_pct = sum(r * w for r, w, _, _ in trade_returns) / total_weight
    alpha_values = [(a, w) for _, w, a, _ in trade_returns if a is not None]
    alpha_vs_sp500_pct = (
        sum(a * w for a, w in alpha_values) / sum(w for _, w in alpha_values) if alpha_values else None
    )
    win_rate_pct = 100 * sum(1 for r, _, _, _ in trade_returns if r > 0) / len(trade_returns)
    avg_holding_days = sum(h * w for _, w, _, h in trade_returns) / total_weight
    annualized_return_pct = (
        ((1 + total_return_pct / 100) ** (365 / avg_holding_days) - 1) * 100 if avg_holding_days > 0 else None
    )

    return {
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "win_rate_pct": win_rate_pct,
        "alpha_vs_sp500_pct": alpha_vs_sp500_pct,
    }


def run() -> dict:
    init_db()
    db = SessionLocal()
    stats = {"members_processed": 0, "members_ranked": 0}

    try:
        cutoff = date.today() - timedelta(days=RANKING_LOOKBACK_DAYS)
        all_trades = db.query(Trade).filter(Trade.transaction_date >= cutoff).all()

        by_member: dict[str, list[Trade]] = defaultdict(list)
        for t in all_trades:
            by_member[t.member_match_key].append(t)

        today = date.today()
        for match_key, member_trades in by_member.items():
            stats["members_processed"] += 1
            purchases = match_purchases_to_sales(member_trades)
            purchases = [p for p in purchases if p["trade"].transaction_date >= cutoff]
            metrics = compute_member_metrics(db, purchases, today)

            trade_count = len(member_trades)
            volume_estimate = sum(t.amount_mid or 0 for t in member_trades)
            lags = [t.disclosure_lag_days for t in member_trades if t.disclosure_lag_days is not None]
            avg_lag = sum(lags) / len(lags) if lags else None

            ranking = db.query(MemberRanking).filter_by(match_key=match_key).one_or_none()
            if ranking is None:
                ranking = MemberRanking(match_key=match_key)
                db.add(ranking)

            ranking.trade_count = trade_count
            ranking.volume_estimate = volume_estimate
            ranking.avg_disclosure_lag_days = avg_lag
            ranking.last_calculated = datetime.now(UTC)
            if metrics:
                ranking.total_return_pct = metrics["total_return_pct"]
                ranking.annualized_return_pct = metrics["annualized_return_pct"]
                ranking.win_rate_pct = metrics["win_rate_pct"]
                ranking.alpha_vs_sp500_pct = metrics["alpha_vs_sp500_pct"]
                stats["members_ranked"] += 1

            db.commit()
            logger.info(
                "%s: trades=%d volume=%.0f return=%s",
                match_key,
                trade_count,
                volume_estimate,
                f"{metrics['total_return_pct']:.1f}%" if metrics else "n/a",
            )
    finally:
        db.close()

    logger.info("DONE members_processed=%d members_ranked=%d", stats["members_processed"], stats["members_ranked"])
    return stats


if __name__ == "__main__":
    run()
