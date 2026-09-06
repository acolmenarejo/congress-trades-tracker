import hashlib
import re
from datetime import date, datetime
from typing import Optional, Tuple

_TITLE_WORDS = {"mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv", "hon", "the", "honorable"}
_TAG_RE = re.compile(r"<[^>]+>")
_NON_ALPHA_RE = re.compile(r"[^a-z]")
_WS_RE = re.compile(r"\s+")

_PARTY_MAP = {
    "d": "D", "dem": "D", "democrat": "D", "democratic": "D",
    "r": "R", "rep": "R", "republican": "R",
    "i": "I", "ind": "I", "independent": "I",
}


def strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", text).strip()


def clean_name(raw: Optional[str]) -> str:
    """Remove honorifics/suffixes and collapse whitespace, keep display casing."""
    if not raw:
        return ""
    text = strip_html(raw).replace(",", " ")
    text = text.replace("\x00", "")
    tokens = [t for t in text.split() if t.strip(".").lower() not in _TITLE_WORDS]
    return _WS_RE.sub(" ", " ".join(tokens)).strip()


def member_match_key(raw_name: Optional[str]) -> str:
    """Collapse name variants (e.g. 'Nancy Pelosi' vs 'Nancy P. Pelosi') into one key:
    first-initial + last-name, lowercase, alpha only."""
    name = clean_name(raw_name)
    if not name:
        return "unknown"
    parts = name.split(" ")
    first = parts[0]
    last = parts[-1]
    key = f"{first[:1]}{last}".lower()
    key = _NON_ALPHA_RE.sub("", key)
    return key or "unknown"


def normalize_party(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _PARTY_MAP.get(raw.strip().lower())


def normalize_transaction_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    low = raw.strip().lower()
    if "purchase" in low or low.startswith("buy"):
        return "purchase"
    if "sale" in low or low.startswith("sell"):
        return "sale"
    if "exchange" in low:
        return "exchange"
    return low or None


_AMOUNT_NUM_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def parse_amount_range(raw: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Parse strings like '$1,001 - $15,000', 'Over $50,000,000', '$1,000,000 +',
    'Unknown' into (low, high)."""
    if not raw:
        return None, None
    text = raw.strip()
    if text.lower() in {"unknown", "n/a", "--", ""}:
        return None, None
    numbers = [float(n.replace(",", "")) for n in _AMOUNT_NUM_RE.findall(text)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        if "over" in text.lower() or "+" in text:
            return numbers[0], None
        return numbers[0], numbers[0]
    return numbers[0], numbers[1]


def parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def make_unique_id(
    match_key: str,
    chamber: Optional[str],
    ticker: Optional[str],
    transaction_type: Optional[str],
    transaction_date: Optional[date],
    amount_low: Optional[float],
    amount_high: Optional[float],
) -> str:
    parts = [
        match_key or "",
        chamber or "",
        (ticker or "").upper(),
        transaction_type or "",
        transaction_date.isoformat() if transaction_date else "",
        str(amount_low) if amount_low is not None else "",
        str(amount_high) if amount_high is not None else "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
