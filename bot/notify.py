"""Send Telegram alerts for newly-ingested trades that match a subscriber's
watchlist (member or ticker). Meant to run right after backend/ingestion/
fetch_trades.py, as a separate step — decoupled via the `Trade.notified` flag
so it can be re-run safely and doesn't care how the trade got inserted.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from config import TELEGRAM_BOT_TOKEN  # noqa: E402
from telegram_api import send_message  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Trade, TelegramWatch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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


def _format_alert(trade: Trade) -> str:
    lag = f"{trade.disclosure_lag_days} días" if trade.disclosure_lag_days is not None else "desconocido"
    lines = [
        f"<b>{_TYPE_EMOJI.get(trade.transaction_type, trade.transaction_type or 'Operación')}</b> — "
        f"<b>{trade.member_name}</b> ({_CHAMBER_LABEL.get(trade.chamber, trade.chamber or '?')})",
        f"Ticker: <b>${trade.ticker}</b>" + (f" — {trade.asset_name}" if trade.asset_name else ""),
        f"Importe: {_format_amount(trade.amount_range_low, trade.amount_range_high)}",
        f"Fecha operación: {trade.transaction_date}",
        f"Fecha disclosure: {trade.disclosure_date or 'desconocida'} (retraso: {lag})",
    ]
    if trade.filing_url:
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

            text = _format_alert(trade)
            for chat_id in chat_ids:
                if send_message(chat_id, text):
                    stats["alerts_sent"] += 1

            trade.notified = True

        db.commit()
    finally:
        db.close()

    logger.info("notify: checked=%d alerts_sent=%d", stats["trades_checked"], stats["alerts_sent"])
    return stats


if __name__ == "__main__":
    send_alerts()
