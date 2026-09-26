"""Same logic as bot/notify.py, ported into app/ for the same reason as
bot_commands.py — see that file's docstring."""
import html
import logging
from datetime import date, timedelta

from sqlalchemy import func

from . import prices
from .conflicts import detect_conflict
from .config import TELEGRAM_BOT_TOKEN
from .database import SessionLocal, init_db
from .models import EarningsCache, Member, MemberRanking, Trade, TelegramWatch
from .telegram_api import send_message

logger = logging.getLogger("bot.notify")

SITE_URL = "https://congress-trades-tracker.netlify.app"

_TYPE_EMOJI = {"purchase": "🟢 COMPRA", "sale": "🔴 VENTA", "exchange": "🔁 CANJE"}
_TYPE_VERB = {"purchase": "compra", "sale": "venta", "exchange": "canje"}
_CHAMBER_LABEL = {"house": "Cámara de Representantes", "senate": "Senado"}
_PARTY_BADGE = {"D": "🔵 Demócrata", "R": "🔴 Republicano", "I": "⚪ Independiente"}
# "{name}" is the member — the PTR "owner" field says whose account the trade
# was in, which is often not the member themselves.
_OWNER_LABEL = {
    "self": "el propio {name}",
    "spouse": "el/la cónyuge de {name}",
    "joint": "cuenta conjunta de {name} y su cónyuge",
    "child": "un hijo/a dependiente de {name}",
    "dependent": "un hijo/a dependiente de {name}",
}

# Mirrors frontend/src/lib/highValue.ts — STOCK Act disclosure bands, not
# arbitrary cutoffs ($250,001-$500,000 and $1,000,001-$5,000,000 are real
# reporting tiers).
HIGH_VALUE_THRESHOLD = 250_000
VERY_HIGH_VALUE_THRESHOLD = 1_000_000

# STOCK Act: a PTR is due within 45 days of the transaction.
STOCK_ACT_DEADLINE_DAYS = 45
CLUSTER_WINDOW_DAYS = 30
EARNINGS_WINDOW_DAYS = 14
MAX_SAME_FILING_ITEMS = 8


def _e(value) -> str:
    """Escape for Telegram's HTML parse mode — a bare '&' or '<' in an asset
    name makes Telegram reject the whole message."""
    return html.escape(str(value), quote=False)


def _trade_value(trade: Trade) -> float:
    return trade.amount_range_low or trade.amount_mid or 0


def _high_value_line(trade: Trade) -> str | None:
    value = _trade_value(trade)
    if value >= VERY_HIGH_VALUE_THRESHOLD:
        return "💰💰💰 <b>IMPORTE MUY ALTO</b> 💰💰💰"
    if value >= HIGH_VALUE_THRESHOLD:
        return "💰 <b>IMPORTE ALTO</b>"
    return None


def _format_amount(low, high) -> str:
    if low is None and high is None:
        return "importe desconocido"
    if high is None:
        return f"más de ${low:,.0f}"
    if low == high:
        return f"${low:,.0f}"
    return f"${low:,.0f} – ${high:,.0f}"


def _member_line(trade: Trade, member: Member | None) -> str:
    """'👤 Congresista: Pete Sessions · 🔴 Republicano · TX-17 · Cámara de Representantes'."""
    parts = [f"👤 Congresista: <b>{_e(member.name if member else trade.member_name)}</b>"]
    party = (member.party if member else None) or trade.party
    if party in _PARTY_BADGE:
        parts.append(_PARTY_BADGE[party])
    district = member.district if member else None
    state = (member.state if member else None) or trade.state
    if district and len(district) > 2 and district[2:].isdigit():
        parts.append(f"{district[:2]}-{int(district[2:])}")
    elif state:
        parts.append(_e(state))
    chamber = (member.chamber if member else None) or trade.chamber
    parts.append(_CHAMBER_LABEL.get(chamber, _e(chamber or "?")))
    return " · ".join(parts)


def _owner_line(trade: Trade) -> str:
    name = _e(trade.member_name)
    owner = (trade.owner or "").strip().lower()
    if not owner:
        label = f"{name} (el filing no indica si fue él/ella, su cónyuge o un dependiente)"
    elif owner in _OWNER_LABEL:
        label = _OWNER_LABEL[owner].format(name=name)
    else:
        label = f"{_e(trade.owner)} (declarado por {name})"
    return f"🧾 Quién operó: <b>{label}</b>"


def _dates_lines(trade: Trade) -> list[str]:
    lines = [f"📅 Operación: {trade.transaction_date or 'desconocida'}"]
    disclosure = f"📨 Publicado: {trade.disclosure_date or 'desconocido'}"
    lag = trade.disclosure_lag_days
    if lag is not None:
        disclosure += f" ({lag} día{'s' if lag != 1 else ''} después)"
        if lag > STOCK_ACT_DEADLINE_DAYS:
            disclosure += f" ⚠️ <b>fuera de plazo</b> (límite legal: {STOCK_ACT_DEADLINE_DAYS} días)"
    lines.append(disclosure)
    return lines


def _conflict_line(trade: Trade, member: Member | None) -> str | None:
    """Prominent warning when the member sits on a committee with plausible
    jurisdiction over the traded company's sector — see conflicts.py for the
    (deliberately conservative) heuristic and its caveats."""
    match = detect_conflict(trade.ticker, member.committees if member else None)
    if not match:
        return None
    return (
        "🚨 <b>POSIBLE CONFLICTO DE INTERÉS</b> 🚨\n"
        f"{_e(trade.member_name)} es miembro de: <b>{_e(' · '.join(match.committees))}</b>\n"
        f"(competencia sobre {_e(', '.join(match.sectors))} — señal heurística automática, no una acusación)"
    )


def _same_filing_line(db, trade: Trade) -> str | None:
    """Other lines of the same PTR — a member dumping 5 tech names in one
    filing reads very differently from a single isolated trade."""
    if not trade.filing_url:
        return None
    others = (
        db.query(Trade)
        .filter(Trade.filing_url == trade.filing_url, Trade.id != trade.id)
        .all()
    )
    seen: dict[tuple, Trade] = {}
    for other in others:
        if (other.ticker, other.transaction_type) != (trade.ticker, trade.transaction_type):
            seen.setdefault((other.ticker, other.transaction_type), other)
    if not seen:
        return None
    items = [
        f"{_TYPE_VERB.get(t.transaction_type, t.transaction_type or '?')} ${_e(t.ticker)}"
        for t in sorted(seen.values(), key=lambda t: -(t.amount_range_low or 0))
    ]
    extra = len(items) - MAX_SAME_FILING_ITEMS
    text = ", ".join(items[:MAX_SAME_FILING_ITEMS]) + (f" y {extra} más" if extra > 0 else "")
    return f"🗂 En el mismo filing también: {text}"


def _member_ticker_history_line(db, trade: Trade) -> str | None:
    """Has this member traded this ticker before? Repeat buying (or a first
    sale after years of holding) is more telling than a one-off."""
    if not trade.transaction_date:
        return None
    since = trade.transaction_date - timedelta(days=730)
    previous = (
        db.query(Trade)
        .filter(
            Trade.member_match_key == trade.member_match_key,
            Trade.ticker == trade.ticker,
            Trade.id != trade.id,
            Trade.transaction_date >= since,
            Trade.transaction_date < trade.transaction_date,
        )
        .order_by(Trade.transaction_date.desc())
        .all()
    )
    if not previous:
        return f"🆕 Primera operación de {_e(trade.member_name)} en ${_e(trade.ticker)} en los últimos 2 años"
    buys = sum(1 for t in previous if t.transaction_type == "purchase")
    sells = sum(1 for t in previous if t.transaction_type == "sale")
    last = previous[0]
    return (
        f"🔄 {_e(trade.member_name)} ya operó ${_e(trade.ticker)} {len(previous)} "
        f"{'vez' if len(previous) == 1 else 'veces'} en 2 años "
        f"({buys} compras, {sells} ventas) — la última, {_TYPE_VERB.get(last.transaction_type, '?')} "
        f"el {last.transaction_date}"
    )


def _cluster_line(db, trade: Trade) -> str | None:
    """Other members trading the same ticker around the same time — several
    members independently buying the same name is the classic signal."""
    if not trade.transaction_date:
        return None
    window = timedelta(days=CLUSTER_WINDOW_DAYS)
    rows = (
        db.query(Trade.member_match_key, Trade.member_name, Trade.transaction_type)
        .filter(
            Trade.ticker == trade.ticker,
            Trade.member_match_key != trade.member_match_key,
            Trade.transaction_date >= trade.transaction_date - window,
            Trade.transaction_date <= trade.transaction_date + window,
        )
        .distinct()
        .all()
    )
    if not rows:
        return None
    # Keyed by match_key: sources spell the same person differently
    # ("David Taylor" / "David J. Taylor").
    names = {key: name for key, name, _ in rows}
    buyers = sorted({names[key] for key, _, kind in rows if kind == "purchase"})
    sellers = sorted({names[key] for key, _, kind in rows if kind == "sale"})
    parts = []
    if buyers:
        parts.append(f"compraron {', '.join(_e(n) for n in buyers[:4])}" + (" y otros" if len(buyers) > 4 else ""))
    if sellers:
        parts.append(f"vendieron {', '.join(_e(n) for n in sellers[:4])}" + (" y otros" if len(sellers) > 4 else ""))
    if not parts:
        return None
    return f"👥 Otros congresistas en ${_e(trade.ticker)} (±{CLUSTER_WINDOW_DAYS} días): " + "; ".join(parts)


def _earnings_line(db, trade: Trade) -> str | None:
    """Trades shortly before an earnings release are the ones worth a second
    look; also useful to know when the next catalyst is."""
    if not trade.ticker:
        return None
    lines = []
    if trade.transaction_date:
        before = (
            db.query(func.min(EarningsCache.date))
            .filter(
                EarningsCache.ticker == trade.ticker,
                EarningsCache.date > trade.transaction_date,
                EarningsCache.date <= trade.transaction_date + timedelta(days=EARNINGS_WINDOW_DAYS),
            )
            .scalar()
        )
        if before:
            days = (before - trade.transaction_date).days
            lines.append(f"⏰ <b>Operó {days} días antes de presentar resultados</b> ({before})")
    upcoming = (
        db.query(func.min(EarningsCache.date))
        .filter(EarningsCache.ticker == trade.ticker, EarningsCache.date >= date.today())
        .scalar()
    )
    if upcoming:
        lines.append(f"📊 Próximos resultados de ${_e(trade.ticker)}: {upcoming}")
    return "\n".join(lines) or None


def _track_record_line(db, trade: Trade) -> str | None:
    """The member's overall estimated-return track record, from the daily
    ranking calc (backend/ranking/calculate_rankings.py) — not specific to
    this ticker, but the closest "is this person actually good at this"
    signal we have cached and cheap to look up."""
    ranking = db.query(MemberRanking).filter_by(match_key=trade.member_match_key).one_or_none()
    if not ranking or ranking.total_return_pct is None:
        return None
    trend = "📈" if ranking.total_return_pct >= 0 else "📉"
    line = (
        f"{trend} Historial de {_e(trade.member_name)} ({ranking.trade_count} trades, ~2 años): "
        f"retorno estimado {ranking.total_return_pct:+.0f}%"
    )
    if ranking.win_rate_pct is not None:
        line += f", acierta el {ranking.win_rate_pct:.0f}%"
    if ranking.alpha_vs_sp500_pct is not None:
        line += f", {ranking.alpha_vs_sp500_pct:+.0f}% vs S&amp;P 500"
    return line


def _price_move_line(db, trade: Trade) -> str | None:
    """How the stock has moved since this specific trade — cheap: one price
    series fetch (cached), only computed for trades that actually get sent."""
    if not trade.ticker or not trade.transaction_date or trade.asset_type not in (None, "Stock"):
        return None
    try:
        series = prices.get_price_series(db, trade.ticker, trade.transaction_date - timedelta(days=5), date.today())
    except Exception:
        return None
    if not series:
        return None
    entry = prices.price_on_or_after(series, trade.transaction_date)
    current = prices.price_on_or_before(series, date.today())
    if not entry or not current or entry <= 0:
        return None
    change_pct = (current / entry - 1) * 100
    direction = "subido" if change_pct >= 0 else "bajado"
    price_summary = (
        f"${_e(trade.ticker)} ha {direction} {abs(change_pct):.1f}% desde la operación "
        f"(${entry:.2f} → ${current:.2f})"
    )

    if abs(change_pct) < 2:
        return f"➖ {price_summary}"
    if trade.transaction_type == "sale":
        # A price rise after selling means they left money on the table; a
        # drop means they got out at a good time — opposite read from a buy.
        good_call = change_pct <= 0
        verdict = "🟢 buena salida" if good_call else "🔴 se perdió la subida"
        return f"{price_summary} — {verdict}"

    arrow = "🟢" if change_pct >= 0 else "🔴"
    return f"{arrow} {price_summary}"


def _reason_line(reasons: set[str], trade: Trade) -> str:
    """Tell the user which of their watches fired, so an alert about someone
    they don't recognise isn't mistaken for a bug."""
    parts = []
    if "member" in reasons:
        parts.append(f"sigues a {_e(trade.member_name)}")
    if "ticker" in reasons:
        parts.append(f"sigues ${_e(trade.ticker)}")
    return f"<i>🔔 Te llega porque {' y '.join(parts)} (/list para ver tu lista)</i>"


def _format_alert(db, trade: Trade) -> str:
    """Body shared by every recipient; the per-chat reason line is appended in
    send_alerts()."""
    member = db.query(Member).filter_by(match_key=trade.member_match_key).one_or_none()

    flags = [line for line in (_high_value_line(trade), _conflict_line(trade, member)) if line]

    asset = f"${_e(trade.ticker)}" + (f" — {_e(trade.asset_name)}" if trade.asset_name else "")
    if trade.asset_type and trade.asset_type != "Stock":
        asset += f" [{_e(trade.asset_type)}]"

    core = [
        f"<b>{_TYPE_EMOJI.get(trade.transaction_type, _e(trade.transaction_type or 'OPERACIÓN'))}</b> {asset}",
        _member_line(trade, member),
        f"💵 Importe: {_format_amount(trade.amount_range_low, trade.amount_range_high)}",
    ]
    core.append(_owner_line(trade))
    core.extend(_dates_lines(trade))

    context = [
        line
        for line in (
            _price_move_line(db, trade),
            _earnings_line(db, trade),
            _member_ticker_history_line(db, trade),
            _cluster_line(db, trade),
            _same_filing_line(db, trade),
            _track_record_line(db, trade),
        )
        if line
    ]

    links = [
        f'<a href="{SITE_URL}/members/{_e(trade.member_match_key)}">Perfil</a>',
        f'<a href="{SITE_URL}/tickers/{_e(trade.ticker)}">${_e(trade.ticker)}</a>',
    ]
    if trade.filing_url:
        links.append(f'<a href="{_e(trade.filing_url)}">Filing original</a>')

    sections = ["\n".join(flags)] if flags else []
    sections.append("\n".join(core))
    if context:
        sections.append("\n".join(context))
    sections.append(" · ".join(links))
    return "\n\n".join(sections)


def send_alerts() -> dict:
    stats = {"trades_checked": 0, "alerts_sent": 0}
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("notify: TELEGRAM_BOT_TOKEN not set, skipping")
        return stats

    init_db()
    db = SessionLocal()
    try:
        pending = db.query(Trade).filter_by(notified=False).all()
        stats["trades_checked"] = len(pending)

        for trade in pending:
            reasons_by_chat: dict[int, set[str]] = {}
            for w in db.query(TelegramWatch).filter_by(watch_type="member", value=trade.member_match_key).all():
                reasons_by_chat.setdefault(w.chat_id, set()).add("member")
            for w in db.query(TelegramWatch).filter_by(watch_type="ticker", value=trade.ticker).all():
                reasons_by_chat.setdefault(w.chat_id, set()).add("ticker")

            if reasons_by_chat:  # only pay for the price/ranking lookups if someone's watching
                body = _format_alert(db, trade)
                for chat_id, reasons in reasons_by_chat.items():
                    if send_message(chat_id, f"{body}\n\n{_reason_line(reasons, trade)}"):
                        stats["alerts_sent"] += 1

            trade.notified = True

        db.commit()
    finally:
        db.close()

    logger.info("notify: checked=%d alerts_sent=%d", stats["trades_checked"], stats["alerts_sent"])
    return stats
