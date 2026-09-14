"""Tiny standalone copy of ingestion/normalize.py's member_match_key, kept
duplicated on purpose: this module lives inside app/ so it bundles reliably
with the Vercel deployment (a cross-package import from ingestion/ here hit
the same "module not found in prod" issue ranking/ did — see app/prices.py's
history). Keep both copies in sync if the matching rule ever changes.
"""
import re

_TITLE_WORDS = {"mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv", "hon", "the", "honorable"}
_TAG_RE = re.compile(r"<[^>]+>")
_NON_ALPHA_RE = re.compile(r"[^a-z]")
_WS_RE = re.compile(r"\s+")


def clean_name(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub("", raw).replace(",", " ").replace("\x00", "")
    tokens = [t for t in text.split() if t.strip(".").lower() not in _TITLE_WORDS]
    return _WS_RE.sub(" ", " ".join(tokens)).strip()


def member_match_key(raw_name: str | None) -> str:
    name = clean_name(raw_name)
    if not name:
        return "unknown"
    parts = name.split(" ")
    key = f"{parts[0][:1]}{parts[-1]}".lower()
    key = _NON_ALPHA_RE.sub("", key)
    return key or "unknown"
