"""Macro panel: rates, bond volatility, credit and the Fed's liquidity
"plumbing", each with a plain-Spanish reading and what it usually implies
for stocks. Rule-based on purpose: the thresholds are the ones market
commentary commonly uses, not fitted to anything, and the page says so.

Data (no API keys):
  FRED  fredgraph.csv  DGS10, DGS2, T10Y2Y, EFFR, SOFR, IORB, WALCL, WTREGEN,
                       RRPONTSYD, WRESBAL, BAMLH0A0HYM2
  Yahoo chart API      ^MOVE (bond volatility), ^VIX
Fetched daily by macro.yml (backend/macro/fetch_macro.py) into MacroPoint;
the API only reads, so it works on Vercel's read-only DB.
"""
import csv
import io
import logging
from datetime import date, timedelta

import requests
from sqlalchemy.orm import Session

from .models import MacroPoint

logger = logging.getLogger(__name__)

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HISTORY_DAYS = 3 * 365

# series id → (source, divisor to the unit we show). Liquidity series are
# shown in billions: WALCL and WTREGEN come in millions, RRPONTSYD and
# WRESBAL already in billions.
SERIES = {
    "DGS10": ("fred", 1),
    "DGS2": ("fred", 1),
    "T10Y2Y": ("fred", 1),
    "EFFR": ("fred", 1),
    "SOFR": ("fred", 1),
    "IORB": ("fred", 1),
    "WALCL": ("fred", 1000),
    "WTREGEN": ("fred", 1000),
    "RRPONTSYD": ("fred", 1),
    "WRESBAL": ("fred", 1),
    "BAMLH0A0HYM2": ("fred", 1),
    "^MOVE": ("yahoo", 1),
    "^VIX": ("yahoo", 1),
}


# ---------------------------------------------------------------- fetching

def _fred(series_id: str, start: date) -> list[tuple[date, float]]:
    resp = requests.get(FRED_CSV, params={"id": series_id, "cosd": start.isoformat()}, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    out = []
    for row in csv.reader(io.StringIO(resp.text)):
        if len(row) < 2 or row[1] in ("", ".") or not row[0][:1].isdigit():
            continue
        try:
            out.append((date.fromisoformat(row[0]), float(row[1])))
        except ValueError:
            continue
    return out


def _yahoo(ticker: str, start: date) -> list[tuple[date, float]]:
    from .prices import _fetch_from_yahoo

    return [(r["date"], float(r["close"])) for r in _fetch_from_yahoo(ticker, start, date.today())]


def refresh(db: Session) -> dict:
    """Fetch every series (last HISTORY_DAYS) and upsert. Returns points per series."""
    start = date.today() - timedelta(days=HISTORY_DAYS)
    stats = {}
    for sid, (source, div) in SERIES.items():
        try:
            pts = _fred(sid, start) if source == "fred" else _yahoo(sid, start)
        except Exception:
            logger.exception("macro: %s failed", sid)
            stats[sid] = 0
            continue
        for d, v in pts:
            db.merge(MacroPoint(series=sid, date=d, value=v / div))
        stats[sid] = len(pts)
        db.commit()
    logger.info("macro: %s", stats)
    return stats


# ---------------------------------------------------------------- reading

class _S:
    """A series loaded from the DB with on-or-before lookups."""

    def __init__(self, pts: list[tuple[date, float]]):
        self.pts = pts

    @property
    def ok(self) -> bool:
        return bool(self.pts)

    @property
    def last(self) -> float | None:
        return self.pts[-1][1] if self.pts else None

    @property
    def last_date(self) -> date | None:
        return self.pts[-1][0] if self.pts else None

    def ago(self, days: int) -> float | None:
        if not self.pts:
            return None
        target = self.pts[-1][0] - timedelta(days=days)
        prev = None
        for d, v in self.pts:
            if d > target:
                break
            prev = v
        return prev

    def change(self, days: int) -> float | None:
        a = self.ago(days)
        return None if a is None or self.last is None else self.last - a

    def min_since(self, days: int) -> float | None:
        cut = self.pts[-1][0] - timedelta(days=days) if self.pts else None
        vals = [v for d, v in self.pts if d >= cut] if cut else []
        return min(vals) if vals else None

    def history(self, days: int = 365, step: int = 5) -> list[dict]:
        cut = self.pts[-1][0] - timedelta(days=days) if self.pts else None
        pts = [(d, v) for d, v in self.pts if d >= cut] if cut else []
        sampled = pts[::step] + ([pts[-1]] if pts and (len(pts) - 1) % step else [])
        return [{"date": d.isoformat(), "value": round(v, 3)} for d, v in sampled]


def _load(db: Session) -> dict[str, _S]:
    out: dict[str, list] = {sid: [] for sid in SERIES}
    since = date.today() - timedelta(days=HISTORY_DAYS + 30)
    for p in db.query(MacroPoint).filter(MacroPoint.date >= since).order_by(MacroPoint.date):
        out.setdefault(p.series, []).append((p.date, p.value))
    return {k: _S(v) for k, v in out.items()}


def _net_liquidity(s: dict[str, _S]) -> _S:
    """Fed balance sheet − TGA − reverse repo, in billions, on WALCL's weekly dates."""
    walcl, tga, rrp = s["WALCL"], s["WTREGEN"], s["RRPONTSYD"]
    pts = []
    for d, v in walcl.pts:
        t = _S([p for p in tga.pts if p[0] <= d]).last
        r = _S([p for p in rrp.pts if p[0] <= d]).last
        if t is not None and r is not None:
            pts.append((d, v - t - r))
    return _S(pts)


def _ind(key, name, series: _S, unit, status, reading, action, change=None, change_label=None, decimals=2):
    return {
        "key": key,
        "name": name,
        "value": None if series.last is None else round(series.last, decimals),
        "unit": unit,
        "as_of": series.last_date.isoformat() if series.last_date else None,
        "change": None if change is None else round(change, decimals),
        "change_label": change_label,
        "status": status,  # ok | watch | stress
        "reading": reading,
        "action": action,
        "history": series.history(),
    }


def snapshot(db: Session) -> dict:
    s = _load(db)
    inds = []

    y10 = s["DGS10"]
    if y10.ok:
        ch = y10.change(30) * 100
        if ch >= 25:
            st, rd = "watch", f"El bono a 10 años sube {ch:.0f} pb en un mes."
            ac = ("Tipos largos al alza: presionan tecnológicas de crecimiento, inmobiliario (XLRE), utilities y "
                  "pequeñas compañías. Favorecen bancos y value. Cuidado con comprar múltiplos altos.")
        elif ch <= -25:
            st, rd = "ok", f"El bono a 10 años baja {-ch:.0f} pb en un mes."
            ac = ("Tipos largos a la baja: alivio para crecimiento, inmobiliario y small caps (IWM); los bonos "
                  "largos (TLT) se revalorizan. Si bajan por miedo a recesión, mejor defensivas.")
        else:
            st, rd = "ok", f"El bono a 10 años está estable ({ch:+.0f} pb en un mes)."
            ac = "Sin presión clara de tipos sobre las valoraciones."
        if y10.last >= 4.5:
            rd += f" A {y10.last:.2f}% el bono compite con las acciones: exige más a las valoraciones."
            st = "watch" if st == "ok" else st
        inds.append(_ind("dgs10", "Bono EE. UU. 10 años", y10, "%", st, rd, ac, ch, "pb en 30 días", 2))

    curve = s["T10Y2Y"]
    if curve.ok:
        was_inverted = (curve.min_since(540) or 0) < 0
        if curve.last < 0:
            st, rd = "watch", f"Curva invertida ({curve.last * 100:.0f} pb): el 2 años paga más que el 10 años."
            ac = ("Históricamente avisa de recesión con 6-18 meses de adelanto. No es señal de venta inmediata, "
                  "pero conviene vigilar beneficios de cíclicas y bancos regionales.")
        elif was_inverted and curve.last < 0.75:
            st, rd = "watch", f"La curva se ha desinvertido hace poco ({curve.last * 100:+.0f} pb)."
            ac = ("Las recesiones suelen llegar después de desinvertir, no durante la inversión. Prudencia con "
                  "cíclicas y small caps; mejor calidad, defensivas y algo de bonos.")
        else:
            st, rd = "ok", f"Curva con pendiente normal ({curve.last * 100:+.0f} pb)."
            ac = "Entorno normal para bancos (prestan a largo y se financian a corto) y para el ciclo."
        inds.append(_ind("curve", "Curva 10 años − 2 años", curve, "pp", st, rd, ac,
                         curve.change(30) * 100, "pb en 30 días", 2))

    y2, effr = s["DGS2"], s["EFFR"]
    if y2.ok and effr.ok:
        gap = (y2.last - effr.last) * 100
        if gap <= -50:
            st, rd = "ok", f"El 2 años está {-gap:.0f} pb por debajo del tipo de la Fed ({effr.last:.2f}%)."
            ac = ("El mercado descuenta bajadas de tipos. Si llegan sin recesión, suele ser bueno para acciones; "
                  "si el mercado se adelanta demasiado, riesgo de decepción en cada reunión de la Fed.")
        elif gap >= 25:
            st, rd = "watch", f"El 2 años está {gap:.0f} pb por encima del tipo de la Fed ({effr.last:.2f}%)."
            ac = "El mercado descuenta subidas de tipos: viento en contra para bolsa y crecimiento."
        else:
            st, rd = "ok", f"El 2 años ({y2.last:.2f}%) está cerca del tipo de la Fed ({effr.last:.2f}%)."
            ac = "El mercado no espera grandes cambios de tipos a corto plazo."
        inds.append(_ind("fed", "Bono 2 años vs. tipo Fed", y2, "%", st, rd, ac, gap, "pb sobre el tipo Fed", 2))

    move = s["^MOVE"]
    if move.ok:
        v = move.last
        if v >= 120:
            st, rd = "stress", f"MOVE en {v:.0f}: volatilidad alta en los bonos."
            ac = ("Cuando los bonos se mueven así, la bolsa suele seguir (financiación más cara, ventas forzadas). "
                  "Reduce apalancamiento y tamaño de posiciones.")
        elif v >= 100:
            st, rd = "watch", f"MOVE en {v:.0f}: volatilidad de bonos por encima de lo normal."
            ac = "Vigila subastas del Tesoro y datos de inflación; la bolsa es más sensible a sorpresas de tipos."
        else:
            st, rd = "ok", f"MOVE en {v:.0f}: bonos tranquilos."
            ac = "Bonos tranquilos suelen acompañar subidas de bolsa y compresión del VIX."
        inds.append(_ind("move", "MOVE (volatilidad de bonos)", move, "", st, rd, ac, move.change(30), "en 30 días", 0))

    vix = s["^VIX"]
    if vix.ok:
        v = vix.last
        if v >= 35:
            st, rd = "stress", f"VIX en {v:.0f}: pánico."
            ac = ("Históricamente, comprar con VIX > 35 ha dado buenos resultados a 6-12 meses, pero a corto "
                  "puede empeorar. Entradas escalonadas, nunca de golpe.")
        elif v >= 25:
            st, rd = "watch", f"VIX en {v:.0f}: miedo."
            ac = "Movimientos amplios: stops más anchos o posiciones más pequeñas."
        elif v < 14:
            st, rd = "watch", f"VIX en {v:.0f}: complacencia."
            ac = "Coberturas baratas (puts) y poco margen para sorpresas; no persigas subidas extendidas."
        else:
            st, rd = "ok", f"VIX en {v:.0f}: normal."
            ac = "Sin señal de estrés en la volatilidad de la bolsa."
        inds.append(_ind("vix", "VIX (volatilidad de bolsa)", vix, "", st, rd, ac, vix.change(30), "en 30 días", 1))

    hy = s["BAMLH0A0HYM2"]
    if hy.ok:
        ch = hy.change(30)
        if hy.last >= 5 or ch >= 0.75:
            st, rd = "stress", f"Diferencial high yield en {hy.last:.2f} pp ({ch:+.2f} en un mes)."
            ac = ("El crédito arriesgado se encarece: suele anticipar caídas de bolsa y problemas en empresas "
                  "endeudadas. Evita balances débiles; prima calidad.")
        elif hy.last < 3.5:
            st, rd = "ok", f"Diferencial high yield en {hy.last:.2f} pp: crédito muy relajado."
            ac = "Apetito por riesgo alto y financiación fácil. Bueno para bolsa, aunque deja poco colchón si cambia."
        else:
            st, rd = "ok", f"Diferencial high yield en {hy.last:.2f} pp: normal."
            ac = "Crédito sin tensiones."
        inds.append(_ind("hy", "Diferencial high yield", hy, "pp", st, rd, ac, ch, "pp en 30 días", 2))

    net = _net_liquidity(s)
    if net.ok:
        ch = net.change(28)
        if ch is not None and ch >= 100:
            st, rd = "ok", f"La liquidez neta sube {ch:,.0f} mil M$ en 4 semanas."
            ac = "Liquidez entrando al sistema: viento a favor para bolsa, especialmente growth y cripto."
        elif ch is not None and ch <= -100:
            st, rd = "watch", f"La liquidez neta baja {-ch:,.0f} mil M$ en 4 semanas."
            ac = ("Liquidez saliendo (Tesoro rellenando su cuenta o la Fed reduciendo balance): suele frenar a los "
                  "activos más especulativos.")
        else:
            st, rd = "ok", f"Liquidez neta estable ({(ch or 0):+,.0f} mil M$ en 4 semanas)."
            ac = "Sin impulso ni drenaje relevante de liquidez."
        inds.append(_ind("netliq", "Liquidez neta (Fed − TGA − repo inverso)", net, "mil M$", st, rd, ac, ch,
                         "mil M$ en 4 semanas", 0))

    res, rrp = s["WRESBAL"], s["RRPONTSYD"]
    if res.ok:
        low_rrp = rrp.ok and rrp.last < 50
        if res.last < 2900:
            st = "stress"
            rd = f"Reservas bancarias en {res.last:,.0f} mil M$: cerca de escasas."
            ac = ("Con reservas escasas aparecen tensiones en repo (como en septiembre de 2019). Probable que la "
                  "Fed pare la reducción de balance o inyecte liquidez: vigila sus comunicados.")
        elif res.last < 3200 and low_rrp:
            st = "watch"
            rd = f"Reservas en {res.last:,.0f} mil M$ y el repo inverso casi vacío ({rrp.last:,.0f} mil M$)."
            ac = "El colchón se ha agotado: cada dólar que drena el Tesoro o la Fed sale ya de las reservas."
        else:
            st, rd = "ok", f"Reservas bancarias en {res.last:,.0f} mil M$: holgadas."
            ac = "Sin riesgo de escasez de reservas a corto plazo."
        inds.append(_ind("reserves", "Reservas bancarias en la Fed", res, "mil M$", st, rd, ac,
                         res.change(28), "mil M$ en 4 semanas", 0))

    sofr, iorb = s["SOFR"], s["IORB"]
    if sofr.ok and iorb.ok:
        spread = _S([(d, v - (_S([p for p in iorb.pts if p[0] <= d]).last or v)) for d, v in sofr.pts[-260:]])
        bps = spread.last * 100
        recent = [v for _, v in spread.pts[-20:]]
        days_above = sum(1 for v in recent if v > 0)
        if bps > 5 or days_above >= 5:
            st = "stress"
            rd = f"SOFR {bps:+.0f} pb sobre el IORB ({days_above} de las últimas 20 sesiones por encima)."
            ac = ("Tensión en la fontanería: falta efectivo en el repo. La Fed suele responder (facilidad de repo, "
                  "parar QT, compras de letras). Hasta entonces, más volatilidad en bolsa y bonos.")
        elif bps > 0:
            st, rd = "watch", f"SOFR {bps:+.0f} pb sobre el IORB."
            ac = "Primer síntoma de efectivo justo en el repo (es normal en fin de mes o de trimestre)."
        else:
            st, rd = "ok", f"SOFR {bps:+.0f} pb respecto al IORB: el repo funciona con normalidad."
            ac = "Fontanería sin tensiones."
        spread.pts = [(d, v * 100) for d, v in spread.pts]
        inds.append(_ind("sofr", "SOFR − IORB (tensión en repo)", spread, "pb", st, rd, ac,
                         spread.change(30), "pb en 30 días", 0))

    stress = sum(i["status"] == "stress" for i in inds)
    watch = sum(i["status"] == "watch" for i in inds)
    if stress >= 2 or (stress and watch >= 3):
        regime, summary = "tenso", "Varias señales de estrés: prioriza proteger capital, posiciones pequeñas y calidad."
    elif stress or watch >= 3:
        regime, summary = "mixto", "Algunas señales a vigilar: selectivo, sin apalancamiento."
    else:
        regime, summary = "favorable", "Sin tensiones relevantes en tipos, crédito ni liquidez."
    return {"regime": regime, "summary": summary, "stress": stress, "watch": watch, "indicators": inds}


def digest_lines(db: Session) -> list[str]:
    snap = snapshot(db)
    if not snap["indicators"]:
        return []
    icon = {"favorable": "🟢", "mixto": "🟡", "tenso": "🔴"}[snap["regime"]]
    by = {i["key"]: i for i in snap["indicators"]}
    parts = []
    if "dgs10" in by:
        parts.append(f"10 años {by['dgs10']['value']:.2f}%")
    if "move" in by:
        parts.append(f"MOVE {by['move']['value']:.0f}")
    if "vix" in by:
        parts.append(f"VIX {by['vix']['value']:.0f}")
    if "netliq" in by and by["netliq"]["change"] is not None:
        parts.append(f"liquidez {by['netliq']['change']:+,.0f} mil M$/4 sem")
    lines = [f"{icon} <b>Macro: {snap['regime']}</b> · " + " · ".join(parts)]
    for i in snap["indicators"]:
        if i["status"] == "stress":
            lines.append(f"  • ⚠️ {i['reading']}")
    return lines
