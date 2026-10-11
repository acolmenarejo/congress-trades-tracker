"""Telegram when a Kalshi market we follow moves 15+ points in a day.

Covers the macro ladders in app/kalshi_expect.py and the company KPI markets
in app/kalshi_company.py (not the earnings-call word bets: a word going from
40% to 60% moves no portfolio). Kalshi's previous_price_dollars is the price
24 h earlier, so no history is needed.

Noise filters, all round numbers: skip markets closing within 3 days (weekly
gas or CPI ladders swing as the number becomes known, that is not news),
wide books (spread > 10 points), thin ones (< 500 contracts open) and the
weekly fuel series altogether. Both the mid and the last trade must have
moved, so one stray print is not enough.

One message per event (all strikes of "Domino's same-store sales in Q3" are
one question), at most once every 3 days per event (TelegramState[SENT_KEY];
it used to be per strike, so a neighbouring strike re-sent the same story),
and at most MAX_PER_RUN messages per run. Each message says whether a
headline explains the move, how much it matters (alto/medio/bajo) and what
it means for the watchlist (app/alert_context.py).
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import alert_context as ctx, alert_track
from .kalshi_company import _market
from .models import TelegramState, TelegramSubscriber

logger = logging.getLogger(__name__)

SENT_KEY = "kalshi_moves_sent"
MIN_MOVE = 0.15
MIN_OI = 500
MAX_SPREAD = 0.10
MAX_PER_RUN = 4
COOLDOWN = timedelta(days=3)
SKIP_SERIES = {"KXAAAGASW", "KXDIESELW"}

e = ctx.e

# Macro series: news query, whether it is one of the big drivers, and what a
# higher reading means (sectors helped / hurt and a one-line take).
MACRO = [
    (("KXWTI", "KXBRENT"), "oil prices", True,
     {"up": ["Energía"], "down": ["Consumo cíclico", "Industria"],
      "text": "petróleo más caro: sube la inflación, gana energía, pierden aerolíneas, transporte y consumo",
      "text_down": "petróleo más barato: baja la inflación, alivia a aerolíneas, transporte y consumo; pierde energía"}),
    (("KXFED",), "Federal Reserve interest rates", True,
     {"up": ["Servicios financieros"], "down": ["Tecnología", "Inmobiliario", "Consumo cíclico", "Comunicaciones"],
      "text": "tipos más altos: castiga tecnológicas caras, inmobiliario y bonos largos; bancos aguantan mejor",
      "text_down": "tipos más bajos: ayuda a tecnológicas, inmobiliario y bonos largos"}),
    (("KXCPI", "KXPCE", "KXOER", "KXSHELTER"), "US inflation CPI", True,
     {"up": ["Energía"], "down": ["Tecnología", "Inmobiliario", "Comunicaciones"],
      "text": "más inflación: aleja las bajadas de tipos; malo para crecimiento y bonos largos",
      "text_down": "menos inflación: acerca las bajadas de tipos; bueno para crecimiento y bonos largos"}),
    (("KXPAYROLLS", "KXU3", "KXGDP"), "US jobs report economy", False,
     {"up": ["Consumo cíclico", "Industria", "Servicios financieros"], "down": [],
      "text": "economía más fuerte: bueno para cíclicas, aunque mantiene los tipos altos",
      "text_down": "economía más floja: malo para cíclicas, aunque acerca bajadas de tipos"}),
    (("KXRECSSN",), "US recession", True,
     {"up": ["Consumo básico", "Salud"], "down": ["Consumo cíclico", "Industria", "Servicios financieros"],
      "text": "más riesgo de recesión: refugio en consumo básico y salud; cíclicas y bancos sufren",
      "text_down": "menos riesgo de recesión: buen tono para cíclicas y bancos"}),
    (("KXINX",), "S&P 500 stock market", True,
     {"up": [], "down": [], "text": "el mercado ve la bolsa más arriba a fin de año", "text_down": "el mercado ve la bolsa más abajo a fin de año: más cautela"}),
    (("KXNATGAS",), "natural gas prices", False,
     {"up": ["Energía", "Utilities (eléctricas, agua, gas)"], "down": ["Industria", "Materiales básicos"],
      "text": "gas más caro: encarece electricidad e industria; favorece a productores",
      "text_down": "gas más barato: alivia a industria y electricidad"}),
    (("KXPJM",), "PJM grid emergency", False,
     {"up": ["Utilities (eléctricas, agua, gas)"], "down": ["Tecnología"],
      "text": "más tensión en la red: suben precios de capacidad, bueno para generadoras (VST, CEG), encarece la IA",
      "text_down": "menos tensión en la red: menos ingresos extra para generadoras como VST o CEG"}),
    (("KXDDR5",), "DRAM memory prices", False,
     {"up": ["Tecnología"], "down": [], "text": "memoria más cara: favorece a Micron/SK Hynix, encarece servidores",
      "text_down": "memoria más barata: se enfría la demanda de chips de memoria"}),
]
_DOWN_WORDS = re.compile(r"\b(below|under|less than|or lower|or less|fewer)\b", re.I)
_MACRO_NEWS = re.compile(
    r"opec|crude|brent|wti|oil (price|futures|supply)|fed\b|powell|fomc|rate (hike|cut)|inflation|cpi|"
    r"jobs report|payrolls|unemployment|recession|gdp|tariff|natural gas|treasur|yields?\b|stocks? (fall|rise|rally|slide)",
    re.I,
)
_NEUTRAL_KPI = re.compile(r"headcount|employees|staff", re.I)


def _closes_soon(close: str | None, now: datetime) -> bool:
    try:
        return datetime.fromisoformat((close or "").replace("Z", "+00:00")) < now + timedelta(days=3)
    except ValueError:
        return True


def _days_to(close: str | None, now: datetime) -> float | None:
    try:
        return (datetime.fromisoformat((close or "").replace("Z", "+00:00")) - now).total_seconds() / 86400
    except ValueError:
        return None


def _event_of(market_ticker: str) -> str:
    return market_ticker.rsplit("-", 1)[0]


def moves(events: list[dict], company: dict[str, list[dict]]) -> list[dict]:
    """[{title, label, prev, p, ticker, event, series, url, stock, oi, close, ev_oi}]
    for every market that moved."""
    now = datetime.now(timezone.utc)
    rows, seen = [], set()

    def check(m: dict, title: str, url: str, stock: str | None, series: str, ev_oi: float):
        if m["ticker"] in seen or m["p"] is None or m["prev"] is None or m["last"] is None:
            return
        seen.add(m["ticker"])
        if m["oi"] < MIN_OI or (m["spread"] is not None and m["spread"] > MAX_SPREAD) or _closes_soon(m["close"], now):
            return
        if m["prev"] <= 0:  # no trade yesterday: Kalshi reports 0
            return
        if abs(m["p"] - m["prev"]) >= MIN_MOVE and abs(m["last"] - m["prev"]) >= MIN_MOVE:
            rows.append({"title": title, "label": m["label"], "prev": m["prev"], "p": m["p"],
                         "ticker": m["ticker"], "event": _event_of(m["ticker"]), "series": series,
                         "url": url, "stock": stock, "oi": m["oi"], "close": m["close"], "ev_oi": ev_oi})

    for ev in events:
        series = ev.get("series_ticker") or ""
        if series in SKIP_SERIES:
            continue
        url = f"https://kalshi.com/markets/{series.lower()}"
        mk = [_market(raw) for raw in ev.get("markets") or []]
        ev_oi = sum(x["oi"] for x in mk)
        for m in mk:
            check(m, ev.get("title") or "", url, None, series, ev_oi)
    for stock, evs in company.items():
        for ev in evs:
            if ev["kind"] != "kpi":
                continue
            for m in ev["markets"]:
                check(m, ev["title"] or "", ev["url"], stock, ev.get("series") or "", ev.get("oi") or 0)
    return rows


def _macro_info(series: str):
    for prefixes, query, core, info in MACRO:
        if series.startswith(prefixes):
            return query, core, info
    return None, False, None


def _yes_means_higher(label: str) -> bool:
    return not _DOWN_WORDS.search(label or "")


def _company_block(db: Session, r: dict, watched: bool, has_news: bool | None, level: str) -> list[str]:
    t = r["stock"]
    up = (r["p"] > r["prev"]) == _yes_means_higher(r["label"])
    lines = []
    if _NEUTRAL_KPI.search(r["title"]):
        lines.append(f"💬 El mercado ve la plantilla {'más alta' if up else 'más baja'} de lo que creía ayer: "
                     f"{'más contratación (crecimiento, pero más gasto)' if up else 'recortes (ahorro de costes o frenazo)'}.")
        good = None
    else:
        lines.append(f"💬 El mercado {'mejora' if up else 'rebaja'} lo que espera de este dato de {e(t)}.")
        good = up
    earn = ctx.next_earnings(db, t)
    when = f"en resultados del {earn:%d/%m} (dentro de {(earn - datetime.utcnow().date()).days} días)" if earn else "cuando publique resultados"
    if earn:
        lines.append(f"📅 Resultados: {earn:%d/%m}.")
    act = []
    if level == "bajo":
        act.append("Impacto bajo: solo vigilar, no hace falta mover nada.")
    elif good is False:
        act.append(f"Si tienes {e(t)}: valora reducir o subir el stop antes de que salga el dato ({when}).")
        act.append("Si no la tienes: no entres antes del dato.")
    elif good is True:
        act.append(f"Si la sigues: el mercado espera un buen dato {when}. Entrar antes, solo con stop.")
        act.append("Si ya la tienes: mantén.")
    else:
        act.append("No cambia por sí solo la tesis: míralo junto al resto del informe.")
    if level != "bajo":
        if has_news:
            act.append("Como ya es noticia, la acción probablemente ya lo ha descontado: no persigas el movimiento.")
        elif has_news is False:
            act.append("Sin noticia pública, la acción quizá aún no lo refleja. Es una pista débil: en Kalshi hay poco dinero.")
    if not watched:
        act.append("No está en tu watchlist.")
    return lines + ["🎯 <b>Qué hacer:</b>"] + [f"  • {a}" for a in act]


def _macro_block(db: Session, r: dict, info: dict | None, wl: set[str], has_news: bool | None, level: str) -> list[str]:
    if not info:
        return ["💬 Movimiento fuerte en un mercado macro."]
    higher = (r["p"] > r["prev"]) == _yes_means_higher(r["label"])
    lines = [f"💬 El mercado ve ahora el dato <b>{'más alto' if higher else 'más bajo'}</b>: "
             f"{info['text'] if higher else info['text_down']}."]
    win, lose = (info["up"], info["down"]) if higher else (info["down"], info["up"])
    by_sector: dict[str, str] = {t: ctx.sector(db, t) or "" for t in wl}
    good = sorted(t for t, s in by_sector.items() if s in win)
    bad = sorted(t for t, s in by_sector.items() if s in lose)
    if good or bad:
        lines.append("⭐ <b>Tu watchlist:</b>")
        if good:
            lines.append(f"  🟢 favorece a {', '.join(good)}")
        if bad:
            lines.append(f"  🔴 perjudica a {', '.join(bad)}")
    else:
        lines.append("⭐ No toca directamente a tu watchlist.")
    act = []
    if level == "bajo":
        act.append("Impacto bajo: solo vigilar.")
    else:
        if bad:
            act.append(f"Revisa los stops de {', '.join(bad)}; no amplíes posición hasta que salga el dato.")
        if good:
            act.append(f"{', '.join(good)} sale{'n' if len(good) > 1 else ''} ganando: si buscabas entrar, es su viento a favor.")
        if not act:
            act.append("Nada que hacer en tu watchlist; tenlo en cuenta para el tono general del mercado.")
        if has_news:
            act.append("Ya es noticia: los bonos y la bolsa suelen haberlo descontado en parte.")
        elif has_news is False:
            act.append("Sin noticia: puede adelantarse a un dato o a un anuncio. Pista débil.")
    return lines + ["🎯 <b>Qué hacer:</b>"] + [f"  • {a}" for a in act]


def message(db: Session, r: dict, others: int, wl: set[str]) -> str:
    now = datetime.now(timezone.utc)
    stock = r["stock"]
    watched = bool(stock and stock in wl)
    query, core, info = (None, False, None) if stock else _macro_info(r["series"])
    if stock:
        name = ctx.company_name(db, stock) or ctx.name_from_title(r["title"]) or stock
        items = ctx.about(ctx.news(f'"{name}"'), name, stock, r["title"])
    else:
        items = ctx.news(query) if query else None
        if items:  # "readers find the silver lining in high fuel prices" is not a cause
            items = [x for x in items if _MACRO_NEWS.search(x["title"])]
    nl, has_news = ctx.news_lines(items)
    points = abs(r["p"] - r["prev"]) * 100
    level = ctx.impact(points, r["ev_oi"], watched, _days_to(r["close"], now), core)
    arrow = "⬆️" if r["p"] > r["prev"] else "⬇️"
    head = f"<b>${e(stock)}</b> · " if stock else "🌍 "
    star = " ⭐" if watched else ""
    lines = [
        f"📊 <b>Kalshi</b> · {head}{e(r['title'])}{star}",
        f"{ctx.IMPACT_ICON[level]} Impacto <b>{level.upper()}</b>",
        "",
        f"{arrow} «{e(r['label'])}»: {r['prev'] * 100:.0f}% → <b>{r['p'] * 100:.0f}%</b> ({(r['p'] - r['prev']) * 100:+.0f} puntos en 24 h)",
    ]
    if others:
        lines.append(f"   (y {others} {'escalones' if others > 1 else 'escalón'} más del mismo dato)")
    lines.append(f"💰 {r['ev_oi']:,.0f} contratos abiertos".replace(",", "."))
    lines.append("")
    lines += nl
    lines += _company_block(db, r, watched, has_news, level) if stock else _macro_block(db, r, info, wl, has_news, level)
    links = [f'<a href="{e(r["url"])}">Kalshi</a>']
    links.insert(0, ctx.ticker_link(stock) if stock else f'<a href="{ctx.WEB}/macro">página Macro</a>')
    lines += ["", "🔗 " + " · ".join(links), "<i>Pista, no recomendación: en Kalshi hay poco dinero detrás.</i>"]
    return "\n".join(lines)


def notify(db: Session, events: list[dict], company: dict[str, list[dict]]) -> int:
    from .config import TELEGRAM_BOT_TOKEN
    from .telegram_api import send_message

    st = db.get(TelegramState, SENT_KEY)
    try:
        sent = json.loads(st.value) if st and st.value else {}
    except ValueError:
        sent = {}
    now = datetime.now(timezone.utc)
    sent = {k: v for k, v in sent.items() if datetime.fromisoformat(v) > now - COOLDOWN}
    blocked = set(sent) | {_event_of(k) for k in sent}  # old entries were per strike
    by_event: dict[str, list[dict]] = {}
    for r in moves(events, company):
        if r["event"] not in blocked and r["ticker"] not in blocked:
            by_event.setdefault(r["event"], []).append(r)
    wl = ctx.watchlist(db)
    # Watchlist first, then the biggest moves.
    ranked = sorted(by_event.values(), key=lambda rs: (rs[0]["stock"] not in wl, -max(abs(x["p"] - x["prev"]) for x in rs)))
    picked = ranked[:MAX_PER_RUN]
    for rs in picked:
        sent[rs[0]["event"]] = now.isoformat()
    db.merge(TelegramState(key=SENT_KEY, value=json.dumps(sent)))
    db.commit()
    if not picked:
        return 0
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []
    n = 0
    for rs in picked:
        best = max(rs, key=lambda x: abs(x["p"] - x["prev"]))
        text = message(db, best, len(rs) - 1, wl)
        n += sum(send_message(c, text) for c in chats)
        # The move points to YES if the price rose; settles when the market resolves.
        alert_track.record(db, f"kalshi:{best['ticker']}", "kalshi", best["p"], best["title"], ticker=best["ticker"],
                           direction="yes" if best["p"] > best["prev"] else "no", alerted=True)
    db.commit()
    logger.info("kalshi_watch: %d events", len(picked))
    return n
