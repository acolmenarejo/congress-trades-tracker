from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Index, func

from .database import Base


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    chamber = Column(String, nullable=True)  # "senate" | "house"
    party = Column(String, nullable=True)  # "D" | "R" | "I" | None
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    bioguide_id = Column(String, nullable=True, index=True)
    committees = Column(String, nullable=True)  # comma-separated, best-effort
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unique_id = Column(String, unique=True, index=True, nullable=False)

    member_match_key = Column(String, index=True, nullable=False)
    member_name = Column(String, nullable=False)
    chamber = Column(String, index=True, nullable=True)
    party = Column(String, index=True, nullable=True)
    state = Column(String, index=True, nullable=True)

    ticker = Column(String, index=True, nullable=True)
    asset_name = Column(String, nullable=True)
    asset_type = Column(String, nullable=True)

    transaction_type = Column(String, index=True, nullable=True)  # purchase | sale | exchange
    owner = Column(String, nullable=True)  # self | spouse | joint | child

    amount_range_low = Column(Float, nullable=True)
    amount_range_high = Column(Float, nullable=True)
    amount_mid = Column(Float, nullable=True)

    transaction_date = Column(Date, index=True, nullable=True)
    disclosure_date = Column(Date, index=True, nullable=True)
    disclosure_lag_days = Column(Integer, nullable=True)

    source = Column(String, nullable=False)  # house_stock_watcher | senate_stock_watcher | congress_invests
    filing_url = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_trades_member_date", "member_match_key", "transaction_date"),
    )


class MemberRanking(Base):
    """Cached, expensive-to-compute performance metrics per member (Fase 3).
    Recomputed on a schedule (e.g. daily) by a separate job, not per-request."""

    __tablename__ = "member_rankings"

    match_key = Column(String, primary_key=True)
    trade_count = Column(Integer, default=0)
    volume_estimate = Column(Float, default=0.0)
    total_return_pct = Column(Float, nullable=True)
    annualized_return_pct = Column(Float, nullable=True)
    win_rate_pct = Column(Float, nullable=True)
    alpha_vs_sp500_pct = Column(Float, nullable=True)
    avg_disclosure_lag_days = Column(Float, nullable=True)
    last_calculated = Column(DateTime, nullable=True)
