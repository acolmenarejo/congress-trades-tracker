"""Shared context for Telegram alerts: is the move already in the news, how
much it matters (alto/medio/bajo), what it means for the watchlist, and links
to our own pages.

News comes from Google News' RSS search (no key). It only answers "was there
a headline about this in the last 48 h?": with one, the move is most likely a
reaction to public news; without, the market may know something not yet
published (or it is noise: Kalshi books are small). If the feed can't be
reached the alert says it couldn't check, never "no news".
"""
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from sqlalchemy.orm import Session

from .models import CompanyProfile, EarningsCache, TelegramWatch

logger = logging.getLogger(__name__)

WEB = "https://congress-trades-tracker.netlify.app"
NEWS_HOURS = 48

# Sector for big names that have no CompanyProfile yet (alerts only need a
# rough bucket to say who wins or loses from a macro move).
SECTOR_FALLBACK = {
    "AAPL": "Tecnología", "MSFT": "Tecnología", "NVDA": "Tecnología", "AMD": "Tecnología",
    "AVGO": "Tecnología", "ORCL": "Tecnología", "MRVL": "Tecnología", "MU": "Tecnología",
    "INTC": "Tecnología", "CRM": "Tecnología", "GOOGL": "Comunicaciones", "GOOG": "Comunicaciones",
    "META": "Comunicaciones", "NFLX": "Comunicaciones", "DIS": "Comunicaciones",
    "AMZN": "Consumo cíclico", "TSLA": "Consumo cíclico", "HD": "Consumo cíclico",
    "MCD": "Consumo cíclico", "DPZ": "Consumo cíclico", "CMG": "Consumo cíclico",
    "KO": "Consumo básico", "PEP": "Consumo básico", "WMT": "Consumo básico",
    "COST": "Consumo básico", "PG": "Consumo básico", "MO": "Consumo básico",
    "JPM": "Servicios financieros", "BAC": "Servicios financieros", "GS": "Servicios financieros",
    "AXP": "Servicios financieros", "SCHW": "Servicios financieros", "CRBG": "Servicios financieros",
    "XOM": "Energía", "CVX": "Energía", "OXY": "Energía", "EQT": "Energía",
    "VST": "Utilities (eléctricas, agua, gas)", "CEG": "Utilities (eléctricas, agua, gas)",
    "NRG": "Utilities (eléctricas, agua, gas)", "TLN": "Utilities (eléctricas, agua, gas)",
    "BA": "Industria", "LMT": "Industria", "CAT": "Industria", "UAL": "Industria",
    "DAL": "Industria", "AAL": "Industria", "ALK": "Industria",
    "UNH": "Salud", "LLY": "Salud", "JNJ": "Salud", "MDT": "Salud",
}

e = lambda x: html.escape(str(x), quote=False)  # noqa: E731


def watchlist(db: Session) -> set[str]:
    return {v.upper() for (v,) in db.query(TelegramWatch.value).filter_by(watch_type="ticker")}


def sector(db: Session, ticker: str) -> str | None:
    p = db.get(CompanyProfile, ticker)
    return (p.sector if p and p.sector else None) or SECTOR_FALLBACK.get(ticker)


def company_name(db: Session, ticker: str) -> str | None:
    p = db.get(CompanyProfile, ticker)
    if not p or not p.name:
        return None
    return re.sub(r",?\s+(Inc\.?|Corporation|Corp\.?|Company|Co\.?|Holdings?|Ltd\.?|plc|N\.V\.|S\.A\.)$", "", p.name).strip()


def next_earnings(db: Session, ticker: str) -> date | None:
    row = (
        db.query(EarningsCache.date)
        .filter(EarningsCache.ticker == ticker, EarningsCache.date >= date.today())
        .order_by(EarningsCache.date)
        .first()
    )
    return row[0] if row else None


def news(query: str, hours: int = NEWS_HOURS) -> list[dict] | None:
    """Headlines from the last `hours` matching `query`, newest first.
    None when the feed could not be read (unknown, not "no news")."""
    url = f"https://news.google.com/rss/search?q={quote(query)}+when:{max(1, hours // 24)}d&hl=en-US&gl=US&ceid=US:en"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as exc:  # network, 4xx/5xx, bad XML
        logger.warning("alert_context: news for %r failed: %s", query, exc)
        return None
    now = datetime.now(timezone.utc)
    out = []
    for it in root.iter("item"):
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        age = (now - when).total_seconds() / 3600
        if age > hours:
            continue
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(f" - {src}"):
            title = title[: -len(src) - 3]
        out.append({"title": title, "source": src, "hours": age, "link": it.findtext("link")})
    return sorted(out, key=lambda x: x["hours"])


def news_lines(items: list[dict] | None) -> tuple[list[str], bool | None]:
    """Lines for the alert, and whether there was public news (None = unknown)."""
    if items is None:
        return ["📰 No he podido comprobar las noticias."], None
    if not items:
        return [f"🕵️ <b>Sin noticias en {NEWS_HOURS} h.</b> Puede que el mercado sepa algo que aún no se ha publicado, o que sea ruido."], False
    top = items[0]
    ago = f"hace {top['hours']:.0f} h" if top["hours"] >= 1 else "hace menos de 1 h"
    src = f" ({e(top['source'])}, {ago})" if top["source"] else f" ({ago})"
    return [f"📰 <b>Hay noticia:</b> «{e(top['title'][:140])}»{src}. Lo más probable es que sea reacción a ella."], True


def impact(points: float, oi: float, watched: bool, days_to_close: float | None, core_macro: bool = False) -> str:
    """'alto' | 'medio' | 'bajo' from how far it moved, how much money is
    behind it, whether it touches the watchlist and how soon it resolves."""
    score = (2 if points >= 30 else 1 if points >= 20 else 0)
    score += 1 if oi >= 5000 else 0
    score += 1 if watched or core_macro else 0
    score += 1 if days_to_close is not None and days_to_close <= 30 else 0
    return "alto" if score >= 3 else "medio" if score == 2 else "bajo"


IMPACT_ICON = {"alto": "🔴", "medio": "🟠", "bajo": "🟢"}


def ticker_link(t: str) -> str:
    return f'<a href="{WEB}/tickers/{quote(t)}">ficha de {e(t)}</a>'


def _visible(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def split_message(text: str, limit: int = 3900) -> list[str]:
    """Telegram rejects messages over 4096 visible chars (tags don't count):
    cut on blank lines, so a section is never split in half."""
    if _visible(text) <= limit:
        return [text]
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and _visible(cur) + _visible(block) + 2 > limit:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts
