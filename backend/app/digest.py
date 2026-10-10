"""Daily Telegram digest: what happened in the last 24h, even when nothing
matched a watchlist (the instant alerts stay silent on quiet weeks, which
looked like a bug in Sept 2026 — it wasn't).

Sent once a day from the frequent bot-poll run (bot/commands.py) as soon as
it's past DIGEST_HOUR_UTC, because GitHub's own `schedule:` lags hours.
Also on demand with /resumen. Sections are separate functions so new
sources (Polymarket, macro) can append their own lines.
"""
import html
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .models import InsiderTrade, SetupSignal, TelegramState, TelegramSubscriber, TelegramWatch, Trade

logger = logging.getLogger(__name__)

DIGEST_HOUR_UTC = 7  # 9:00 in Madrid (summer), 8:00 in winter
STATE_KEY = "digest_last_sent"
TOP_N = 5

e = lambda x: html.escape(str(x), quote=False)  # noqa: E731


def _usd(x: float | None) -> str:
    if not x:
        return "?"
    return f"${x / 1e6:,.1f}M" if x >= 1e6 else f"${x / 1e3:,.0f}k"


def congress_lines(db: Session, since: datetime) -> list[str]:
    new = (
        db.query(Trade)
        .filter(Trade.created_at >= since, Trade.transaction_type.in_(["purchase", "sale"]))
        .all()
    )
    if not new:
        return ["🏛 <b>Congreso:</b> ninguna operación nueva publicada"]
    watched_members = {v for (v,) in db.query(TelegramWatch.value).filter_by(watch_type="member")}
    watched_tickers = {v for (v,) in db.query(TelegramWatch.value).filter_by(watch_type="ticker")}
    buys = [t for t in new if t.transaction_type == "purchase"]
    lines = [f"🏛 <b>Congreso:</b> {len(new)} operaciones nuevas ({len(buys)} compras, {len(new) - len(buys)} ventas)"]
    top = sorted(buys, key=lambda t: -(t.amount_mid or 0))[:TOP_N]
    for t in top:
        star = "⭐ " if t.member_match_key in watched_members or t.ticker in watched_tickers else ""
        lines.append(f"  • {star}{e(t.member_name)} compró <b>{e(t.ticker or '?')}</b> · {_usd(t.amount_mid)}")
    big_sales = sorted([t for t in new if t.transaction_type == "sale" and (t.amount_mid or 0) >= 250_000], key=lambda t: -(t.amount_mid or 0))
    for t in big_sales[:2]:
        lines.append(f"  • {e(t.member_name)} vendió <b>{e(t.ticker or '?')}</b> · {_usd(t.amount_mid)}")
    return lines


def insider_lines(db: Session, since: datetime) -> list[str]:
    from . import insiders

    rows = db.query(InsiderTrade).filter(InsiderTrade.detected_at >= since).all()
    groups: dict[str, list[InsiderTrade]] = {}
    for t in rows:
        if insiders.should_alert(db, t)[0]:
            groups.setdefault(t.ticker, []).append(t)
    if not groups:
        return [f"🏢 <b>Directivos:</b> {len(rows)} compras registradas, ninguna relevante"]
    lines = [f"🏢 <b>Directivos:</b> {len(groups)} empresas con compras relevantes"]
    for tk, ts in sorted(groups.items(), key=lambda kv: -sum(t.value_usd for t in kv[1]))[:TOP_N]:
        n = len({t.insider_cik for t in ts})
        lines.append(f"  • <b>{e(tk)}</b> · {n} directivo{'s' if n > 1 else ''} · {_usd(sum(t.value_usd for t in ts))}")
    return lines


def signal_lines(db: Session) -> list[str]:
    from . import prices, setups

    open_ = db.query(SetupSignal).filter(SetupSignal.outcome.is_(None)).order_by(SetupSignal.signal_date).all()
    if not open_:
        return []
    lines = ["📈 <b>Señales abiertas</b>"]
    for s in open_:
        bars = prices.get_price_series(db, s.ticker, s.signal_date - timedelta(days=5), date.today())
        res = setups.evaluate_signal(bars, s)
        ret = f"{res['return_pct']:+.1f}%" if res["return_pct"] is not None else "?"
        kind = "ruptura" if s.direction == "breakout" else "señal"
        lines.append(f"  • <b>{e(s.ticker)}</b> ({kind} del {s.signal_date:%d/%m}): {ret}")
    return lines


SECTIONS = [congress_lines, insider_lines]


def build(db: Session, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    since = now - timedelta(hours=24)
    lines = [f"📰 <b>Resumen diario</b> · {now:%d/%m}", ""]
    for section in SECTIONS:
        try:
            lines += section(db, since) + [""]
        except Exception:
            logger.exception("digest: section %s failed", section.__name__)
    for extra in (signal_lines, *EXTRA_SECTIONS):
        try:
            got = extra(db)
            if got:
                lines += got + [""]
        except Exception:
            logger.exception("digest: section %s failed", extra.__name__)
    lines.append("<i>Las alertas instantáneas siguen llegando aparte · /resumen para pedirlo</i>")
    return "\n".join(lines)


def polymarket_lines(db: Session) -> list[str]:
    from . import polymarket

    return polymarket.digest_lines(db)


# Sections without a time window (current state).
EXTRA_SECTIONS: list = [polymarket_lines]


def maybe_send(db: Session, now: datetime | None = None) -> bool:
    """Send today's digest once, after DIGEST_HOUR_UTC."""
    from .config import TELEGRAM_BOT_TOKEN
    from .telegram_api import send_message

    now = now or datetime.utcnow()
    today = now.date().isoformat()
    st = db.get(TelegramState, STATE_KEY)
    if now.hour < DIGEST_HOUR_UTC or (st and st.value == today) or not TELEGRAM_BOT_TOKEN:
        return False
    body = build(db, now)
    for s in db.query(TelegramSubscriber).all():
        send_message(s.chat_id, body)
    db.merge(TelegramState(key=STATE_KEY, value=today))
    db.commit()
    logger.info("digest: sent for %s", today)
    return True
