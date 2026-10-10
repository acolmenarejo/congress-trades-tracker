"""Polymarket "suspicious bet" scanner.

What we look for (the user's own example: someone puts $10M on "Maduro
arrested today"): a big BUY on an outcome the market thinks is unlikely,
in a market that resolves soon, ideally from a wallet with little history.
Either it's information the market doesn't have yet, or a very odd bet —
both worth a look, and worth a Telegram alert when the market is about
finance/economy (Fed, tariffs, oil, companies...) or, at a higher bar,
geopolitics that moves markets.

Bets are judged per position, not per trade: this run's buys (from $2k)
are grouped by wallet + market + outcome and topped up with the wallet's
whole position from data-api /positions, so a bet split into pieces or
built up over days still counts as one big bet.

Suspicion score, 0-100 (see `score_trade`):
  size     0-30  $10k → 0 ... $1M+ → 30 (log scale)
  odds     0-25  price paid 50% → 0 ... ≤ 5% → 25 (long shot)
  horizon  0-20  resolves in ≤ 1 day → 20, ≤ 3 d → 15, ≤ 7 d → 10, ≤ 14 d → 6, ≤ 60 d → 3
  wallet   0-20  ≤ 3 markets ever traded → 20, ≤ 10 → 12, ≤ 30 → 5
  share    0-5   trade ≥ 10% of the market's liquidity
Stored (shown on the web) if score ≥ STORE_MIN_SCORE; alerted per ALERT rules below. Sports,
esports and short-term crypto "up or down" markets are skipped entirely:
big one-sided bets there are normal gambling, not information.

Wallets are pseudonymous: we never claim who's behind one. Public APIs, no
key: data-api (trades, wallet stats) and gamma-api (market metadata).
"""
import html
import logging
import math
import re
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from .models import PolymarketAlert, TelegramState

logger = logging.getLogger("polymarket")

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

MIN_TRADE_USD = 10_000  # per wallet+market position, summed across buys
MIN_CHUNK_USD = 2_000  # smallest single buy we fetch, to catch bets split into pieces
PAGE_SIZE = 500
MAX_PAGES = 6
STORE_MIN_SCORE = 25  # web list; Telegram has its own, higher bars below
ALERT_MIN_SCORE_MARKETS = 55
ALERT_MIN_SCORE_GEO = 75
MAX_ALERTS_PER_RUN = 5
STATE_KEY = "polymarket_last_ts"

SKIP = re.compile(
    r"\b(nfl|nba|mlb|nhl|wnba|mls|ufc|epl|uefa|fifa|premier league|la liga|serie a|bundesliga|champions league|"
    r"tennis|atp|wta|golf|pga|f1|formula 1|nascar|boxing|cricket|esports?|dota|cs2|counter-strike|valorant|"
    r"league of legends|lol:|overwatch|super bowl|world series|stanley cup|grand slam|match|game \d|"
    r"vs\.?|o/u|spread|touchdown|goals?|oscars?|grammys?|emmys?|eurovision|box office|album|song|"
    r"up or down|bitcoin above|ethereum above|btc|eth price|solana above|xrp above|exact score|fc|tweets?|"
    r"win on \d{4}-\d\d-\d\d|price of (bitcoin|ethereum|solana|xrp)|"
    r"(bitcoin|ethereum|solana|xrp|dogecoin) (dip|reach|hit|above|below))\b",
    re.I,
)
MARKETS = re.compile(
    r"\b(fed|fomc|interest rates?|rate (cut|hike)|bps|powell|warsh|inflation|cpi|pce|gdp|recession|"
    r"unemployment|jobs report|payrolls|tariffs?|trade deal|treasury|yields?|bond|debt ceiling|shutdown|default|"
    r"s&p|nasdaq|dow|stock|shares|earnings|ipo|merger|acqui\w+|bankrupt\w*|ceo|sec\b|etf|oil|opec|brent|wti|"
    r"gas prices|gold|silver|copper|dollar|euro|yen|yuan|nvidia|apple|tesla|microsoft|amazon|google|alphabet|"
    r"meta|openai|anthropic|boeing|intel|tsmc|sanctions?|ecb|bank of japan|boj|central bank)\b",
    re.I,
)
GEO = re.compile(
    r"\b(arrest\w*|captured?|ousted?|resign\w*|coup|invade\w*|invasion|strikes?|attack\w*|war|ceasefire|"
    r"missile|nuclear|regime|maduro|venezuela\w*|iran\w*|blockade|israel\w*|gaza|hezbollah|houthis?|taiwan|china|russia|"
    r"ukraine|putin|zelensky|xi jinping|kim jong|north korea|cuba|hormuz)\b",
    re.I,
)

# What a resolution could move, for the alert's "qué podría implicar" line.
# Deliberately coarse: a pointer to what to look at, not a trade.
IMPLICATIONS = [
    (re.compile(r"\b(fed|fomc|rate cut|interest rates?|powell|warsh|bps)\b", re.I),
     "Tipos de la Fed: mueve bonos (TLT), dólar, bancos (XLF) y tecnológicas de crecimiento (QQQ)."),
    (re.compile(r"\b(cpi|inflation|pce)\b", re.I),
     "Dato de inflación: bonos (TLT), expectativas de tipos y oro (GLD)."),
    (re.compile(r"\b(tariffs?|trade deal|sanctions?)\b", re.I),
     "Aranceles/sanciones: importadores y retail, industriales, emergentes y el dólar."),
    (re.compile(r"\b(oil|opec|brent|wti|maduro|venezuela|iran|hormuz|houthis?|saudi)\b", re.I),
     "Oferta de petróleo: crudo (USO), petroleras (XLE), aerolíneas y refinerías."),
    (re.compile(r"\b(taiwan|china|xi jinping|tsmc)\b", re.I),
     "China/Taiwán: semiconductores (SMH, TSM, NVDA) y cadena de suministro."),
    (re.compile(r"\b(russia|ukraine|putin|zelensky|nuclear|war|invasion|missile)\b", re.I),
     "Riesgo geopolítico: defensa (ITA, LMT, RTX), oro (GLD), gas europeo, bolsa europea."),
    (re.compile(r"\b(shutdown|debt ceiling|default|treasury)\b", re.I),
     "Fiscal EE. UU.: letras del Tesoro, liquidez (TGA) y volatilidad (VIX)."),
    (re.compile(r"\b(recession|unemployment|payrolls|jobs report|gdp)\b", re.I),
     "Ciclo económico: bonos, cíclicas vs. defensivas y pequeñas compañías (IWM)."),
    (re.compile(r"\b(earnings|ipo|merger|acqui\w+|bankrupt\w*|ceo|nvidia|apple|tesla|microsoft|amazon|google|alphabet|meta|boeing|intel)\b", re.I),
     "Evento de empresa: la acción afectada y su sector directamente."),
]


def _get(url: str, params: dict):
    resp = requests.get(url, params=params, timeout=25)
    resp.raise_for_status()
    return resp.json()


def classify(text: str) -> str | None:
    """'mercados' | 'geopolitica' | 'otros', or None to skip the market."""
    if SKIP.search(text):
        return None
    if MARKETS.search(text):
        return "mercados"
    if GEO.search(text):
        return "geopolitica"
    return "otros"


def implication(text: str) -> str | None:
    for pat, line in IMPLICATIONS:
        if pat.search(text):
            return line
    return None


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_trade(usd: float, price: float, hours_to_end: float | None, wallet_markets: int | None,
                liquidity: float | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    pts = 30 * _clip(math.log10(max(usd, 1) / MIN_TRADE_USD) / 2)
    pts_odds = 25 * _clip((0.5 - price) / 0.45)
    pts += pts_odds
    if price <= 0.2:
        reasons.append(f"apuesta a algo poco probable ({price * 100:.0f}% según el mercado)")
    if hours_to_end is not None and hours_to_end >= 0:
        for limit, p in ((24, 20), (72, 15), (168, 10), (336, 6), (1440, 3)):
            if hours_to_end <= limit:
                pts += p
                reasons.append("se resuelve en " + (f"{hours_to_end:.0f} h" if hours_to_end < 48 else f"{hours_to_end / 24:.0f} días"))
                break
    if wallet_markets is not None:
        for limit, p in ((3, 20), (10, 12), (30, 5)):
            if wallet_markets <= limit:
                pts += p
                reasons.append(f"cartera casi nueva ({wallet_markets} mercados en total)")
                break
    if liquidity and usd / liquidity >= 0.10:
        pts += 5
        reasons.append(f"{usd / liquidity * 100:.0f}% de la liquidez del mercado")
    return round(pts, 1), reasons


def _recent_big_trades(since_ts: int) -> list[dict]:
    out: list[dict] = []
    for page in range(MAX_PAGES):
        try:
            rows = _get(f"{DATA_BASE}/trades", {
                "filterType": "CASH", "filterAmount": MIN_CHUNK_USD, "takerOnly": "true",
                "side": "BUY", "limit": PAGE_SIZE, "offset": page * PAGE_SIZE,
            })
        except Exception:
            logger.exception("polymarket: trades page %d failed", page)
            break
        if not rows:
            break
        out += [r for r in rows if (r.get("timestamp") or 0) > since_ts]
        if min(r.get("timestamp") or 0 for r in rows) <= since_ts:
            break
    return out


def _markets(condition_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(condition_ids), 40):
        try:
            for m in _get(f"{GAMMA_BASE}/markets", {"condition_ids": condition_ids[i : i + 40], "limit": 100}):
                out[m.get("conditionId")] = m
        except Exception:
            logger.exception("polymarket: market metadata failed")
    return out


def _wallet_markets(wallet: str, cache: dict) -> int | None:
    if wallet not in cache:
        try:
            cache[wallet] = int(_get(f"{DATA_BASE}/traded", {"user": wallet}).get("traded"))
        except Exception:
            cache[wallet] = None
    return cache[wallet]


def _position(wallet: str, condition_id: str, outcome_index) -> dict | None:
    """The wallet's whole position on one outcome (all its buys, any day)."""
    try:
        rows = _get(f"{DATA_BASE}/positions", {"user": wallet, "market": condition_id, "sizeThreshold": 0})
    except Exception:
        return None
    for r in rows or []:
        if r.get("conditionId") == condition_id and str(r.get("outcomeIndex")) == str(outcome_index):
            return r
    return None


def _hours_to_end(m: dict, now: datetime) -> float | None:
    end = m.get("endDate")
    if not end:
        return None
    try:
        return (datetime.fromisoformat(end.replace("Z", "+00:00")) - now).total_seconds() / 3600
    except ValueError:
        return None


def scan(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    st = db.get(TelegramState, STATE_KEY)
    since = int(st.value) if st and st.value else int(now.timestamp()) - 6 * 3600
    trades = _recent_big_trades(since)
    stats = {"big_trades": len(trades), "stored": 0}
    if not trades:
        return stats

    texts = {t["conditionId"]: f"{t.get('title', '')} {t.get('slug', '')} {t.get('eventSlug', '')}" for t in trades}
    keep = {cid for cid, txt in texts.items() if classify(txt)}
    markets = _markets(sorted(keep))

    # Group this run's buys by wallet + market + outcome: a bet split into
    # several pieces (or built up over days) counts as one position.
    groups: dict[tuple, list[dict]] = {}
    for t in trades:
        if t.get("conditionId") not in keep or not t.get("proxyWallet"):
            continue
        try:
            t["_price"] = float(t["price"])
            t["_usd"] = float(t["size"]) * t["_price"]
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < t["_price"] < 1:
            groups.setdefault((t["proxyWallet"], t["conditionId"], t.get("outcomeIndex")), []).append(t)

    wallets: dict = {}
    for (wallet, cid, oidx), buys in groups.items():
        run_usd = sum(b["_usd"] for b in buys)
        run_price = sum(b["_usd"] * b["_price"] for b in buys) / run_usd
        # Small pieces only matter on long shots; skip the per-wallet API calls otherwise.
        if run_usd < MIN_TRADE_USD and run_price > 0.3:
            continue
        m = markets.get(cid, {})
        liquidity = float(m.get("liquidity") or 0) or None
        hours = _hours_to_end(m, now)
        if hours is not None and hours < 0:
            continue  # already past its end date: just settling, not a bet on news
        pos = _position(wallet, cid, oidx)
        usd, price, n_buys = run_usd, run_price, len(buys)
        if pos:
            try:
                total = float(pos.get("initialValue") or 0)
                if total > usd:
                    usd, price = total, float(pos.get("avgPrice") or price)
            except (TypeError, ValueError):
                pass
        if usd < MIN_TRADE_USD:
            continue
        # Cheap pre-check before the wallet-history API call: without a fresh
        # wallet (max 20 pts) this position can't reach the store threshold.
        base, _ = score_trade(usd, price, hours, None, liquidity)
        if base + 20 < STORE_MIN_SCORE:
            continue
        nmk = _wallet_markets(wallet, wallets)
        score, reasons = score_trade(usd, price, hours, nmk, liquidity)
        if n_buys > 1 or usd > run_usd * 1.2:
            reasons.append("posición acumulada en varias compras" + (f" ({n_buys} en la última hora)" if n_buys > 1 else ""))
        if score < STORE_MIN_SCORE:
            continue
        last = max(buys, key=lambda b: b.get("timestamp") or 0)
        key = f"pos:{wallet}:{cid}:{oidx}"
        row = db.query(PolymarketAlert).filter_by(tx_hash=key).one_or_none()
        if row and usd < row.size_usd * 1.5:
            continue  # already recorded; only a much bigger position is news again
        text = f"{last.get('title', '')} {m.get('question', '')} {m.get('description', '')[:300]}"
        ts = last.get("timestamp")
        fields = dict(
            event_title=last.get("title") or "",
            market_question=m.get("question") or last.get("title") or "",
            outcome=last.get("outcome"),
            side="BUY",
            price=price,
            size_usd=usd,
            liquidity_usd=liquidity,
            pct_of_liquidity=usd / liquidity if liquidity else None,
            wallet=wallet,
            tag=classify(text) or "otros",
            event_slug=last.get("eventSlug"),
            market_slug=last.get("slug"),
            trade_timestamp=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
            score=score,
            reasons=" | ".join(reasons),
            hours_to_end=hours,
            wallet_markets=nmk,
            implication=implication(text),
            notified=False,
        )
        if row:
            for k, v in fields.items():
                setattr(row, k, v)
            row.detected_at = datetime.utcnow()
        else:
            db.add(PolymarketAlert(tx_hash=key, **fields))
        stats["stored"] += 1

    db.merge(TelegramState(key=STATE_KEY, value=str(max(t.get("timestamp") or 0 for t in trades))))
    db.commit()
    logger.info("polymarket: %s", stats)
    return stats


def should_alert(a: PolymarketAlert) -> bool:
    if a.tag == "mercados":
        return (a.score or 0) >= ALERT_MIN_SCORE_MARKETS
    if a.tag == "geopolitica":
        return (a.score or 0) >= ALERT_MIN_SCORE_GEO
    return False


def format_alert(a: PolymarketAlert) -> str:
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    payout = a.size_usd / a.price if a.price else None
    lines = [
        f"🎯 <b>APUESTA SOSPECHOSA</b> · Polymarket · {a.score:.0f}/100",
        f"<b>{e(a.market_question)}</b>",
        "",
        f"💵 {_usd(a.size_usd)} a «{e(a.outcome)}» a {a.price * 100:.0f}¢"
        + (f" → cobraría {_usd(payout)} si acierta" if payout else ""),
        *[f"✓ {e(r)}" for r in (a.reasons or "").split(" | ") if r],
    ]
    if a.implication:
        lines += ["", f"📌 <b>Qué podría implicar:</b> {e(a.implication)}"]
    if a.event_slug:
        lines += ["", f'<a href="https://polymarket.com/event/{e(a.event_slug)}">Ver mercado</a> · cartera {e((a.wallet or "")[:10])}…']
    lines += ["", "<i>Cartera anónima: no sabemos quién es · no es asesoramiento</i>"]
    return "\n".join(lines)


def _usd(x: float | None) -> str:
    if not x:
        return "?"
    return f"${x / 1e6:,.1f}M" if x >= 1e6 else f"${x / 1e3:,.0f}k"


def notify(db: Session) -> int:
    from .config import TELEGRAM_BOT_TOKEN
    from .models import TelegramSubscriber
    from .telegram_api import send_message

    pending = db.query(PolymarketAlert).filter(PolymarketAlert.notified.is_(False)).order_by(PolymarketAlert.score.desc()).all()
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []
    sent = 0
    for a in pending:
        if should_alert(a) and chats and sent < MAX_ALERTS_PER_RUN * len(chats):
            sent += sum(send_message(c, format_alert(a)) for c in chats)
        a.notified = True
    db.commit()
    return sent


def digest_lines(db: Session) -> list[str]:
    """Top suspicious bets of the last 24h, for the daily digest."""
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.query(PolymarketAlert)
        .filter(PolymarketAlert.detected_at >= since, PolymarketAlert.score.isnot(None))
        .order_by(PolymarketAlert.score.desc())
        .limit(3)
        .all()
    )
    if not rows:
        return []
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    return ["🎯 <b>Polymarket: apuestas más raras (24 h)</b>"] + [
        f"  • {r.score:.0f}/100 · {_usd(r.size_usd)} a «{e(r.outcome)}» ({r.price * 100:.0f}¢) en {e(r.market_question[:70])}"
        for r in rows
    ]
