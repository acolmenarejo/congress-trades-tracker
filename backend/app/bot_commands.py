"""Same logic as bot/commands.py, ported into app/ so it bundles reliably on
Vercel (see app/prices.py's docstring for why). Callable directly as a
function (process_updates()) from the /internal/poll endpoint, or run
standalone via bot/commands.py for local dev / the GitHub Actions fallback.
"""
import logging

from .config import DEFAULT_WATCHED_MEMBERS, TELEGRAM_BOT_TOKEN
from .database import SessionLocal, init_db
from .models import Member, TelegramState, TelegramSubscriber, TelegramWatch
from .name_utils import member_match_key
from .telegram_api import get_updates, send_message

logger = logging.getLogger("bot.commands")

OFFSET_KEY = "telegram_update_offset"

HELP_TEXT = (
    "<b>Congress Trades Tracker</b>\n"
    "Te aviso cuando un miembro del Congreso que vigilas compra/vende acciones.\n\n"
    "Comandos:\n"
    "/watch NOMBRE — vigila a un miembro (ej. /watch Nancy Pelosi)\n"
    "/unwatch NOMBRE — deja de vigilarlo\n"
    "/watchticker TICKER — avisa cuando cualquier congresista opere ese ticker (ej. /watchticker NVDA)\n"
    "/unwatchticker TICKER — deja de vigilar ese ticker\n"
    "/list — muestra tu lista de vigilancia actual\n"
)

_DEFAULT_NAMES = {match_key: name for match_key, name in DEFAULT_WATCHED_MEMBERS}


def _get_offset(db) -> int | None:
    row = db.query(TelegramState).filter_by(key=OFFSET_KEY).one_or_none()
    return int(row.value) if row and row.value else None


def _set_offset(db, update_id: int) -> None:
    row = db.query(TelegramState).filter_by(key=OFFSET_KEY).one_or_none()
    if row is None:
        db.add(TelegramState(key=OFFSET_KEY, value=str(update_id)))
    else:
        row.value = str(update_id)


def _ensure_subscriber(db, chat_id: int, username: str | None) -> bool:
    """Returns True if this chat is new (just created)."""
    existing = db.query(TelegramSubscriber).filter_by(chat_id=chat_id).one_or_none()
    if existing:
        return False
    db.add(TelegramSubscriber(chat_id=chat_id, username=username))
    db.flush()
    return True


def _seed_default_watches(db, chat_id: int) -> None:
    for match_key, _name in DEFAULT_WATCHED_MEMBERS:
        exists = (
            db.query(TelegramWatch)
            .filter_by(chat_id=chat_id, watch_type="member", value=match_key)
            .one_or_none()
        )
        if not exists:
            db.add(TelegramWatch(chat_id=chat_id, watch_type="member", value=match_key))
    db.flush()


def _describe_member(db, match_key: str) -> str:
    member = db.query(Member).filter_by(match_key=match_key).one_or_none()
    if member:
        return member.name
    return _DEFAULT_NAMES.get(match_key, match_key)


def _handle_watch(db, chat_id: int, name: str) -> str:
    if not name:
        return "Uso: /watch Nombre Apellido"
    match_key = member_match_key(name)
    exists = db.query(TelegramWatch).filter_by(chat_id=chat_id, watch_type="member", value=match_key).one_or_none()
    if exists:
        return f"Ya estabas vigilando a {_describe_member(db, match_key)}."
    db.add(TelegramWatch(chat_id=chat_id, watch_type="member", value=match_key))
    db.flush()
    return f"✅ Ahora vigilo a {_describe_member(db, match_key)}."


def _handle_unwatch(db, chat_id: int, name: str) -> str:
    if not name:
        return "Uso: /unwatch Nombre Apellido"
    match_key = member_match_key(name)
    row = db.query(TelegramWatch).filter_by(chat_id=chat_id, watch_type="member", value=match_key).one_or_none()
    if not row:
        return f"No estabas vigilando a {name}."
    display = _describe_member(db, match_key)
    db.delete(row)
    return f"❌ Dejé de vigilar a {display}."


def _handle_watchticker(db, chat_id: int, ticker: str) -> str:
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return "Uso: /watchticker NVDA"
    exists = db.query(TelegramWatch).filter_by(chat_id=chat_id, watch_type="ticker", value=ticker).one_or_none()
    if exists:
        return f"Ya estabas vigilando ${ticker}."
    db.add(TelegramWatch(chat_id=chat_id, watch_type="ticker", value=ticker))
    return f"✅ Ahora vigilo ${ticker} (cualquier congresista que lo opere)."


def _handle_unwatchticker(db, chat_id: int, ticker: str) -> str:
    ticker = (ticker or "").strip().upper()
    row = db.query(TelegramWatch).filter_by(chat_id=chat_id, watch_type="ticker", value=ticker).one_or_none()
    if not row:
        return f"No estabas vigilando ${ticker}."
    db.delete(row)
    return f"❌ Dejé de vigilar ${ticker}."


def _handle_list(db, chat_id: int) -> str:
    watches = db.query(TelegramWatch).filter_by(chat_id=chat_id).all()
    members = [w for w in watches if w.watch_type == "member"]
    tickers = [w for w in watches if w.watch_type == "ticker"]
    lines = ["<b>Tu lista de vigilancia:</b>"]
    lines.append("\n<u>Miembros:</u>")
    lines += [f"• {_describe_member(db, w.value)}" for w in members] or ["  (ninguno)"]
    lines.append("\n<u>Tickers:</u>")
    lines += [f"• ${w.value}" for w in tickers] or ["  (ninguno)"]
    return "\n".join(lines)


def _dispatch(db, chat_id: int, text: str, is_new_subscriber: bool) -> str:
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower().split("@")[0]  # strip /cmd@BotName in groups
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/start", "/help"):
        if is_new_subscriber:
            _seed_default_watches(db, chat_id)
            return HELP_TEXT + "\nTe suscribí a la lista por defecto: " + ", ".join(
                n for _, n in DEFAULT_WATCHED_MEMBERS
            ) + ". Usa /list para verla."
        return HELP_TEXT
    if command == "/watch":
        return _handle_watch(db, chat_id, arg)
    if command == "/unwatch":
        return _handle_unwatch(db, chat_id, arg)
    if command == "/watchticker":
        return _handle_watchticker(db, chat_id, arg)
    if command == "/unwatchticker":
        return _handle_unwatchticker(db, chat_id, arg)
    if command == "/list":
        return _handle_list(db, chat_id)
    return "No entendí ese comando. Usa /help para ver la lista de comandos."


def process_updates() -> int:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("commands: TELEGRAM_BOT_TOKEN not set, skipping")
        return 0

    init_db()
    db = SessionLocal()
    processed = 0
    try:
        offset = _get_offset(db)
        updates = get_updates(offset=(offset + 1) if offset else None)
        for update in updates:
            update_id = update["update_id"]
            message = update.get("message") or update.get("edited_message")
            if message and "text" in message:
                chat_id = message["chat"]["id"]
                username = message["chat"].get("username")
                is_new = _ensure_subscriber(db, chat_id, username)
                reply = _dispatch(db, chat_id, message["text"], is_new)
                send_message(chat_id, reply)
            _set_offset(db, update_id)
            db.commit()
            processed += 1
    finally:
        db.close()

    logger.info("commands: processed %d update(s)", processed)
    return processed
