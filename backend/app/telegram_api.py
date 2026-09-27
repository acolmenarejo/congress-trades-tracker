"""Thin wrapper over the raw Telegram Bot API (no library dependency)."""
import logging

import requests

from .config import TELEGRAM_API_BASE

logger = logging.getLogger(__name__)


def get_updates(offset: int | None = None, timeout: int = 10) -> list[dict]:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        resp = requests.get(f"{TELEGRAM_API_BASE}/getUpdates", params=params, timeout=timeout + 10)
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception:
        logger.exception("telegram_api: getUpdates failed")
        return []


def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    try:
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("telegram_api: sendMessage to %s failed: %s", chat_id, resp.text)
            return False
        return True
    except Exception:
        logger.exception("telegram_api: sendMessage to %s raised", chat_id)
        return False


def send_photo(chat_id: int, png: bytes, caption: str, parse_mode: str = "HTML") -> bool:
    """Photo with an HTML caption (Telegram caps captions at 1024 chars)."""
    try:
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode},
            files={"photo": ("chart.png", png, "image/png")},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("telegram_api: sendPhoto to %s failed: %s", chat_id, resp.text)
            return False
        return True
    except Exception:
        logger.exception("telegram_api: sendPhoto to %s raised", chat_id)
        return False


def send_alert(chat_id: int, body: str, png: bytes | None = None) -> bool:
    """Photo + caption when it fits Telegram's 1024-char caption limit;
    otherwise the photo with just the headline, then the full text."""
    if png:
        if len(body) <= 1024:
            if send_photo(chat_id, png, body):
                return True
        else:
            send_photo(chat_id, png, body.split("\n", 1)[0])
    return send_message(chat_id, body)
