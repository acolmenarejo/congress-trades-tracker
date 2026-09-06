from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Member, MemberRanking, Trade


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

    total = q.count()
    items = (
        q.order_by(Trade.disclosure_date.desc().nullslast(), Trade.transaction_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def get_member(db: Session, match_key: str) -> Optional[Member]:
    return db.query(Member).filter_by(match_key=match_key).one_or_none()


def get_member_trades(db: Session, match_key: str, limit: int = 500):
    return (
        db.query(Trade)
        .filter(Trade.member_match_key == match_key)
        .order_by(Trade.transaction_date.desc())
        .limit(limit)
        .all()
    )


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


def global_kpis(db: Session):
    total_trades = db.query(func.count(Trade.id)).scalar() or 0
    total_volume = db.query(func.coalesce(func.sum(Trade.amount_mid), 0.0)).scalar() or 0.0
    active_filers = db.query(func.count(func.distinct(Trade.member_match_key))).scalar() or 0
    return {
        "total_trades": total_trades,
        "total_volume_estimate": total_volume,
        "active_filers": active_filers,
    }
