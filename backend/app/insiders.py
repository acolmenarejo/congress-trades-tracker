"""Insider open-market purchases from SEC Form 4, with Telegram alerts.

Why purchases only: insiders sell for lots of reasons unrelated to the
company's prospects (taxes, diversification, pre-scheduled 10b5-1 plans),
but open-market buys with their own cash (transaction code "P") are one of
the best-documented free signals in the academic literature — and unlike
13F they're public within 2 business days.

Source: EDGAR's "latest filings" Atom feed (type=4), then each filing's full
submission .txt, which contains the Form 4 XML inline (one request per
filing). SEC requires a User-Agent that identifies the requester with a
contact email (anything else gets 403) — set SEC_USER_AGENT, e.g.
"CongressTradesTracker you@example.com". SEC's fair-use limit is 10 req/s.

Alert rule (deliberately strict — every alert is meant to be worth reading):
  - open-market purchase (P), filing total >= MIN_STORE_USD is stored;
  - alert if >= BIG_BUY_USD, or C-suite officer >= OFFICER_BUY_USD, or a
    cluster (>= 2 distinct insiders buying the same ticker in 30 days);
  - 10%-owner-only filers (usually funds) need >= FUND_BUY_USD;
  - skip penny stocks (price < MIN_PRICE).
"""
import html
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests
from sqlalchemy.orm import Session

from .models import InsiderTrade, TelegramState

logger = logging.getLogger(__name__)

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT")
FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
MAX_FEED_PAGES = 10  # 100 entries/page; enough to cover several hours of filings

MIN_STORE_USD = 50_000
BIG_BUY_USD = 500_000
OFFICER_BUY_USD = 150_000
FUND_BUY_USD = 1_000_000
MIN_PRICE = 2.0
CLUSTER_DAYS = 30
C_SUITE = re.compile(r"(?<!vice )(?<!vice-)\b(CEO|CFO|COO|President|Chief|Chair(man|woman|person)?)\b", re.I)

SCAN_STATE_KEY = "insiders_last_scan"
SCAN_EVERY_MINUTES = 30


def _get(url: str, **params) -> requests.Response | None:
    time.sleep(0.15)  # stay well under SEC's 10 req/s
    try:
        resp = requests.get(url, params=params or None, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if resp.status_code != 200:
            logger.warning("insiders: %s -> HTTP %s", url, resp.status_code)
            return None
        return resp
    except Exception:
        logger.warning("insiders: request failed %s", url)
        return None


def _feed_accessions(stop_at: set[str]) -> list[tuple[str, str]]:
    """(accession, submission .txt URL) for recent Form 4 filings, newest
    first, stopping once we reach filings already processed."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for page in range(MAX_FEED_PAGES):
        resp = _get(FEED_URL, action="getcurrent", type="4", owner="include", count=100, start=page * 100, output="atom")
        if resp is None:
            break
        root = ET.fromstring(resp.content)
        entries = root.findall("a:entry", ns)
        if not entries:
            break
        reached_known = False
        for e in entries:
            link = e.find("a:link", ns)
            href = link.get("href") if link is not None else ""
            m = re.search(r"/data/(\d+)/(\d{18})/([\d-]+)-index\.htm", href)
            if not m:
                continue
            cik, _, acc = m.groups()
            if acc in stop_at:
                reached_known = True
                continue
            if acc in seen:
                continue
            seen.add(acc)
            out.append((acc, f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}.txt"))
        if reached_known:
            break
    return out


def _text(node, path: str) -> str | None:
    el = node.find(path)
    if el is None:
        return None
    v = el.find("value")
    txt = (v.text if v is not None else el.text) or ""
    return txt.strip() or None


def _num(node, path: str) -> float | None:
    try:
        return float(_text(node, path))
    except (TypeError, ValueError):
        return None


def parse_form4(xml_text: str) -> dict | None:
    """Aggregate open-market purchases in one Form 4. None if there are none."""
    root = ET.fromstring(xml_text)
    ticker = (_text(root, "issuer/issuerTradingSymbol") or "").upper().strip()
    if not ticker or ticker in ("NONE", "N/A"):
        return None
    owner = root.find("reportingOwner")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    flag = lambda p: (_text(rel, p) or "").lower() in ("1", "true") if rel is not None else False  # noqa: E731
    is_officer, is_director, is_ten = flag("isOfficer"), flag("isDirector"), flag("isTenPercentOwner")
    title = _text(rel, "officerTitle") if rel is not None else None
    role = title or ("Director" if is_director else "10% owner" if is_ten else _text(rel, "otherText") if rel is not None else None)

    shares = value = 0.0
    shares_after = None
    tx_date = None
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if _text(tx, "transactionCoding/transactionCode") != "P":
            continue
        if _text(tx, "transactionAmounts/transactionAcquiredDisposedCode") != "A":
            continue
        sh = _num(tx, "transactionAmounts/transactionShares") or 0
        px = _num(tx, "transactionAmounts/transactionPricePerShare") or 0
        shares += sh
        value += sh * px
        shares_after = _num(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction") or shares_after
        d = _text(tx, "transactionDate")
        if d:
            tx_date = max(tx_date or d[:10], d[:10])
    if shares <= 0:
        return None
    return {
        "ticker": ticker,
        "issuer_name": _text(root, "issuer/issuerName"),
        "insider_name": (_text(owner, "reportingOwnerId/rptOwnerName") if owner is not None else None) or "?",
        "insider_cik": _text(owner, "reportingOwnerId/rptOwnerCik") if owner is not None else None,
        "role": role,
        "is_officer": is_officer,
        "is_director": is_director,
        "is_ten_pct": is_ten,
        "transaction_date": date.fromisoformat(tx_date) if tx_date else None,
        "shares": shares,
        "avg_price": value / shares if shares else None,
        "value_usd": value,
        "shares_after": shares_after,
    }


def _extract_xml(submission: str) -> str | None:
    m = re.search(r"<XML>\s*(.*?)\s*</XML>", submission, re.S)
    return m.group(1) if m else None


def _cluster(db: Session, t: InsiderTrade) -> list[InsiderTrade]:
    since = (t.transaction_date or date.today()) - timedelta(days=CLUSTER_DAYS)
    rows = (
        db.query(InsiderTrade)
        .filter(InsiderTrade.ticker == t.ticker, InsiderTrade.transaction_date >= since, InsiderTrade.accession != t.accession)
        .all()
    )
    return [r for r in rows if r.insider_cik != t.insider_cik]


def should_alert(db: Session, t: InsiderTrade) -> tuple[bool, list[InsiderTrade]]:
    others = _cluster(db, t)
    if (t.avg_price or 0) < MIN_PRICE:
        return False, others
    if t.is_ten_pct and not (t.is_officer or t.is_director):
        return t.value_usd >= FUND_BUY_USD, others
    if t.value_usd >= BIG_BUY_USD:
        return True, others
    if t.is_officer and C_SUITE.search(t.role or "") and t.value_usd >= OFFICER_BUY_USD:
        return True, others
    return len(others) >= 1, others


def format_alert(t: InsiderTrade, others: list[InsiderTrade]) -> str:
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    lines = [
        f"🏢 <b>COMPRA DE DIRECTIVO</b>  <b>{e(t.ticker)}</b>" + (f" — {e(t.issuer_name)}" if t.issuer_name else ""),
        f"👤 {e(t.insider_name)} ({e(t.role or 'insider')})",
        f"💵 ${t.value_usd:,.0f} — {t.shares:,.0f} acciones a ~${t.avg_price:,.2f}",
    ]
    if t.shares_after and t.shares_after > t.shares:
        lines.append(f"📊 Aumenta su posición un {t.shares / (t.shares_after - t.shares) * 100:.0f}% (ahora {t.shares_after:,.0f} acciones)")
    if t.transaction_date:
        lines.append(f"📅 Operación: {t.transaction_date:%d/%m/%Y}")
    if others:
        names = sorted({o.insider_name for o in others})
        total = sum(o.value_usd for o in others) + t.value_usd
        lines.append(f"👥 <b>Compra en grupo:</b> {len(names) + 1} directivos en {CLUSTER_DAYS} días (${total:,.0f} en total): {e(', '.join(names[:4]))}")
    lines += ["", "<i>Compra en mercado abierto con dinero propio (Form 4, código P).</i>"]
    return "\n".join(lines)


def _due(db: Session) -> bool:
    st = db.get(TelegramState, SCAN_STATE_KEY)
    if not st or not st.value:
        return True
    return datetime.utcnow() - datetime.fromisoformat(st.value) >= timedelta(minutes=SCAN_EVERY_MINUTES)


def scan(db: Session, force: bool = False) -> dict:
    """Fetch new Form 4 purchases into InsiderTrade. Throttled to once every
    SCAN_EVERY_MINUTES so it can piggyback on the frequent bot-poll run."""
    stats = {"filings": 0, "purchases": 0}
    if not SEC_USER_AGENT:
        logger.warning("insiders: SEC_USER_AGENT not set, skipping")
        return stats
    if not force and not _due(db):
        return stats

    # First ever scan pages back ~1000 filings: store them for cluster
    # detection, but don't flood Telegram with days-old purchases.
    first_run = db.get(TelegramState, "insiders_seen") is None
    recent = {a for (a,) in db.query(InsiderTrade.accession).order_by(InsiderTrade.detected_at.desc()).limit(500)}
    known = recent | set((db.get(TelegramState, "insiders_seen") or TelegramState(value="")).value.split(","))
    filings = _feed_accessions(known)
    stats["filings"] = len(filings)
    for acc, url in filings:
        resp = _get(url)
        xml_text = _extract_xml(resp.text) if resp is not None else None
        if not xml_text:
            continue
        try:
            p = parse_form4(xml_text)
        except ET.ParseError:
            logger.warning("insiders: bad XML in %s", acc)
            continue
        if p and p["value_usd"] >= MIN_STORE_USD and db.get(InsiderTrade, acc) is None:
            db.add(InsiderTrade(accession=acc, filed_at=datetime.utcnow(), notified=first_run, **p))
            stats["purchases"] += 1

    # Remember the newest accessions seen (purchases or not) so the next scan
    # stops paging there instead of re-downloading non-purchase filings.
    if filings:
        st = db.get(TelegramState, "insiders_seen") or TelegramState(key="insiders_seen")
        st.value = ",".join(a for a, _ in filings[:300])
        db.merge(st)
    db.merge(TelegramState(key=SCAN_STATE_KEY, value=datetime.utcnow().isoformat()))
    db.commit()
    logger.info("insiders: %d filings checked, %d purchases stored", stats["filings"], stats["purchases"])
    return stats


def notify(db: Session) -> int:
    """Send pending purchases that pass should_alert() to every subscriber.
    Independent of watchlists: these go to everyone, always."""
    from .config import TELEGRAM_BOT_TOKEN
    from .models import TelegramSubscriber
    from .telegram_api import send_message

    pending = db.query(InsiderTrade).filter_by(notified=False).order_by(InsiderTrade.value_usd.desc()).all()
    if not pending:
        return 0
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []
    sent = 0
    for t in pending:
        ok, others = should_alert(db, t)
        if ok and chats:
            body = format_alert(t, others)
            sent += sum(send_message(c, body) for c in chats)
        t.notified = True
    db.commit()
    logger.info("insiders: %d pending, %d messages sent", len(pending), sent)
    return sent
