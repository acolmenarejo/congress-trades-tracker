from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Member, MemberRanking, Trade, TradeReturn
from . import prices


def list_trades(
    db: Session,
    member: Optional[str] = None,
    ticker: Optional[str] = None,
    chamber: Optional[str] = None,
    party: Optional[str] = None,
    transaction_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
):
    q = db.query(Trade)
    if member:
        like = f"%{member.lower()}%"
        q = q.filter(func.lower(Trade.member_name).like(like))
    if ticker:
        q = q.filter(Trade.ticker == ticker.upper())
    if chamber:
        q = q.filter(Trade.chamber == chamber.lower())
    if party:
        q = q.filter(Trade.party == party.upper())
    if transaction_type:
        q = q.filter(Trade.transaction_type == transaction_type.lower())
    if date_from:
        q = q.filter(Trade.transaction_date >= date_from)
    if date_to:
        q = q.filter(Trade.transaction_date <= date_to)
    else:
        # A handful of source records have a corrupted (future) transaction_date
        # — e.g. a parsing bug swapping fields. Left alone, one of those jumps
        # to the top of "most recent" and breaks date-axis charts. Only applied
        # when the caller didn't ask for a specific range, so it stays
        # reachable via an explicit date_to/ticker/member filter for debugging.
        q = q.filter(Trade.transaction_date <= date.today())

    total = q.count()
    items = (
        # Order by when the trade actually happened, not when it was
        # disclosed — a trade filed very late (STOCK Act lag can run months)
        # would otherwise jump to the top of "most recent" just because it
        # was just made public, burying genuinely recent activity under old
        # trades.
        q.order_by(Trade.transaction_date.desc().nullslast(), Trade.disclosure_date.desc().nullslast())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def _photo_url(bioguide_id: Optional[str]) -> Optional[str]:
    if not bioguide_id:
        return None
    return f"https://unitedstates.github.io/images/congress/225x275/{bioguide_id}.jpg"


def get_member(db: Session, match_key: str) -> Optional[dict]:
    member = db.query(Member).filter_by(match_key=match_key).one_or_none()
    if member is None:
        return None
    ranking = get_member_ranking(db, match_key)
    return {
        "id": member.id,
        "match_key": member.match_key,
        "name": member.name,
        "chamber": member.chamber,
        "party": member.party,
        "state": member.state,
        "district": member.district,
        "bioguide_id": member.bioguide_id,
        "committees": member.committees,
        "photo_url": _photo_url(member.bioguide_id),
        "ranking": {
            "trade_count": ranking.trade_count,
            "volume_estimate": ranking.volume_estimate,
            "total_return_pct": ranking.total_return_pct,
            "annualized_return_pct": ranking.annualized_return_pct,
            "win_rate_pct": ranking.win_rate_pct,
            "alpha_vs_sp500_pct": ranking.alpha_vs_sp500_pct,
            "avg_disclosure_lag_days": ranking.avg_disclosure_lag_days,
        }
        if ranking
        else None,
    }


def get_member_trades(db: Session, match_key: str, limit: int = 500):
    return (
        db.query(Trade)
        .filter(Trade.member_match_key == match_key)
        .order_by(Trade.transaction_date.desc())
        .limit(limit)
        .all()
    )


def get_member_ranking(db: Session, match_key: str) -> Optional[MemberRanking]:
    return db.query(MemberRanking).filter_by(match_key=match_key).one_or_none()


def get_member_best_trades(db: Session, match_key: str, limit: int = 5, worst: bool = False):
    """Top (or bottom) individual trades by estimated return, precomputed
    daily alongside the ranking — see backend/ranking/calculate_rankings.py."""
    order = TradeReturn.return_pct.asc() if worst else TradeReturn.return_pct.desc()
    rows = (
        db.query(TradeReturn, Trade)
        .join(Trade, Trade.id == TradeReturn.trade_id)
        .filter(TradeReturn.match_key == match_key)
        .order_by(order)
        .limit(limit)
        .all()
    )
    return [
        {
            "ticker": tr.ticker,
            "asset_name": trade.asset_name,
            "transaction_type": trade.transaction_type,
            "transaction_date": trade.transaction_date,
            "amount_range_low": trade.amount_range_low,
            "amount_range_high": trade.amount_range_high,
            "return_pct": tr.return_pct,
            "entry_price": tr.entry_price,
            "exit_price": tr.exit_price,
            "closed": tr.closed,
            "filing_url": trade.filing_url,
        }
        for tr, trade in rows
    ]


def get_ticker_summary(db: Session, ticker: str, limit: int = 200):
    ticker = ticker.upper()
    trades = (
        db.query(Trade)
        .filter(Trade.ticker == ticker)
        .order_by(Trade.transaction_date.desc())
        .limit(limit)
        .all()
    )
    buy_count = sum(1 for t in trades if t.transaction_type == "purchase")
    sell_count = sum(1 for t in trades if t.transaction_type == "sale")
    volume = sum(t.amount_mid or 0 for t in trades)
    distinct_members = len({t.member_match_key for t in trades})
    return {
        "ticker": ticker,
        "trade_count": len(trades),
        "volume_estimate": volume,
        "distinct_members": distinct_members,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "trades": trades,
    }


def get_rankings(db: Session, sort_by: str = "total_return_pct", limit: int = 100):
    valid_sorts = {
        "total_return_pct",
        "annualized_return_pct",
        "volume_estimate",
        "trade_count",
        "win_rate_pct",
        "alpha_vs_sp500_pct",
        "avg_disclosure_lag_days",  # "worst compliance" ranking: highest lag first
    }
    if sort_by not in valid_sorts:
        sort_by = "total_return_pct"

    col = getattr(MemberRanking, sort_by)
    rankings = (
        db.query(MemberRanking, Member)
        .join(Member, Member.match_key == MemberRanking.match_key)
        .order_by(col.desc().nullslast())
        .limit(limit)
        .all()
    )
    out = []
    for ranking, member in rankings:
        out.append(
            {
                "match_key": member.match_key,
                "name": member.name,
                "chamber": member.chamber,
                "party": member.party,
                "state": member.state,
                "photo_url": _photo_url(member.bioguide_id),
                "trade_count": ranking.trade_count,
                "volume_estimate": ranking.volume_estimate,
                "total_return_pct": ranking.total_return_pct,
                "annualized_return_pct": ranking.annualized_return_pct,
                "win_rate_pct": ranking.win_rate_pct,
                "alpha_vs_sp500_pct": ranking.alpha_vs_sp500_pct,
                "avg_disclosure_lag_days": ranking.avg_disclosure_lag_days,
                "last_calculated": ranking.last_calculated.isoformat() if ranking.last_calculated else None,
            }
        )
    return out


def get_ticker_prices(db: Session, ticker: str, days: int = 180):
    ticker = ticker.upper()
    series = prices.get_price_series(db, ticker, date.today() - timedelta(days=days), date.today())
    return [
        {
            "date": row["date"].isoformat(),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in series
    ]


def global_kpis(db: Session):
    total_trades = db.query(func.count(Trade.id)).scalar() or 0
    total_volume = db.query(func.coalesce(func.sum(Trade.amount_mid), 0.0)).scalar() or 0.0
    active_filers = db.query(func.count(func.distinct(Trade.member_match_key))).scalar() or 0
    return {
        "total_trades": total_trades,
        "total_volume_estimate": total_volume,
        "active_filers": active_filers,
    }
