from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unique_id: str
    member_match_key: str
    member_name: str
    chamber: Optional[str] = None
    party: Optional[str] = None
    state: Optional[str] = None
    ticker: Optional[str] = None
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    transaction_type: Optional[str] = None
    owner: Optional[str] = None
    amount_range_low: Optional[float] = None
    amount_range_high: Optional[float] = None
    amount_mid: Optional[float] = None
    transaction_date: Optional[date] = None
    disclosure_date: Optional[date] = None
    disclosure_lag_days: Optional[int] = None
    source: str
    filing_url: Optional[str] = None


class TradeListOut(BaseModel):
    total: int
    items: list[TradeOut]


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_key: str
    name: str
    chamber: Optional[str] = None
    party: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    bioguide_id: Optional[str] = None
    committees: Optional[str] = None


class MemberRankingOut(BaseModel):
    match_key: str
    name: str
    chamber: Optional[str] = None
    party: Optional[str] = None
    state: Optional[str] = None
    trade_count: int
    volume_estimate: float
    total_return_pct: Optional[float] = None
    annualized_return_pct: Optional[float] = None
    win_rate_pct: Optional[float] = None
    alpha_vs_sp500_pct: Optional[float] = None
    avg_disclosure_lag_days: Optional[float] = None
    last_calculated: Optional[str] = None


class TickerSummaryOut(BaseModel):
    ticker: str
    trade_count: int
    volume_estimate: float
    distinct_members: int
    buy_count: int
    sell_count: int
    trades: list[TradeOut]
