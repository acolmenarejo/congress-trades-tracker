"""Daily Telegram digest: what happened in the last 24h, even when nothing
matched a watchlist (the instant alerts stay silent on quiet weeks, which
looked like a bug in Sept 2026 — it wasn't).

Sent once a day from the frequent bot-poll run (bot/commands.py) as soon as
it's past DIGEST_HOUR_UTC, because GitHub's own `schedule:` lags hours.
Also on demand with /resumen. Sections are separate functions so new
sources (Polymarket, macro) add their own lines.
"""
import html
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .alert_context import WEB, split_message
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
        lines.append(f"  • {star}🟢 {e(t.member_name)} compró {_tk(t.ticker)} · {_usd(t.amount_mid)}")
    big_sales = sorted([t for t in new if t.transaction_type == "sale" and (t.amount_mid or 0) >= 250_000], key=lambda t: -(t.amount_mid or 0))
    for t in big_sales[:2]:
        lines.append(f"  • 🔻 {e(t.member_name)} vendió {_tk(t.ticker)} · {_usd(t.amount_mid)}")
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
        lines.append(f"  • 🟢 {_tk(tk)} · {n} directivo{'s' if n > 1 else ''} · {_usd(sum(t.value_usd for t in ts))}")
    return lines


def _tk(t: str | None) -> str:
    if not t:
        return "<b>?</b>"
    return f'<a href="{WEB}/tickers/{e(t)}"><b>{e(t)}</b></a>'

def _who(ctx: dict) -> str:
    people = [f"{e(c['name'])} (congresista, {c['date']:%d/%m}, {_usd(c['amount'])})" for c in ctx["congress"][:2]]
    people += [f"{e(i['name'])} ({e(i['role'] or 'directivo')}, {i['date']:%d/%m}, {_usd(i['amount'])})"
               for i in ctx["insiders"][:2]]
    return "; ".join(people)


def signal_lines(db: Session) -> list[str]:
    """Open technical signals with when, why, the plan and who was buying."""
    from . import prices, setups

    open_ = db.query(SetupSignal).filter(SetupSignal.outcome.is_(None)).order_by(SetupSignal.signal_date).all()
    if not open_:
        return []
    lines = ["📈 <b>Señales técnicas abiertas</b> <i>(aún sin tocar objetivo ni stop)</i>"]
    for s in open_:
        bars = prices.get_price_series(db, s.ticker, s.signal_date - timedelta(days=5), date.today())
        res = setups.evaluate_signal(bars, s)
        ret = f"{res['return_pct']:+.1f}%" if res["return_pct"] is not None else "?"
        kind = "ruptura" if s.direction == "breakout" else f"nota {s.score:.0f}/100"
        days = (date.today() - s.signal_date).days
        icon = "✅" if (res["return_pct"] or 0) > 0 else "⚠️"
        lines.append(f"  • {icon} {_tk(s.ticker)} · {kind} · aviso del {s.signal_date:%d/%m} (hace {days} días) · va <b>{ret}</b>")
        lines.append(f"    🎯 Entrada {setups._fmt_price(s.entry)} → objetivo {setups._fmt_price(s.target)} · 🛑 stop {setups._fmt_price(s.stop)}")
        reasons = [r for r in (s.reasons or "").split(" | ") if r][:2]
        if reasons:
            lines.append(f"    💡 {e('; '.join(reasons))}")
        who = _who(setups.signal_context(db, s.ticker, s.signal_date))
        lines.append(f"    👥 Compraron antes: {who}" if who else "    👥 Sin compras de congresistas ni directivos en los 90 días previos")
    return lines


SECTIONS = [congress_lines, insider_lines]


def build(db: Session, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    since = now - timedelta(hours=24)
    days = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    lines = [f"📰 <b>Resumen diario</b> · {days[now.weekday()]} {now:%d/%m}", ""]
    for section in (watchlist_lines, *SECTIONS):
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
    lines.append(f'🔗 <a href="{WEB}">Web</a> · <a href="{WEB}/watchlist">Watchlist</a> · '
                 f'<a href="{WEB}/macro">Macro</a> · <a href="{WEB}/directivos">Directivos</a>')
    lines.append("<i>Las alertas instantáneas llegan aparte · /resumen para pedirlo</i>")
    return "\n".join(lines)


def watchlist_lines(db: Session, since: datetime) -> list[str]:
    """What happened today to the tickers on the watchlist, one line each."""
    from . import alert_context, kalshi_company

    wl = sorted(alert_context.watchlist(db))
    if not wl:
        return []
    kalshi = kalshi_company.load(db)
    out = []
    for tk in wl:
        bits = []
        for t in db.query(Trade).filter(Trade.ticker == tk, Trade.created_at >= since,
                                        Trade.transaction_type.in_(["purchase", "sale"])):
            verb = "🟢 compra" if t.transaction_type == "purchase" else "🔻 venta"
            bits.append(f"{verb} de {e(t.member_name)} ({_usd(t.amount_mid)})")
        ins = db.query(InsiderTrade).filter(InsiderTrade.ticker == tk, InsiderTrade.detected_at >= since).count()
        if ins:
            bits.append(f"🏢 {ins} compra{'s' if ins > 1 else ''} de directivos")
        sig = db.query(SetupSignal).filter(SetupSignal.ticker == tk, SetupSignal.outcome.is_(None)).first()
        if sig:
            bits.append("📈 señal técnica abierta")
        for ev in kalshi.get(tk, [])[:2]:
            if ev.get("kind") == "kpi" and ev.get("median_label") and "headcount" not in (ev.get("title") or "").lower():
                flag = " ⚠️ dato flojo" if ev.get("lean") == "weak" else ""
                bits.append(f"🔮 Kalshi espera {e(ev['median_label'])} en «{e(ev['title'])}»{flag}")
        earn = alert_context.next_earnings(db, tk)
        if earn and (earn - now_date()).days <= 14:
            bits.append(f"📅 resultados el {earn:%d/%m}")
        if bits:
            out.append(f"  • {_tk(tk)}: " + " · ".join(bits))
    head = f"⭐ <b>Tu watchlist</b> ({len(wl)} acciones)"
    if not out:
        return [head, "  Sin novedades hoy en tus acciones."]
    return [head] + out


def now_date() -> date:
    return datetime.utcnow().date()


def macro_lines(db: Session) -> list[str]:
    from . import macro

    return macro.digest_lines(db, detailed=True)


def polymarket_lines(db: Session) -> list[str]:
    from . import polymarket

    return polymarket.digest_lines(db)


# Sections without a time window (current state).
EXTRA_SECTIONS: list = [macro_lines, polymarket_lines]


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
        for part in split_message(body):
            send_message(s.chat_id, part)
    db.merge(TelegramState(key=STATE_KEY, value=today))
    db.commit()
    logger.info("digest: sent for %s", today)
    return True
