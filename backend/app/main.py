from datetime import date
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud
from .config import CRON_SECRET, GITHUB_REPO, GITHUB_TOKEN
from .database import get_db, init_db
from .schemas import MemberOut, MemberRankingOut, TickerSummaryOut, TradeListOut, TradeOut

app = FastAPI(title="Congress Trades Tracker API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    return crud.global_kpis(db)


@app.get("/trades", response_model=TradeListOut)
def get_trades(
    member: Optional[str] = None,
    ticker: Optional[str] = None,
    chamber: Optional[str] = Query(None, pattern="^(house|senate)$"),
    party: Optional[str] = Query(None, pattern="^(D|R|I)$"),
    transaction_type: Optional[str] = Query(None, pattern="^(purchase|sale|exchange)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    total, items = crud.list_trades(
        db,
        member=member,
        ticker=ticker,
        chamber=chamber,
        party=party,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": items}


@app.get("/members/ranking", response_model=list[MemberRankingOut])
def members_ranking(
    sort_by: str = Query("total_return_pct"),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_rankings(db, sort_by=sort_by, limit=limit)


@app.get("/members/{match_key}", response_model=MemberOut)
def get_member(match_key: str, db: Session = Depends(get_db)):
    member = crud.get_member(db, match_key)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@app.get("/members/{match_key}/trades", response_model=list[TradeOut])
def get_member_trades(match_key: str, limit: int = Query(500, le=2000), db: Session = Depends(get_db)):
    return crud.get_member_trades(db, match_key, limit=limit)


@app.get("/tickers/{ticker}", response_model=TickerSummaryOut)
def get_ticker(ticker: str, db: Session = Depends(get_db)):
    summary = crud.get_ticker_summary(db, ticker)
    if summary["trade_count"] == 0:
        raise HTTPException(status_code=404, detail="No trades found for ticker")
    return summary


@app.get("/tickers/{ticker}/prices")
def get_ticker_prices(ticker: str, days: int = Query(180, le=1825), db: Session = Depends(get_db)):
    return crud.get_ticker_prices(db, ticker, days=days)


def _dispatch_workflow(workflow_file: str) -> int:
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow_file}/dispatches",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"ref": "master"},
        timeout=10,
    )
    return resp.status_code


@app.api_route("/internal/trigger-poll", methods=["GET", "POST"])
def trigger_poll(secret: str = Query(...)):
    """Called by an external free pinger (e.g. cron-job.org) every 1-2 minutes.
    Relays into a GitHub Actions workflow_dispatch for bot-poll.yml, which is
    where the actual Telegram polling + durable state write happens (this
    process can't write the read-only-in-prod SQLite file itself)."""
    if not CRON_SECRET or secret != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN not configured")
    status_code = _dispatch_workflow("bot-poll.yml")
    if status_code >= 300:
        raise HTTPException(status_code=502, detail=f"GitHub dispatch failed: {status_code}")
    return {"status": "dispatched"}
