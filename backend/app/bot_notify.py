"""Same logic as bot/notify.py, ported into app/ for the same reason as
bot_commands.py — see that file's docstring."""
import logging
from datetime import date, timedelta

from . import prices
from .config import TELEGRAM_BOT_TOKEN
from .database import SessionLocal, init_db
from .models import MemberRanking, Trade, TelegramWatch
from .telegram_api import send_message

logger = logging.getLogger("bot.notify")

_TYPE_EMOJI = {"purchase": "🟢 Compra", "sale": "🔴 Venta", "exchange": "🔁 Canje"}
_CHAMBER_LABEL = {"house": "Cámara de Representantes", "senate": "Senado"}


def _format_amount(low, high) -> str:
    if low is None and high is None:
        return "importe desconocido"
    if high is None:
        return f"más de ${low:,.0f}"
    if low == high:
        return f"${low:,.0f}"
    return f"${low:,.0f} - ${high:,.0f}"


def _track_record_line(db, trade: Trade) -> str | None:
    """The member's overall estimated-return track record, from the daily
    ranking calc (backend/ranking/calculate_rankings.py) — not specific to
    this ticker, but the closest "is this person actually good at this"
    signal we have cached and cheap to look up."""
    ranking = db.query(MemberRanking).filter_by(match_key=trade.member_match_key).one_or_none()
    if not ranking or ranking.total_return_pct is None:
        return None
    trend = "📈" if ranking.total_return_pct >= 0 else "📉"
    return (
        f"{trend} Historial de {trade.member_name} (últimos ~2 años, {ranking.trade_count} trades): "
        f"retorno estimado {ranking.total_return_pct:+.0f}%, acierta el {ranking.win_rate_pct:.0f}% de sus trades"
    )


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
    price_summary = f"${trade.ticker} ha {direction} {abs(change_pct):.1f}% desde entonces (${entry:.2f} → ${current:.2f})"

    if trade.transaction_type == "sale":
        # A price rise after selling means they left money on the table; a
        # drop means they got out at a good time — opposite read from a buy.
        good_call = change_pct <= 0
        verdict = "🟢 buena salida" if good_call else "🔴 se perdió la subida"
        return f"{price_summary} — {verdict}"

    arrow = "🟢" if change_pct >= 0 else "🔴"
    return f"{arrow} {price_summary}"


def _format_alert(db, trade: Trade) -> str:
    lag = f"{trade.disclosure_lag_days} días" if trade.disclosure_lag_days is not None else "desconocido"
    lines = [
        f"<b>{_TYPE_EMOJI.get(trade.transaction_type, trade.transaction_type or 'Operación')}</b> — "
        f"<b>{trade.member_name}</b> ({_CHAMBER_LABEL.get(trade.chamber, trade.chamber or '?')})",
        f"Ticker: <b>${trade.ticker}</b>" + (f" — {trade.asset_name}" if trade.asset_name else ""),
        f"Importe: {_format_amount(trade.amount_range_low, trade.amount_range_high)}",
        f"Fecha operación: {trade.transaction_date}",
        f"Fecha disclosure: {trade.disclosure_date or 'desconocida'} (retraso: {lag})",
    ]

    price_line = _price_move_line(db, trade)
    if price_line:
        lines.append("")
        lines.append(price_line)

    track_record = _track_record_line(db, trade)
    if track_record:
        lines.append(track_record)

    if trade.filing_url:
        lines.append("")
        lines.append(f'<a href="{trade.filing_url}">Ver filing original</a>')
    return "\n".join(lines)


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
            member_watchers = {
                w.chat_id
                for w in db.query(TelegramWatch)
                .filter_by(watch_type="member", value=trade.member_match_key)
                .all()
            }
            ticker_watchers = {
                w.chat_id
                for w in db.query(TelegramWatch).filter_by(watch_type="ticker", value=trade.ticker).all()
            }
            chat_ids = member_watchers | ticker_watchers

            if chat_ids:  # only pay for the price/ranking lookups if someone's watching
                text = _format_alert(db, trade)
                for chat_id in chat_ids:
                    if send_message(chat_id, text):
                        stats["alerts_sent"] += 1

            trade.notified = True

        db.commit()
    finally:
        db.close()

    logger.info("notify: checked=%d alerts_sent=%d", stats["trades_checked"], stats["alerts_sent"])
    return stats
