from sqlalchemy import Boolean, Column, Integer, String, Float, Date, DateTime, Index, func

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

    notified = Column(Boolean, nullable=False, default=False, server_default="0")

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


class TradeReturn(Base):
    """Per-trade estimated return, computed alongside MemberRanking by the
    same daily job — lets the member profile page show "best/worst trades"
    without recomputing prices on every request (and without the Vercel
    read-only-filesystem problem: this table is only ever written by the
    GitHub Actions cron, same as MemberRanking)."""

    __tablename__ = "trade_returns"

    trade_id = Column(Integer, primary_key=True)
    match_key = Column(String, index=True, nullable=False)
    ticker = Column(String, nullable=False)
    return_pct = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    closed = Column(Boolean, default=False)  # False = still holding, return is "as of today"
    last_calculated = Column(DateTime, nullable=True)


class PriceCache(Base):
    """Daily close prices, fetched once and reused across ranking runs and the
    ticker candlestick endpoint. Avoids re-hitting Yahoo Finance for the same
    ticker/date on every run."""

    __tablename__ = "price_cache"

    ticker = Column(String, primary_key=True)
    date = Column(Date, primary_key=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)


class TelegramSubscriber(Base):
    __tablename__ = "telegram_subscribers"

    chat_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TelegramWatch(Base):
    """A subscriber watching either a member (by match_key) or a ticker."""

    __tablename__ = "telegram_watches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, index=True, nullable=False)
    watch_type = Column(String, nullable=False)  # "member" | "ticker"
    value = Column(String, nullable=False)  # member match_key, or ticker symbol
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_watch_unique", "chat_id", "watch_type", "value", unique=True),
    )


class EarningsCache(Base):
    """One row per (ticker, earnings date) — fetched once from FMP and
    reused, mirroring PriceCache's pattern (see app/prices.py)."""

    __tablename__ = "earnings_cache"

    ticker = Column(String, primary_key=True)
    date = Column(Date, primary_key=True)


class EarningsSkip(Base):
    """Tickers FMP's free plan won't serve earnings for (HTTP 402) or that
    genuinely have none — remembered so scan_earnings.py doesn't burn its
    daily fetch budget retrying the same permanently-blocked ticker."""

    __tablename__ = "earnings_skip"

    ticker = Column(String, primary_key=True)
    checked_at = Column(DateTime, server_default=func.now())


class PolymarketAlert(Base):
    """A single unusually large trade on a political/policy Polymarket
    market whose outcome isn't yet publicly known (price reflects real
    uncertainty, not near-consensus). Not linked to any person — Polymarket
    wallets are pseudonymous, there's no public wallet-to-identity mapping.
    This is a personal "someone is betting big on something uncertain"
    signal, not a congress-trades feature. See app/polymarket.py."""

    __tablename__ = "polymarket_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String, unique=True, index=True, nullable=False)
    event_title = Column(String, nullable=False)
    market_question = Column(String, nullable=False)
    outcome = Column(String, nullable=True)
    side = Column(String, nullable=True)  # BUY | SELL
    price = Column(Float, nullable=True)
    size_usd = Column(Float, nullable=False)
    liquidity_usd = Column(Float, nullable=True)
    pct_of_liquidity = Column(Float, nullable=True)
    wallet = Column(String, nullable=True)
    tag = Column(String, nullable=True)  # which curated tag matched (congress, elections, ...)
    event_slug = Column(String, nullable=True)
    market_slug = Column(String, nullable=True)
    trade_timestamp = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, server_default=func.now())


class TelegramState(Base):
    """Tiny key-value store, e.g. the last processed Telegram update_id."""

    __tablename__ = "telegram_state"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class InsiderTrade(Base):
    """Open-market purchase (Form 4, transaction code P) by a company insider,
    aggregated per filing. Only purchases are stored: insiders sell for many
    reasons (taxes, diversification, 10b5-1 plans), but buy for one. See
    app/insiders.py."""

    __tablename__ = "insider_trades"

    accession = Column(String, primary_key=True)  # SEC accession number, one per filing
    ticker = Column(String, index=True, nullable=False)
    issuer_name = Column(String, nullable=True)
    insider_name = Column(String, nullable=False)
    insider_cik = Column(String, index=True, nullable=True)
    role = Column(String, nullable=True)  # "CEO", "Director", "10% owner"...
    is_officer = Column(Boolean, default=False)
    is_director = Column(Boolean, default=False)
    is_ten_pct = Column(Boolean, default=False)
    transaction_date = Column(Date, index=True, nullable=True)
    filed_at = Column(DateTime, index=True, nullable=True)
    shares = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=True)
    value_usd = Column(Float, nullable=False)
    shares_after = Column(Float, nullable=True)
    notified = Column(Boolean, nullable=False, default=False, server_default="0")
    detected_at = Column(DateTime, server_default=func.now())


class SetupSignal(Base):
    """A technical setup alert that was sent (app/setups.py), kept so the
    same ticker isn't re-alerted every day and so live hit-rate can be
    measured later against what the backtest promised."""

    __tablename__ = "setup_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, index=True, nullable=False)
    direction = Column(String, nullable=False)  # long | short
    signal_date = Column(Date, index=True, nullable=False)
    score = Column(Float, nullable=False)
    entry = Column(Float, nullable=False)
    stop = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    reasons = Column(String, nullable=True)
    outcome = Column(String, nullable=True)  # target | stop | time — filled in later
    created_at = Column(DateTime, server_default=func.now())
