"""Company context for alerts: what it does, its sector, and which members of
Congress bought it and when.

Profile comes from FMP's /stable/profile (free key, same FMP_API_KEY as
earnings/ingest), cached forever in CompanyProfile — a company's sector
doesn't change often and the free plan is 250 calls/day. Only the first
sentence of the (long, English) description is kept and translated with
MyMemory's free API; if translation fails it stays in English.
(Wikipedia/Wikidata were tried first: too sparse for mid/small caps.
Google's unofficial translate endpoint returns 429 from CI-like IPs.)
"""
import logging
import os
import re
from datetime import date, timedelta

import requests
from sqlalchemy.orm import Session

from .models import CompanyProfile, Trade

logger = logging.getLogger(__name__)

SECTORS_ES = {
    "Technology": "Tecnología",
    "Healthcare": "Salud",
    "Financial Services": "Servicios financieros",
    "Consumer Cyclical": "Consumo cíclico",
    "Consumer Defensive": "Consumo básico",
    "Industrials": "Industria",
    "Energy": "Energía",
    "Utilities": "Utilities (eléctricas, agua, gas)",
    "Real Estate": "Inmobiliario",
    "Basic Materials": "Materiales básicos",
    "Communication Services": "Comunicaciones",
}
MAX_SUMMARY_CHARS = 220


def _translate(text: str) -> str | None:
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get", params={"q": text, "langpair": "en|es"}, timeout=15
        )
        data = resp.json()
        out = (data.get("responseData") or {}).get("translatedText")
        if resp.status_code == 200 and out and "MYMEMORY WARNING" not in out.upper():
            return out
    except Exception:
        logger.warning("company: translation failed")
    return None


def _first_sentence(text: str) -> str:
    # Avoid splitting on "Inc." / "Corp." / "U.S." etc.
    m = re.search(r"^(.{40,}?(?<!\b[A-Z])(?<!Inc)(?<!Corp)(?<!Co)(?<!Ltd)\.)\s", text + " ")
    s = (m.group(1) if m else text).strip()
    return s if len(s) <= MAX_SUMMARY_CHARS else s[: MAX_SUMMARY_CHARS - 1].rsplit(" ", 1)[0] + "…"


def get_profile(db: Session, ticker: str) -> CompanyProfile | None:
    cached = db.get(CompanyProfile, ticker)
    if cached:
        return cached
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return None
    try:
        resp = requests.get(
            "https://financialmodelingprep.com/stable/profile", params={"symbol": ticker, "apikey": key}, timeout=15
        )
        rows = resp.json() if resp.status_code == 200 else []
    except Exception:
        logger.warning("company: FMP profile failed for %s", ticker)
        return None
    if not rows or not isinstance(rows, list):
        return None
    p = rows[0]
    sentence = _first_sentence(p.get("description") or "")
    industry = p.get("industry")
    profile = CompanyProfile(
        ticker=ticker,
        name=p.get("companyName"),
        sector=SECTORS_ES.get(p.get("sector"), p.get("sector")),
        industry=(_translate(industry) or industry) if industry else None,
        summary=(_translate(sentence) or sentence) if sentence else None,
    )
    try:
        db.merge(profile)
        db.commit()
    except Exception:  # read-only DB (Vercel): still return it
        db.rollback()
    return profile


def profile_lines(db: Session, ticker: str) -> list[str]:
    import html

    p = get_profile(db, ticker)
    if not p:
        return []
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    lines = []
    if p.sector or p.industry:
        lines.append("🏷 " + " · ".join(e(x) for x in (p.sector, p.industry) if x))
    if p.summary:
        lines.append(f"ℹ️ {e(p.summary)}")
    return lines


def congress_lines(db: Session, ticker: str, years: int = 2, limit: int = 4) -> list[str]:
    """Most recent Congress purchases of this ticker (by transaction date)."""
    import html

    since = date.today() - timedelta(days=365 * years)
    buys = (
        db.query(Trade)
        .filter(Trade.ticker == ticker, Trade.transaction_type == "purchase", Trade.transaction_date >= since)
        .order_by(Trade.transaction_date.desc())
        .all()
    )
    if not buys:
        return ["🏛 Ningún congresista la ha comprado en los últimos 2 años"]
    # One line per member (latest buy + count). Group by normalised name too:
    # the sources sometimes spell the same member two ways ("Gilbert Cisneros"
    # vs "Gilbert Ray Cisneros") under different match keys.
    def key(t: Trade) -> str:
        parts = re.sub(r"[^a-z ]", "", (t.member_name or "").lower()).split()
        return f"{parts[0]} {parts[-1]}" if parts else t.member_match_key

    by_member: dict[str, list[Trade]] = {}
    for t in buys:  # newest first
        by_member.setdefault(key(t), []).append(t)
    lines = [f"🏛 <b>Congreso:</b> {len(buys)} {'compra' if len(buys) == 1 else 'compras'} de {len(by_member)} {'miembro' if len(by_member) == 1 else 'miembros'} en {years} años"]
    for trades in list(by_member.values())[:limit]:
        t = trades[0]
        party = f" ({t.party})" if t.party else ""
        more = f" (+{len(trades) - 1} más)" if len(trades) > 1 else ""
        lines.append(f"   • {html.escape(t.member_name, quote=False)}{party} · {t.transaction_date:%d/%m/%y}{more}")
    if len(by_member) > limit:
        lines.append(f"   • y {len(by_member) - limit} más")
    return lines
