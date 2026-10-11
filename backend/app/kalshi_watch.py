"""Telegram when a Kalshi market we follow moves 15+ points in a day.

Covers the macro ladders in app/kalshi_expect.py and the company KPI markets
in app/kalshi_company.py (not the earnings-call word bets: a word going from
40% to 60% moves no portfolio). Kalshi's previous_price_dollars is the price
24 h earlier, so no history is needed.

Noise filters, all round numbers: skip markets closing within 3 days (weekly
gas or CPI ladders swing as the number becomes known, that is not news),
wide books (spread > 10 points), thin ones (< 500 contracts open) and the
weekly fuel series altogether. Both the mid and the last trade must have
moved, so one stray print is not enough. A market alerts at most once every
3 days (TelegramState[SENT_KEY]).
"""
import html
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .kalshi_company import _market
from .models import TelegramState, TelegramSubscriber

logger = logging.getLogger(__name__)

SENT_KEY = "kalshi_moves_sent"
MIN_MOVE = 0.15
MIN_OI = 500
MAX_SPREAD = 0.10
SKIP_SERIES = {"KXAAAGASW", "KXDIESELW"}


def _closes_soon(close: str | None, now: datetime) -> bool:
    try:
        return datetime.fromisoformat((close or "").replace("Z", "+00:00")) < now + timedelta(days=3)
    except ValueError:
        return True


def moves(events: list[dict], company: dict[str, list[dict]]) -> list[dict]:
    """[{title, label, prev, p, ticker, url, stock}] for every market that moved."""
    now = datetime.now(timezone.utc)
    rows, seen = [], set()

    def check(m: dict, title: str, url: str, stock: str | None):
        if m["ticker"] in seen or m["p"] is None or m["prev"] is None or m["last"] is None:
            return
        seen.add(m["ticker"])
        if m["oi"] < MIN_OI or (m["spread"] is not None and m["spread"] > MAX_SPREAD) or _closes_soon(m["close"], now):
            return
        if m["prev"] <= 0:  # no trade yesterday: Kalshi reports 0
            return
        if abs(m["p"] - m["prev"]) >= MIN_MOVE and abs(m["last"] - m["prev"]) >= MIN_MOVE:
            rows.append({"title": title, "label": m["label"], "prev": m["prev"], "p": m["p"],
                         "ticker": m["ticker"], "url": url, "stock": stock})

    for e in events:
        if e.get("series_ticker") in SKIP_SERIES:
            continue
        url = f"https://kalshi.com/markets/{(e.get('series_ticker') or '').lower()}"
        for raw in e.get("markets") or []:
            check(_market(raw), e.get("title") or "", url, None)
    for stock, evs in company.items():
        for e in evs:
            if e["kind"] != "kpi":
                continue
            for m in e["markets"]:
                check(m, e["title"] or "", e["url"], stock)
    return rows


def notify(db: Session, events: list[dict], company: dict[str, list[dict]]) -> int:
    from .config import TELEGRAM_BOT_TOKEN
    from .telegram_api import send_message

    st = db.get(TelegramState, SENT_KEY)
    try:
        sent = json.loads(st.value) if st and st.value else {}
    except ValueError:
        sent = {}
    now = datetime.now(timezone.utc)
    sent = {k: v for k, v in sent.items() if datetime.fromisoformat(v) > now - timedelta(days=3)}
    new = [r for r in moves(events, company) if r["ticker"] not in sent]
    for r in new:
        sent[r["ticker"]] = now.isoformat()
    db.merge(TelegramState(key=SENT_KEY, value=json.dumps(sent)))
    db.commit()
    if not new:
        return 0

    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    lines = ["📊 <b>Kalshi: movimiento fuerte en 24 h</b>"]
    for r in sorted(new, key=lambda r: -abs(r["p"] - r["prev"]))[:8]:
        arrow = "⬆️" if r["p"] > r["prev"] else "⬇️"
        who = f"<b>${e(r['stock'])}</b> · " if r["stock"] else ""
        lines += ["", f"{arrow} {who}{e(r['title'])}",
                  f"«{e(r['label'])}»: {r['prev'] * 100:.0f}% → <b>{r['p'] * 100:.0f}%</b>",
                  f'<a href="{e(r["url"])}">Ver en Kalshi</a>']
    lines += ["", "Mercados de predicción con poco dinero detrás: tómalo como pista, no como dato."]
    text = "\n".join(lines)
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []
    logger.info("kalshi_watch: %d moves", len(new))
    return sum(send_message(c, text) for c in chats)
