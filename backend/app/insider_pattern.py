"""Is this insider's purchase out of character? (Cohen, Malloy & Pomorski,
"Decoding Inside Information", 2012: insiders who trade in the same calendar
month every year carry no information; the ones who break their pattern do.)

Approximation: the insider's own Form 4 filing dates (any transaction, from
EDGAR's submissions JSON) stand in for their trade dates. "routine" = they
filed in this same calendar month in each of the 3 previous years;
"opportunistic" = not routine and at least 3 years of history; "unknown" =
less history than that. It only labels the alert, it never gates it; the live
accuracy of each label is measured in alert_outcomes (direction column)."""
import logging
from datetime import date

from .insiders import _get

logger = logging.getLogger(__name__)

SUBMISSIONS = "https://data.sec.gov/submissions"
YEARS = 3


def _form4_dates(block: dict) -> list[date]:
    out = []
    for form, d in zip(block.get("form") or [], block.get("filingDate") or []):
        if form in ("4", "4/A"):
            try:
                out.append(date.fromisoformat(d))
            except ValueError:
                pass
    return out


def filing_dates(cik: str, since: date) -> list[date] | None:
    """Form 4 filing dates of one person from `since` on; None if EDGAR could not be read."""
    resp = _get(f"{SUBMISSIONS}/CIK{int(cik):010d}.json")
    if resp is None:
        return None
    try:
        data = resp.json()
        filings = data.get("filings") or {}
        dates = _form4_dates(filings.get("recent") or {})
        for f in filings.get("files") or []:  # older filings live in extra files
            if (f.get("filingTo") or "9999") >= since.isoformat():
                older = _get(f"{SUBMISSIONS}/{f['name']}")
                if older is not None:
                    dates += _form4_dates(older.json())
    except Exception:
        logger.exception("insider_pattern: bad submissions for %s", cik)
        return None
    return dates


def classify(dates: list[date], tx: date) -> str:
    months = {(d.year, d.month) for d in dates}
    if all((tx.year - k, tx.month) in months for k in range(1, YEARS + 1)):
        return "routine"
    if not dates or min(dates) > date(tx.year - YEARS, tx.month, 1):
        return "unknown"
    return "opportunistic"


def pattern(cik: str | None, tx: date | None, cache: dict) -> str:
    if not cik or not tx:
        return "unknown"
    if cik not in cache:
        cache[cik] = filing_dates(cik, date(tx.year - YEARS - 1, 1, 1))
    dates = cache[cik]
    return classify(dates, tx) if dates is not None else "unknown"


LABEL = {
    "opportunistic": "🧭 <b>Compra atípica:</b> no suele comprar en este mes. Es el tipo de compra con más información según la literatura.",
    "routine": "🧭 <b>Compra de rutina:</b> declara operaciones en este mismo mes todos los años. Señal más débil.",
}
