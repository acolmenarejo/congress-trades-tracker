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
  - only "company insiders" count: officers/directors who are people, of an
    operating company. Out: 10%-owner-only filers (funds, insurers buying
    for their book), entities (LLC, LP, Capital...), closed-end funds / ETFs
    / mutual funds / BDCs as issuers, and stocks under MIN_PRICE;
  - alert if the buy grows the insider's position by >= MIN_INCREASE (or a
    C-suite officer by >= CSUITE_MIN_INCREASE) and is >= MIN_ALERT_USD —
    size relative to what they already own says more than the dollar
    amount, which mostly tracks how rich the insider is;
  - or a cluster: >= CLUSTER_MIN_INSIDERS distinct insiders buying the same
    ticker within CLUSTER_DAYS. A cluster goes out as ONE message listing
    every buyer, not one message per filing.
"""
import html
import logging
import math
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
MIN_ALERT_USD = 100_000
MIN_INCREASE = 0.20
CSUITE_MIN_INCREASE = 0.10
MIN_PRICE = 5.0
CLUSTER_DAYS = 30
CLUSTER_MIN_INSIDERS = 3
CLUSTER_MIN_INCREASE = 0.05  # a 1% top-up by a director is routine, not conviction
MAX_FILING_LAG_DAYS = 30  # late filings: the information is stale by the time it's public
C_SUITE = re.compile(r"(?<!vice )(?<!vice-)\b(CEO|CFO|COO|President|Chief|Chair(man|woman|person)?)\b", re.I)

# Issuers that are investment vehicles, not operating companies: a director
# of a closed-end fund buying its shares says nothing about a business.
FUND_ISSUER = re.compile(r"\bfunds?\b|\bBDC\b|\bETF\b|\btrust\b(?!,? inc)|\bportfolio\b|pershing square usa", re.I)
FUND_ROLE = re.compile(r"portfolio manager|advis|chief investment officer", re.I)
# Filers that are entities rather than people (funds, family offices, insurers).
ENTITY_NAME = re.compile(
    r"\b(capital|management|partners|L\.?P|LLC|L\.?L\.?C|fund|trust|insurance|ltd|limited|holdings?|advisors?|"
    r"investments?|group|inc|corp|corporation|company|co|S\.?A|N\.?V|AG|GmbH|plc|foundation)\b\.?",
    re.I,
)
PLAIN_TICKER = re.compile(r"^[A-Z]{1,5}$")

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


def is_company_insider(t: InsiderTrade) -> bool:
    """A person on the inside of an operating company (see module docstring)."""
    if (t.avg_price or 0) < MIN_PRICE:
        return False
    if not (t.is_officer or t.is_director):
        return False  # 10%-owner-only: almost always a fund buying for its book
    if not PLAIN_TICKER.match(t.ticker or "") or (len(t.ticker) == 5 and t.ticker.endswith("X")):
        return False  # foreign listings ("ASX:LNW"), mutual funds ("BBASX")
    if FUND_ISSUER.search(t.issuer_name or "") or FUND_ROLE.search(t.role or ""):
        return False
    if ENTITY_NAME.search(t.insider_name or ""):
        return False
    if t.transaction_date and t.filed_at and (t.filed_at.date() - t.transaction_date).days > MAX_FILING_LAG_DAYS:
        return False
    return not _looks_like_ipo(t)


def _looks_like_ipo(t: InsiderTrade) -> bool:
    """Insiders buying in their own company's IPO file it as an open-market
    purchase (code P), at the round offering price, for a brand-new position.
    That's a listing formality, not a bet on undervaluation."""
    px = t.avg_price or 0
    return position_increase(t) == math.inf and abs(px * 2 - round(px * 2)) < 1e-6


def position_increase(t: InsiderTrade) -> float | None:
    """Shares bought / shares held before. inf for a brand-new position,
    None when the filing doesn't say what they hold afterwards."""
    if not t.shares_after:
        return None
    before = t.shares_after - t.shares
    return t.shares / before if before > 0 else math.inf


def _is_csuite(t: InsiderTrade) -> bool:
    return bool(t.is_officer and C_SUITE.search(t.role or ""))


def _cluster(db: Session, t: InsiderTrade) -> list[InsiderTrade]:
    """Other qualifying insiders' buys of the same ticker in the window."""
    since = (t.transaction_date or date.today()) - timedelta(days=CLUSTER_DAYS)
    rows = (
        db.query(InsiderTrade)
        .filter(InsiderTrade.ticker == t.ticker, InsiderTrade.transaction_date >= since, InsiderTrade.accession != t.accession)
        .all()
    )
    return [r for r in rows if r.insider_cik != t.insider_cik and is_company_insider(r)]


def _counts_for_cluster(t: InsiderTrade) -> bool:
    inc = position_increase(t)
    return inc is None or inc >= CLUSTER_MIN_INCREASE


def should_alert(db: Session, t: InsiderTrade) -> tuple[bool, list[InsiderTrade]]:
    if not is_company_insider(t):
        return False, []
    others = _cluster(db, t)
    committed = {o.insider_cik for o in others if _counts_for_cluster(o)}
    if _counts_for_cluster(t) and len(committed | {t.insider_cik}) >= CLUSTER_MIN_INSIDERS:
        return True, others
    inc = position_increase(t)
    if t.value_usd >= MIN_ALERT_USD and inc is not None:
        if inc >= MIN_INCREASE or (_is_csuite(t) and inc >= CSUITE_MIN_INCREASE):
            return True, others
    return False, others


def _fmt_usd(x: float) -> str:
    return f"${x / 1e6:,.1f}M" if x >= 1e6 else f"${x / 1e3:,.0f}k"


def _pretty(name: str | None) -> str:
    """'LENNAR CORP /NEW/' -> 'Lennar'; 'BERKSHIRE HATHAWAY INC' -> 'Berkshire Hathaway'."""
    if not name:
        return ""
    name = re.sub(r"/[A-Z]+/?", "", name).strip(" ,.")
    name = re.sub(r",?\s+(INC|CORP|CORPORATION|CO|LTD|PLC|LLC|LP|L\.P|N\.V|S\.A|HOLDINGS?)\.?$", "", name, flags=re.I).strip(" ,.")
    return name.title() if name.isupper() else name


_ROLES = [
    (r"chief executive|\bceo\b", "CEO"),
    (r"chief financial|\bcfo\b", "CFO"),
    (r"chief operating|\bcoo\b", "COO"),
    (r"^president", "Presidente"),
    (r"chair", "Presidente del consejo"),
    (r"10% owner", "accionista >10%"),
    (r"^director$", "consejero"),
]


def _role_es(role: str | None) -> str:
    for pat, label in _ROLES:
        if role and re.search(pat, role, re.I):
            return label
    return role or "directivo"


def _fmt_shares(x: float) -> str:
    return f"{x / 1e6:,.2f}M" if x >= 1e6 else f"{x:,.0f}"


def _pos_line(t: InsiderTrade) -> str | None:
    inc = position_increase(t)
    if inc is None:
        return None
    return "posición nueva" if inc == math.inf else f"+{inc * 100:.0f}% su posición"


def format_alert(buys: list[InsiderTrade], analysis=None, db: Session | None = None) -> str:
    """One message per ticker. `buys` are the qualifying purchases (newest
    last); with several insiders it becomes a cluster summary listing each
    buyer. Labelled so each line reads on its own. `analysis` is the optional
    (bars, features, Setup) from setups.analyze() for the technical block."""
    from . import setups
    from .company import congress_lines, profile_lines

    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    t = buys[-1]
    company = _pretty(t.issuer_name) or t.ticker
    insiders = {b.insider_cik or b.insider_name for b in buys}
    total = sum(b.value_usd for b in buys)
    shares = sum(b.shares for b in buys)
    avg_price = sum(b.value_usd for b in buys) / shares if shares else t.avg_price

    if len(insiders) == 1:
        lines = [
            f"🏢 <b>COMPRA DE DIRECTIVO</b> · <b>{e(t.ticker)}</b> ({e(company)})",
            *(profile_lines(db, t.ticker) if db is not None else []),
            "",
            f"👤 <b>Quién:</b> {e(_pretty(t.insider_name))} — {e(_role_es(t.role))}",
            f"💵 <b>Compra:</b> {_fmt_usd(total)} · {_fmt_shares(shares)} acciones a ${avg_price:,.2f}",
        ]
        if t.transaction_date:
            published = f" · detectada {t.filed_at:%d/%m}" if t.filed_at else ""
            lines.append(f"📅 <b>Fecha de compra:</b> {t.transaction_date:%d/%m}{published}")
        pos = _pos_line(t)
        if pos and t.shares_after:
            lines.append(f"📊 <b>Posición:</b> {_fmt_shares(t.shares_after)} acciones tras la compra ({pos})")
    else:
        lines = [
            f"👥 <b>{len(insiders)} DIRECTIVOS COMPRANDO</b> · <b>{e(t.ticker)}</b> ({e(company)})",
            *(profile_lines(db, t.ticker) if db is not None else []),
            "",
            f"💵 <b>Total:</b> {_fmt_usd(total)} en {CLUSTER_DAYS} días · precio medio ${avg_price:,.2f}",
        ]
        per_insider: dict[str, list[InsiderTrade]] = {}
        for b in buys:
            per_insider.setdefault(b.insider_cik or b.insider_name, []).append(b)
        for bs in sorted(per_insider.values(), key=lambda bs: -sum(b.value_usd for b in bs)):
            last = max(bs, key=lambda b: (b.transaction_date or date.min))
            bought = sum(b.shares for b in bs)
            pos = None
            if last.shares_after:
                before = last.shares_after - bought
                pos = "posición nueva" if before <= 0 else f"+{bought / before * 100:.0f}% su posición"
            when = f" · {last.transaction_date:%d/%m}" if last.transaction_date else ""
            lines.append(
                f"• {e(_pretty(last.insider_name))} ({e(_role_es(last.role))}): {_fmt_usd(sum(b.value_usd for b in bs))}"
                + (f", {pos}" if pos else "") + when
            )

    if analysis:
        _, f, st = analysis
        vs_buy = (f["close"] / avg_price - 1) * 100 if avg_price else None
        lines += [
            "",
            f"<b>Análisis técnico</b> · {st.technical:.0f}/100 {setups._score_bar(st.technical)}"
            + (f" · +{st.congress:.0f} por congresistas" if st.congress else ""),
            f"Precio actual {setups._fmt_price(f['close'])}"
            + (f" ({vs_buy:+.0f}% vs. {'su compra' if len(insiders) == 1 else 'su precio medio'})" if vs_buy is not None else ""),
            *[f"✓ {e(r)}" for r in st.reasons[:3]],
            *[f"⚠ {e(r)}" for r in st.risks[:2]],
        ]
        if st.technical < setups.ALERT_MIN_SCORE:
            lines.append("⚠ Técnico aún sin confirmar: mejor esperar a que acompañe")
        lines += ["", *setups.plan_lines(f)]
    if db is not None:
        lines += ["", *congress_lines(db, t.ticker)]
    lines += ["", "<i>Compra en mercado abierto (Form 4) · no es asesoramiento</i>"]
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
    from . import setups
    from .telegram_api import send_alert

    pending = db.query(InsiderTrade).filter_by(notified=False).order_by(InsiderTrade.value_usd.desc()).all()
    if not pending:
        return 0
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []

    # One message per ticker: several insiders of the same company filing in
    # the same scan (typical of a cluster) are summarised together, along with
    # the qualifying buys from earlier in the window.
    groups: dict[str, dict[str, InsiderTrade]] = {}
    for t in pending:
        ok, others = should_alert(db, t)
        t.notified = True
        if not ok:
            continue
        g = groups.setdefault(t.ticker, {})
        for b in (t, *others):
            g[b.accession] = b

    sent = 0
    for ticker, by_acc in groups.items():
        buys = sorted(by_acc.values(), key=lambda b: (b.transaction_date or date.min, b.filed_at or datetime.min))
        if not chats:
            continue
        try:
            analysis = setups.analyze(db, ticker)
        except Exception:
            logger.exception("insiders: technical analysis failed for %s", ticker)
            analysis = None
        body = format_alert(buys, analysis, db)
        png = None
        if analysis:
            bars, f, _ = analysis
            label = "Compra directivo" if len({b.insider_cik for b in buys}) == 1 else "Compras directivos"
            dated = [b for b in buys if b.avg_price]
            marker = None
            if dated:
                sh = sum(b.shares for b in dated)
                first = min((b.transaction_date for b in dated if b.transaction_date), default=date.today())
                marker = [(first, sum(b.value_usd for b in dated) / sh, label)]
            png = setups.render_chart(ticker, bars, f, markers=marker)
        sent += sum(send_alert(c, body, png) for c in chats)
    db.commit()
    logger.info("insiders: %d pending, %d tickers alerted, %d messages sent", len(pending), len(groups), sent)
    return sent
