"""Red-flag filings on watchlist stocks, from EDGAR's submissions JSON.

Only filings that mean "the numbers or the company itself may be in trouble":
  - NT 10-K / NT 10-Q: late annual/quarterly report notice
  - 8-K item 4.02: past financial statements should no longer be relied on
  - 8-K item 4.01: change of auditor
  - 8-K item 3.01: notice of delisting / failure to meet a listing rule
  - 8-K item 1.03: bankruptcy
Late filers and restatements have been shown to keep drifting down after the
news (e.g. Alford, Jones & Zmijewski, 1994, from memory); the alert is an
"avoid / review your stop" prompt, never a short signal. One message per
filing, only for tickers someone watches. Hit rate is tracked as source
"edgar_flag" in alert_outcomes (30/90-day return against SPY)."""
import html
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import alert_context as ctx, alert_track
from .insiders import _get
from .models import TelegramState, TelegramSubscriber

logger = logging.getLogger(__name__)

STATE_KEY = "insiders_flags_sent"  # 'insiders%' so insiders.yml keeps it on a DB merge
LOOKBACK_DAYS = 4
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# 8-K item -> (what it is, what to do)
ITEMS = {
    "4.02": ("la empresa avisa de que sus cuentas pasadas no son fiables (reformulación)", "alto"),
    "4.01": ("cambio de auditor", "medio"),
    "3.01": ("aviso de posible exclusión de bolsa", "alto"),
    "1.03": ("quiebra o concurso de acreedores", "alto"),
}


def ticker_ciks() -> dict[str, int]:
    resp = _get(TICKERS_URL)
    if resp is None:
        return {}
    return {v["ticker"].upper(): int(v["cik_str"]) for v in resp.json().values()}


def flags_for(ticker: str, cik: int, since: date) -> list[dict]:
    resp = _get(SUBMISSIONS.format(cik=cik))
    if resp is None:
        return []
    rec = (resp.json().get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(rec.get("form") or []):
        try:
            filed = date.fromisoformat(rec["filingDate"][i])
        except (KeyError, IndexError, ValueError):
            continue
        if filed < since:
            continue
        items = [x.strip() for x in (rec.get("items") or [""] * (i + 1))[i].split(",") if x.strip()]
        what = level = None
        if form in ("NT 10-K", "NT 10-Q"):
            what, level = "avisa de que no llegará a tiempo con su informe " + ("anual" if form == "NT 10-K" else "trimestral"), "medio"
        else:
            for it in items:
                if form.startswith("8-K") and it in ITEMS:
                    what, level = ITEMS[it]
                    break
        if what:
            acc = rec["accessionNumber"][i]
            doc = rec.get("primaryDocument", [""] * (i + 1))[i]
            out.append({"ticker": ticker, "acc": acc, "form": form, "filed": filed, "what": what, "level": level,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
    return out


def message(db: Session, f: dict) -> str:
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    t = f["ticker"]
    name = ctx.company_name(db, t) or t
    return "\n".join([
        f"🚨 <b>ALARMA EN LA WATCHLIST</b> · <b>{e(t)}</b> ({e(name)}) · impacto {ctx.IMPACT_ICON[f['level']]} {f['level']}",
        "",
        f"📄 <b>{e(f['form'])}</b> del {f['filed']:%d/%m}: {e(f['what'])}.",
        "",
        "🎯 <b>Qué hacer:</b>",
        f"• Si tienes {e(t)}: revisa el documento y valora reducir o subir el stop. No lo promedies a la baja hasta saber más.",
        f"• Si no la tienes: no entres hasta que aclaren.",
        "",
        f'🔗 <a href="{e(f["url"])}">Documento en la SEC</a> · {ctx.ticker_link(t)}',
        "<i>Las empresas que llegan tarde o corrigen cuentas suelen seguir flojas semanas después, pero no es seguro · no es asesoramiento</i>",
    ])


def scan(db: Session, send: bool = True) -> int:
    from .config import TELEGRAM_BOT_TOKEN
    from .telegram_api import send_message

    wl = ctx.watchlist(db)
    if not wl:
        return 0
    ciks = ticker_ciks()
    st = db.get(TelegramState, STATE_KEY)
    try:
        sent = set(json.loads(st.value)) if st and st.value else set()
    except ValueError:
        sent = set()
    since = date.today() - timedelta(days=LOOKBACK_DAYS)
    new = []
    for t in sorted(wl):
        if t in ciks:
            new += [f for f in flags_for(t, ciks[t], since) if f["acc"] not in sent]
    if not new:
        return 0
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN and send else []
    n = 0
    for f in new:
        n += sum(send_message(c, message(db, f)) for c in chats)
        sent.add(f["acc"])
        price = _last_close(db, f["ticker"])
        alert_track.record(db, f"edgar:{f['acc']}", "edgar_flag", price, f"{f['form']} {f['ticker']}", ticker=f["ticker"],
                           direction=f["form"] if f["form"].startswith("NT") else "8-K", alerted=bool(chats))
    db.merge(TelegramState(key=STATE_KEY, value=json.dumps(sorted(sent)[-500:])))
    db.commit()
    logger.info("edgar_flags: %d new filing(s)", len(new))
    return n


def _last_close(db: Session, ticker: str) -> float | None:
    from .prices import get_price_series

    ser = get_price_series(db, ticker, date.today() - timedelta(days=10), date.today())
    return ser[-1]["close"] if ser else None
