"""Technical "setup" scanner: accumulation + momentum + volatility squeeze +
Congress flow, scored for both directions, with a concrete trade plan.

Pure Python on purpose (no pandas/numpy): this lives in app/ so a future API
endpoint can import it on Vercel without bloating the bundle, and the series
involved are small (a few hundred to ~1.5k daily bars per ticker).

Everything here is point-in-time: features for bar `i` only look at bars
<= i, so the same code drives both the live scanner and the backtest
(backend/setups/backtest.py) without lookahead.

About "institutional accumulation": no free source gives real-time
institutional flow (13F is quarterly with a 45-day lag). What we compute are
the standard price/volume proxies — the same family Konkorde 2.0 is built
from: NVI ("manos fuertes", moves on low-volume days), MFI, CMF, OBV.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

WARMUP_BARS = 260  # need ~1y for SMA200 / 52w high / NVI EMA255
MIN_DOLLAR_VOLUME = 20_000_000  # 20-day avg; below this a "setup" is mostly noise/slippage
HORIZON_BARS = 20  # ~1 month of trading days

# Trade plan, in ATR(14) multiples from the signal close. Defaults chosen by
# the backtest — see backend/setups/backtest.py.
STOP_ATR = 2.0
TARGET_ATR = 3.0


# ---------------------------------------------------------------- primitives

def _sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _ema(values: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    k = 2 / (n + 1)
    prev = None
    for i, v in enumerate(values):
        if v is None:
            continue
        prev = v if prev is None else prev + k * (v - prev)
        out[i] = prev
    return out


def _rolling_sum(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s
    return out


def _wilder(values: list[float], n: int) -> list[float | None]:
    """Wilder smoothing (RSI/ATR style)."""
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    avg = sum(values[:n]) / n
    out[n - 1] = avg
    for i in range(n, len(values)):
        avg = (avg * (n - 1) + values[i]) / n
        out[i] = avg
    return out


# ---------------------------------------------------------------- features

def compute_features(
    bars: list[dict],
    spy_close: dict[date, float] | None = None,
    congress_events: list[tuple[date, str, str]] | None = None,
) -> list[dict | None]:
    """Per-bar feature dicts (None during warmup).

    bars: ascending daily OHLCV dicts (date/open/high/low/close/volume).
    spy_close: date -> SPY close, for relative strength. Optional.
    congress_events: (disclosure_date, member_match_key, "purchase"|"sale")
      for this ticker — disclosure date, not transaction date, because that's
      when the information became public.
    """
    bars = [b for b in bars if b.get("close") and b.get("high") and b.get("low")]
    n = len(bars)
    if n < WARMUP_BARS:
        return [None] * n

    d = [b["date"] for b in bars]
    o = [b.get("open") or b["close"] for b in bars]
    h = [b["high"] for b in bars]
    lo = [b["low"] for b in bars]
    c = [b["close"] for b in bars]
    v = [float(b.get("volume") or 0) for b in bars]

    sma20, sma50, sma200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)

    # RSI(14)
    gains = [0.0] + [max(c[i] - c[i - 1], 0) for i in range(1, n)]
    losses = [0.0] + [max(c[i - 1] - c[i], 0) for i in range(1, n)]
    ag, al = _wilder(gains, 14), _wilder(losses, 14)
    rsi = [None if ag[i] is None else (100.0 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])) for i in range(n)]

    # ATR(14)
    tr = [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, n)]
    atr = _wilder(tr, 14)

    # Chaikin Money Flow(20)
    mfv = [((c[i] - lo[i]) - (h[i] - c[i])) / (h[i] - lo[i]) * v[i] if h[i] > lo[i] else 0.0 for i in range(n)]
    s_mfv, s_v20 = _rolling_sum(mfv, 20), _rolling_sum(v, 20)

    # OBV
    obv = [0.0]
    for i in range(1, n):
        obv.append(obv[-1] + (v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0))

    # NVI (Fosback) — the "manos fuertes" line of Konkorde. Only moves on days
    # where volume falls, the idea being that's when informed money acts.
    nvi = [1000.0]
    for i in range(1, n):
        nvi.append(nvi[-1] * (c[i] / c[i - 1]) if v[i] < v[i - 1] and c[i - 1] else nvi[-1])
    nvi_ema = _ema(nvi, 255)

    # MFI(14)
    tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(n)]
    pos = [0.0] + [tp[i] * v[i] if tp[i] > tp[i - 1] else 0.0 for i in range(1, n)]
    neg = [0.0] + [tp[i] * v[i] if tp[i] < tp[i - 1] else 0.0 for i in range(1, n)]
    spos, sneg = _rolling_sum(pos, 14), _rolling_sum(neg, 14)

    # Bollinger width (20, 2σ)
    bbw: list[float | None] = [None] * n
    for i in range(19, n):
        win = c[i - 19 : i + 1]
        m = sum(win) / 20
        sd = math.sqrt(sum((x - m) ** 2 for x in win) / 20)
        bbw[i] = 4 * sd / m if m else None

    dollar_vol = _sma([c[i] * v[i] for i in range(n)], 20)
    vol50 = _sma(v, 50)
    vol5 = _sma(v, 5)

    spy = [spy_close.get(x) if spy_close else None for x in d]

    events = sorted(congress_events or [])

    out: list[dict | None] = [None] * n
    ev_i = 0
    window: list[tuple[date, str, str]] = []
    for i in range(WARMUP_BARS, n):
        if None in (sma200[i], rsi[i], atr[i], nvi_ema[i], bbw[i], spos[i]) or not c[i - 20] or not c[i - 60]:
            continue

        # Congress flow over the trailing 30 days (by disclosure date)
        while ev_i < len(events) and events[ev_i][0] <= d[i]:
            window.append(events[ev_i])
            ev_i += 1
        cutoff = d[i] - timedelta(days=30)
        window = [e for e in window if e[0] > cutoff]
        buyers = {m for _, m, t in window if t == "purchase"}
        sellers = {m for _, m, t in window if t == "sale"}

        bbw_hist = [x for x in bbw[i - 119 : i + 1] if x is not None]
        bbw_pct = sum(1 for x in bbw_hist if x <= bbw[i]) / len(bbw_hist)

        hi252 = max(h[i - 251 : i + 1])
        lo252 = min(lo[i - 251 : i + 1])

        rs20 = rs60 = None
        if spy[i] and spy[i - 20] and spy[i - 60]:
            rs20 = (c[i] / c[i - 20]) - (spy[i] / spy[i - 20])
            rs60 = (c[i] / c[i - 60]) - (spy[i] / spy[i - 60])

        out[i] = {
            "date": d[i],
            "open": o[i],
            "close": c[i],
            "atr": atr[i],
            "atr_pct": atr[i] / c[i],
            "rsi": rsi[i],
            "sma20": sma20[i],
            "sma50": sma50[i],
            "sma200": sma200[i],
            "ret20": c[i] / c[i - 20] - 1,
            "ret60": c[i] / c[i - 60] - 1,
            "rs20": rs20,
            "rs60": rs60,
            "dist_hi52": c[i] / hi252,
            "dist_lo52": c[i] / lo252,
            "cmf": s_mfv[i] / s_v20[i] if s_v20[i] else 0.0,
            "obv_slope": (obv[i] - obv[i - 20]) / s_v20[i] if s_v20[i] else 0.0,
            "nvi_above": nvi[i] > nvi_ema[i],
            "nvi_ret20": nvi[i] / nvi[i - 20] - 1,
            "mfi": 100.0 if sneg[i] == 0 else 100 - 100 / (1 + spos[i] / sneg[i]),
            "bbw_pct": bbw_pct,
            "dollar_vol": dollar_vol[i],
            "rel_vol": vol5[i] / vol50[i] if vol50[i] else 1.0,
            "low10": min(lo[i - 9 : i + 1]),
            "high10": max(h[i - 9 : i + 1]),
            "congress_buyers": len(buyers),
            "congress_sellers": len(sellers),
        }
    return out


# ---------------------------------------------------------------- scoring

@dataclass
class Setup:
    direction: str  # "long" | "short"
    score: float
    blocks: dict[str, float] = field(default_factory=dict)  # block -> points
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score(f: dict, direction: str) -> Setup:
    """0-100 score. Blocks and max points:
    accumulation 30, momentum 30, squeeze 10, volume 10, congress 20.
    `direction="short"` mirrors every condition (distribution, downtrend...).
    """
    s = 1 if direction == "long" else -1
    blocks: dict[str, float] = {}
    reasons: list[str] = []
    risks: list[str] = []

    # --- Accumulation / distribution (Konkorde-style proxies)
    acc = 0.0
    acc_hits: list[str] = []
    cmf = f["cmf"] * s
    acc += 10 * _clip(cmf / 0.15)
    if cmf > 0.05:
        acc_hits.append("CMF")
    obv = f["obv_slope"] * s
    acc += 8 * _clip(obv / 0.3)
    if obv > 0.1:
        acc_hits.append("OBV")
    if f["nvi_above"] == (s > 0):
        acc += 6
        acc_hits.append("NVI")
    mfi = f["mfi"]
    if (s > 0 and 50 <= mfi <= 80) or (s < 0 and 20 <= mfi <= 50):
        acc += 6
    if acc_hits:
        strength = "fuerte " if len(acc_hits) >= 2 else ""
        reasons.insert(0, f"{'Entrada' if s > 0 else 'Salida'} de dinero {strength}({', '.join(acc_hits)})")
    blocks["acumulacion" if s > 0 else "distribucion"] = acc

    # --- Momentum / trend
    mom = 0.0
    c, s50, s200 = f["close"], f["sma50"], f["sma200"]
    if (s > 0 and c > s50 > s200) or (s < 0 and c < s50 < s200):
        mom += 10
        reasons.append(f"Tendencia {'alcista' if s > 0 else 'bajista'} sólida")
    elif (s > 0 and c > s50) or (s < 0 and c < s50):
        mom += 5
    rsi = f["rsi"]
    if (s > 0 and 50 <= rsi <= 70) or (s < 0 and 30 <= rsi <= 50):
        mom += 8
        reasons.append(f"RSI {rsi:.0f}: fuerza sin {'sobrecompra' if s > 0 else 'sobreventa'}")
    elif (s > 0 and rsi > 75) or (s < 0 and rsi < 25):
        risks.append(f"RSI {rsi:.0f}, {'sobrecomprado' if s > 0 else 'sobrevendido'}")
    if f["rs60"] is not None:
        rs = f["rs60"] * s
        mom += 7 * _clip(rs / 0.15)
        if rs > 0.05:
            reasons.append(f"{'Bate' if s > 0 else 'Pierde contra'} al S&P 500 ({f['rs60'] * 100:+.0f} pts en 3 meses)")
    if s > 0 and f["dist_hi52"] >= 0.92:
        mom += 5
        reasons.append(f"Cerca de máximos anuales (a {(1 - f['dist_hi52']) * 100:.0f}%)")
    elif s < 0 and f["dist_lo52"] <= 1.08:
        mom += 5
        reasons.append(f"Cerca de mínimos anuales (a {(f['dist_lo52'] - 1) * 100:.0f}%)")
    blocks["momentum"] = mom

    # --- Volatility squeeze (setup for expansion, direction-agnostic)
    sq = 10 * _clip((0.35 - f["bbw_pct"]) / 0.35)
    if f["bbw_pct"] <= 0.2:
        reasons.append("Volatilidad comprimida: posible ruptura")
    blocks["compresion"] = sq

    # --- Volume confirmation
    vol = 0.0
    if f["rel_vol"] >= 1.2 and (f["ret20"] * s) > 0:
        vol = 10 * _clip((f["rel_vol"] - 1) / 0.8)
        reasons.append(f"Volumen x{f['rel_vol']:.1f} sobre su media")
    blocks["volumen"] = vol

    # --- Congress flow (our own data)
    cong = 0.0
    same, other = (f["congress_buyers"], f["congress_sellers"]) if s > 0 else (f["congress_sellers"], f["congress_buyers"])
    net = same - other
    if net > 0:
        cong = min(20.0, 8.0 * net)
        reasons.insert(0, f"{same} {'congresista' if same == 1 else 'congresistas'} {'comprando' if s > 0 else 'vendiendo'} (30 días)")
    elif net < 0:
        risks.append(f"{other} {'congresista' if other == 1 else 'congresistas'} en sentido contrario")
    blocks["congreso"] = cong

    if f["dollar_vol"] < MIN_DOLLAR_VOLUME:
        risks.append(f"Poca liquidez (${f['dollar_vol'] / 1e6:.0f}M/día)")

    return Setup(direction, round(sum(blocks.values()), 1), blocks, reasons, risks)


def trade_plan(f: dict, direction: str, stop_atr: float = STOP_ATR, target_atr: float = TARGET_ATR) -> dict:
    """Entry/stop/target from the signal close. Stop is the tighter of the ATR
    stop and just beyond the 10-day swing, but never closer than 1 ATR (noise)."""
    c, atr = f["close"], f["atr"]
    if direction == "long":
        stop = max(c - stop_atr * atr, min(f["low10"] - 0.25 * atr, c - atr))
        target = c + target_atr * atr
    else:
        stop = min(c + stop_atr * atr, max(f["high10"] + 0.25 * atr, c + atr))
        target = c - target_atr * atr
    return {
        "entry": c,
        "entry_max": c + 0.5 * atr if direction == "long" else c - 0.5 * atr,  # don't chase beyond this
        "stop": stop,
        "target": target,
        "risk_reward": abs(target - c) / abs(c - stop) if c != stop else None,
        "horizon_bars": HORIZON_BARS,
    }


# ---------------------------------------------------------------- alert text

def _fmt_price(x: float) -> str:
    return f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def _score_bar(score: float) -> str:
    filled = round(score / 10)
    return "▰" * filled + "▱" * (10 - filled)


def plan_lines(f: dict, direction: str = "long") -> list[str]:
    """The trade plan as an aligned <pre> block + a risk/reward line."""
    import html

    plan = trade_plan(f, direction)
    c = plan["entry"]
    pct = lambda x: f"{(x / c - 1) * 100:+.0f}%"  # noqa: E731

    rows = [
        ("Entrada", _fmt_price(c), f"máx {_fmt_price(plan['entry_max'])}"),
        ("Objetivo", _fmt_price(plan["target"]), pct(plan["target"])),
        ("Stop", _fmt_price(plan["stop"]), pct(plan["stop"])),
    ]
    w = max(len(r[1]) for r in rows)
    table = "\n".join(f"{label:<9}{price:>{w}}  {extra}" for label, price, extra in rows)
    return [
        f"<pre>{html.escape(table, quote=False)}</pre>",
        f"⏱ ~1 mes · gana {plan['risk_reward']:.1f}× lo que arriesga",
    ]


def format_alert(ticker: str, f: dict, st: Setup, name: str | None = None) -> str:
    """Short Telegram HTML caption (fits the 1024-char photo caption limit):
    headline, the plan as an aligned block, and the top reasons."""
    import html

    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    long_ = st.direction == "long"
    lines = [
        f"{'📈' if long_ else '📉'} <b>{e(ticker)}</b>" + (f" · {e(name)}" if name else ""),
        f"{'Posible subida' if long_ else 'Posible bajada'} · <b>{st.score:.0f}</b>/100 {_score_bar(st.score)}",
        "",
        *plan_lines(f, st.direction),
        "",
        *[f"✓ {e(r)}" for r in st.reasons[:4]],
        *[f"⚠ {e(r)}" for r in st.risks[:2]],
        "",
        "<i>Señal automática · no es asesoramiento</i>",
    ]
    return "\n".join(lines)


def render_chart(
    ticker: str, bars: list[dict], f: dict, direction: str = "long", markers: list[tuple[date, float, str]] | None = None
) -> bytes | None:
    """PNG: last ~4 months of closes + SMA50, with the plan drawn as a
    green (target) / red (stop) zone projected ~1 month ahead. `markers`
    (date, price, label) are drawn as amber dots, e.g. an insider's buy.
    matplotlib is imported lazily and installed only in setups.yml — it's not
    in requirements.txt, which Vercel also installs."""
    try:
        import io

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    plan = trade_plan(f, direction)
    closes = [b["close"] for b in bars]
    sma50 = _sma(closes, 50)
    n = min(90, len(bars))
    xs = list(range(n))
    ys = closes[-n:]
    ma = sma50[-n:]
    fut = n - 1 + HORIZON_BARS

    bg, fg, grid = "#0f1419", "#e6e8eb", "#232a33"
    green, red, line = "#22c55e", "#ef4444", "#60a5fa"
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    ax.plot(xs, ys, color=line, lw=2)
    ax.plot(xs, ma, color="#94a3b8", lw=1, ls="--", alpha=0.7, label="Media 50 sesiones")
    entry, target, stop = plan["entry"], plan["target"], plan["stop"]
    ax.fill_between([n - 1, fut], entry, target, color=green, alpha=0.18, lw=0)
    ax.fill_between([n - 1, fut], stop, entry, color=red, alpha=0.18, lw=0)
    for y, col, label in ((target, green, "Objetivo"), (entry, fg, "Entrada"), (stop, red, "Stop")):
        ax.hlines(y, n - 1, fut, colors=col, lw=1.5)
        tag = "" if label == "Entrada" else f" {(y / entry - 1) * 100:+.0f}%"
        ax.text(fut + 0.5, y, f" {label} {_fmt_price(y)}{tag}", color=col, va="center", fontsize=10, fontweight="bold")
    ax.scatter([n - 1], [entry], color=fg, s=30, zorder=5)
    amber = "#f59e0b"
    window_dates = [b["date"] for b in bars[-n:]]
    for i, (d, price, label) in enumerate(markers or []):
        x = next((k for k, wd in enumerate(window_dates) if wd >= d), n - 1)
        ax.hlines(price, x, n - 1, colors=amber, lw=1, ls=":")
        ax.scatter([x], [price], color=amber, s=70, zorder=6, edgecolors=bg, linewidths=1.5)
        ax.annotate(label, (x, price), xytext=(-10, -4 - 14 * i), textcoords="offset points", ha="right", va="center", color=amber, fontsize=9, fontweight="bold")

    ax.set_xlim(0, fut + 22)
    marker_prices = [m[1] for m in markers or []]
    lo = min(min(ys), stop, *marker_prices)
    hi = max(max(ys), target, *marker_prices)
    pad = (hi - lo) * 0.08
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xticks([])
    ax.tick_params(colors="#8b949e", labelsize=9)
    ax.grid(axis="y", color=grid, lw=0.8)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(f"{ticker}  ·  últimos {n} días → próximo mes", color=fg, loc="left", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", frameon=False, labelcolor="#8b949e", fontsize=8)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------- live scan

# Backtest (2020-2026, 488 tickers): only the long side with score >= 70
# beat SPY consistently (every year, in- and out-of-sample): ~0.6 distinct
# signals/week, +1.5% avg per trade with the 2/3 ATR plan, ~52% hit rate.
# Short setups lost money at every score level, so they're not alerted.
ALERT_MIN_SCORE = 70
HIGH_VOL_ATR_PCT = 0.025  # score>=70 AND ATR>2.5% did even better (+2.8-3.2%/trade) but on few samples
COOLDOWN_DAYS = 30
MAX_ALERTS_PER_RUN = 3
EXTRA_TICKERS = ["GLD", "SLV", "USO", "UNG", "CPER", "DBA", "URA", "XLE", "XLF", "XLK", "XLV", "SMH", "QQQ", "IWM"]


def analyze(db, ticker: str) -> tuple[list[dict], dict, Setup] | None:
    """Fetch prices and score one ticker right now (used to add technical
    context to other alerts, e.g. insider buys). None if not enough history."""
    from . import prices
    from .models import Trade

    start, end = date.today() - timedelta(days=560), date.today()
    spy = {b["date"]: b["close"] for b in prices._fetch_from_yahoo("SPY", start, end)}
    bars = prices._fetch_from_yahoo(ticker, start, end)
    events = [
        (d, m, t)
        for d, m, t in db.query(Trade.disclosure_date, Trade.member_match_key, Trade.transaction_type).filter(
            Trade.ticker == ticker, Trade.disclosure_date.isnot(None), Trade.transaction_type.in_(["purchase", "sale"])
        )
    ]
    feats = compute_features(bars, spy, events)
    if not feats or feats[-1] is None:
        return None
    return bars, feats[-1], score(feats[-1], "long")


def universe(db, min_trades: int = 5) -> tuple[list[str], dict[str, list]]:
    """Same universe as the backtest: tickers Congress traded >= min_trades
    times since 2021, plus commodity/sector ETFs. Also returns the Congress
    events per ticker for the flow feature."""
    from collections import defaultdict

    from .models import Trade

    counts: dict[str, int] = defaultdict(int)
    events: dict[str, list] = defaultdict(list)
    q = db.query(Trade.ticker, Trade.transaction_date, Trade.disclosure_date, Trade.member_match_key, Trade.transaction_type).filter(
        Trade.ticker.isnot(None), Trade.ticker != "", Trade.transaction_type.in_(["purchase", "sale"])
    )
    for tk, tx, disc, member, typ in q:
        tk = tk.strip().upper()
        if tx and tx >= date(2021, 1, 1):
            counts[tk] += 1
        if disc:
            events[tk].append((disc, member, typ))
    tickers = [t for t, n in counts.items() if n >= min_trades and t.replace(".", "").replace("-", "").isalnum()]
    return tickers + [t for t in EXTRA_TICKERS if t not in tickers], events


def _simulate_outcome(bars: list[dict], sig) -> str | None:
    """target/stop/time for a past signal, once its horizon has elapsed."""
    after = [b for b in bars if b["date"] > sig.signal_date]
    if len(after) < HORIZON_BARS:
        return None
    for b in after[:HORIZON_BARS]:
        if b["low"] <= sig.stop:
            return "stop"
        if b["high"] >= sig.target:
            return "target"
    return "time"


def _clean_name(raw: str) -> str:
    """PTR asset names look like 'Quanta Services, Inc. - Common Stock (PWR)'."""
    import re

    name = re.split(r"\s+-\s+|\(", raw)[0]
    name = re.sub(r",?\s+(Inc|Corp|Corporation|Co|Ltd|plc|LLC|N\.V|S\.A)\.?$", "", name.strip(), flags=re.I)
    return name.strip()[:40]


def scan_and_alert(db) -> dict:
    from . import prices
    from .config import TELEGRAM_BOT_TOKEN
    from .models import SetupSignal, TelegramSubscriber
    from .models import Trade
    from .telegram_api import send_message, send_photo

    tickers, events = universe(db)
    start, end = date.today() - timedelta(days=560), date.today()
    spy_bars = prices._fetch_from_yahoo("SPY", start, end)
    spy = {b["date"]: b["close"] for b in spy_bars}
    last_session = spy_bars[-1]["date"] if spy_bars else None

    open_signals = {s.ticker: s for s in db.query(SetupSignal).filter(SetupSignal.outcome.is_(None))}
    recent = {
        s.ticker
        for s in db.query(SetupSignal).filter(SetupSignal.signal_date >= date.today() - timedelta(days=COOLDOWN_DAYS))
    }

    candidates = []
    for tk in tickers:
        bars = prices._fetch_from_yahoo(tk, start, end)
        prices.throttle()
        if tk in open_signals:
            outcome = _simulate_outcome(bars, open_signals[tk])
            if outcome:
                open_signals[tk].outcome = outcome
        if not bars or bars[-1]["date"] != last_session or tk in recent:
            continue
        f = compute_features(bars, spy, events.get(tk))[-1]
        if f is None or f["dollar_vol"] < MIN_DOLLAR_VOLUME:
            continue
        st = score(f, "long")
        if st.score >= ALERT_MIN_SCORE:
            candidates.append((st.score, tk, f, st, bars))

    candidates.sort(key=lambda x: (-x[0], x[1]))
    chats = [s.chat_id for s in db.query(TelegramSubscriber).all()] if TELEGRAM_BOT_TOKEN else []
    sent = 0
    for _, tk, f, st, bars in candidates[:MAX_ALERTS_PER_RUN]:
        if f["atr_pct"] >= HIGH_VOL_ATR_PCT:
            st.reasons.append("Alta volatilidad: el grupo que mejor rindió en el backtest")
        plan = trade_plan(f, "long")
        name = db.query(Trade.asset_name).filter(Trade.ticker == tk, Trade.asset_name.isnot(None)).order_by(Trade.id.desc()).first()
        body = format_alert(tk, f, st, _clean_name(name[0]) if name else None)
        png = render_chart(tk, bars, f)
        for c in chats:
            ok = send_photo(c, png, body) if png else False
            sent += ok or send_message(c, body)  # fall back to plain text if the photo fails
        db.add(SetupSignal(
            ticker=tk, direction="long", signal_date=f["date"], score=st.score,
            entry=plan["entry"], stop=plan["stop"], target=plan["target"], reasons=" | ".join(st.reasons),
        ))
    db.commit()
    return {"tickers": len(tickers), "candidates": len(candidates), "messages_sent": sent}
