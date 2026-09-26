"""Backtest of app/setups.py: does a high setup score actually precede a move
in the next ~20 trading days, and does the stop/target plan make money?

Prices go to a local JSON cache (backend/setups/.cache/, gitignored) instead
of PriceCache, so running this never touches the committed SQLite that the
crons keep rewriting.

Usage:
    python backtest.py                 # full run (first run downloads ~5-10 min)
    python backtest.py --limit 50      # quick smoke test
    python backtest.py --refresh       # re-download prices

Writes backtest_report.md next to this file.
"""
import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402  (backtest-only dependency, never imported by app/)

from app import prices  # noqa: E402
from app import setups  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Trade  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, ".cache", "prices")
REPORT_PATH = os.path.join(HERE, "backtest_report.md")

HISTORY_START = date(2019, 6, 1)
SAMPLE_EVERY = 5  # bars; daily samples would be heavily overlapping anyway
MIN_TRADES = 5  # universe: tickers Congress traded at least this often since 2021
SPLIT_DATE = date(2025, 1, 1)  # in-sample before, out-of-sample after

# Commodities/sectors via liquid ETFs, since "stock o commodity"
EXTRA_TICKERS = ["GLD", "SLV", "USO", "UNG", "CPER", "DBA", "URA", "XLE", "XLF", "XLK", "XLV", "SMH", "QQQ", "IWM"]
GRID = [(s, t) for s in (1.5, 2.0, 2.5) for t in (2.0, 3.0, 4.0)]


# ---------------------------------------------------------------- data

def load_bars(ticker: str, refresh: bool) -> list[dict]:
    path = os.path.join(CACHE_DIR, f"{ticker}.json")
    if not refresh and os.path.exists(path):
        with open(path) as fh:
            raw = json.load(fh)
    else:
        rows = prices._fetch_from_yahoo(ticker, HISTORY_START, date.today())
        prices.throttle()
        raw = [{**r, "date": r["date"].isoformat()} for r in rows]
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(raw, fh)
    return [{**r, "date": date.fromisoformat(r["date"])} for r in raw]


def load_universe_and_events(limit: int | None):
    db = SessionLocal()
    try:
        trades = (
            db.query(Trade)
            .filter(Trade.ticker.isnot(None), Trade.ticker != "", Trade.transaction_type.in_(["purchase", "sale"]))
            .all()
        )
    finally:
        db.close()

    counts: dict[str, int] = defaultdict(int)
    events: dict[str, list] = defaultdict(list)
    purchases = []
    for t in trades:
        tk = t.ticker.strip().upper()
        if t.transaction_date and t.transaction_date >= date(2021, 1, 1):
            counts[tk] += 1
        if t.disclosure_date:
            events[tk].append((t.disclosure_date, t.member_match_key, t.transaction_type))
            if t.transaction_type == "purchase":
                purchases.append((tk, t.disclosure_date, t.member_match_key, t.amount_range_low or 0))

    universe = [tk for tk, n in sorted(counts.items(), key=lambda x: -x[1]) if n >= MIN_TRADES and tk.replace(".", "").replace("-", "").isalnum()]
    if limit:
        universe = universe[:limit]
    universe += [t for t in EXTRA_TICKERS if t not in universe]
    return universe, events, purchases


# ---------------------------------------------------------------- simulation

def simulate(bars: list[dict], i: int, f: dict, direction: str, stop_atr: float, target_atr: float):
    """Enter at next open, exit at stop/target/horizon. Same-bar stop+target
    counts as a stop (conservative). Returns (return_pct, outcome)."""
    plan = setups.trade_plan(f, direction, stop_atr, target_atr)
    s = 1 if direction == "long" else -1
    entry = bars[i + 1]["open"] or bars[i + 1]["close"]
    stop, target = plan["stop"], plan["target"]
    for j in range(i + 1, min(i + 1 + setups.HORIZON_BARS, len(bars))):
        b = bars[j]
        o = b["open"] or b["close"]
        if (s > 0 and o <= stop) or (s < 0 and o >= stop):
            return s * (o / entry - 1), "stop"
        if (s > 0 and b["low"] <= stop) or (s < 0 and b["high"] >= stop):
            return s * (stop / entry - 1), "stop"
        if (s > 0 and o >= target) or (s < 0 and o <= target):
            return s * (o / entry - 1), "target"
        if (s > 0 and b["high"] >= target) or (s < 0 and b["low"] <= target):
            return s * (target / entry - 1), "target"
    last = bars[min(i + setups.HORIZON_BARS, len(bars) - 1)]["close"]
    return s * (last / entry - 1), "time"


def run(limit: int | None, refresh: bool):
    universe, events, purchases = load_universe_and_events(limit)
    log.info("universe: %d tickers", len(universe))

    spy_bars = load_bars("SPY", refresh)
    spy = {b["date"]: b["close"] for b in spy_bars}

    rows = []
    congress_rows = []
    purchases_by_ticker: dict[str, list] = defaultdict(list)
    for p in purchases:
        purchases_by_ticker[p[0]].append(p)

    for k, tk in enumerate(universe, 1):
        try:
            bars = load_bars(tk, refresh)
        except Exception:
            log.exception("failed %s", tk)
            continue
        bars = [b for b in bars if b.get("close") and b.get("high") and b.get("low")]
        if len(bars) < setups.WARMUP_BARS + 40:
            continue
        feats = setups.compute_features(bars, spy, events.get(tk))
        idx_by_date = {b["date"]: i for i, b in enumerate(bars)}

        def fwd_excess(i):
            j = i + setups.HORIZON_BARS
            if j >= len(bars):
                return None
            d0, d1 = bars[i]["date"], bars[j]["date"]
            if d0 not in spy or d1 not in spy:
                return None
            return (bars[j]["close"] / bars[i]["close"] - 1) - (spy[d1] / spy[d0] - 1)

        for i in range(0, len(bars) - setups.HORIZON_BARS - 1, SAMPLE_EVERY):
            f = feats[i]
            if f is None or f["dollar_vol"] < setups.MIN_DOLLAR_VOLUME:
                continue
            fx = fwd_excess(i)
            if fx is None:
                continue
            row = {
                "ticker": tk,
                "date": f["date"],
                "fwd_excess": fx,
                **{k2: f[k2] for k2 in ("rsi", "cmf", "obv_slope", "nvi_above", "mfi", "bbw_pct", "rs20", "rs60", "ret20", "dist_hi52", "rel_vol", "atr_pct", "congress_buyers", "congress_sellers")},
                "above200": f["close"] > f["sma200"],
                "trend_up": f["sma50"] > f["sma200"],
                "dist_sma50": f["close"] / f["sma50"] - 1,
                "dist_sma20": f["close"] / f["sma20"] - 1,
            }
            for direction in ("long", "short"):
                st = setups.score(f, direction)
                row[f"{direction}_score"] = st.score
                for b, pts in st.blocks.items():
                    row[f"{direction}_{b}"] = pts
                for sa, ta in GRID:
                    r, outcome = simulate(bars, i, f, direction, sa, ta)
                    row[f"{direction}_ret_{sa}_{ta}"] = r
                    if (sa, ta) == (setups.STOP_ATR, setups.TARGET_ATR):
                        row[f"{direction}_outcome"] = outcome
            rows.append(row)

        # Congress purchases: what did the indicators say at disclosure time,
        # and how did the ones that worked differ from the ones that didn't?
        for _, disc, member, amount in purchases_by_ticker.get(tk, []):
            i = next((idx_by_date[disc + timedelta(days=x)] for x in range(5) if disc + timedelta(days=x) in idx_by_date), None)
            if i is None or feats[i] is None:
                continue
            fx = fwd_excess(i)
            if fx is None:
                continue
            f = feats[i]
            congress_rows.append({
                "ticker": tk, "date": disc, "member": member, "amount": amount, "fwd_excess": fx,
                "long_score": setups.score(f, "long").score,
                **{k2: f[k2] for k2 in ("rsi", "cmf", "obv_slope", "nvi_above", "mfi", "bbw_pct", "rs60", "dist_hi52", "rel_vol", "atr_pct")},
            })

        if k % 25 == 0:
            log.info("%d/%d tickers, %d samples", k, len(universe), len(rows))

    return pd.DataFrame(rows), pd.DataFrame(congress_rows)


# ---------------------------------------------------------------- report

def pct(x):
    return f"{x * 100:+.2f}%"


def score_table(df: pd.DataFrame, direction: str) -> str:
    s = 1 if direction == "long" else -1
    col = f"{direction}_score"
    bins = [0, 30, 40, 50, 60, 70, 101]
    df = df.assign(bucket=pd.cut(df[col], bins, right=False))
    ret = f"{direction}_ret_{setups.STOP_ATR}_{setups.TARGET_ATR}"
    lines = [
        "| Score | N | Exceso 20d vs SPY (a favor) | % aciertos dirección | Plan: ret. medio | Plan: % objetivo | Plan: % stop |",
        "|---|---|---|---|---|---|---|",
    ]
    for b, g in df.groupby("bucket", observed=True):
        if len(g) < 20:
            continue
        fav = g["fwd_excess"] * s
        lines.append(
            f"| {b} | {len(g)} | {pct(fav.mean())} | {(fav > 0).mean() * 100:.0f}% | {pct(g[ret].mean())} "
            f"| {(g[f'{direction}_outcome'] == 'target').mean() * 100:.0f}% | {(g[f'{direction}_outcome'] == 'stop').mean() * 100:.0f}% |"
        )
    return "\n".join(lines)


def feature_table(df: pd.DataFrame) -> str:
    """Quintile spread of each raw feature vs forward excess return — lets the
    data say which ingredients carry signal, independently of our weights."""
    lines = ["| Indicador | Q1 (bajo) | Q2 | Q3 | Q4 | Q5 (alto) | Q5−Q1 |", "|---|---|---|---|---|---|---|"]
    for col in ("rsi", "cmf", "obv_slope", "mfi", "bbw_pct", "rs60", "dist_hi52", "rel_vol", "atr_pct"):
        sub = df[[col, "fwd_excess"]].dropna()
        try:
            q = pd.qcut(sub[col], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        m = sub.groupby(q)["fwd_excess"].mean()
        if len(m) < 5:
            continue
        lines.append(f"| {col} | " + " | ".join(pct(x) for x in m) + f" | {pct(m.iloc[-1] - m.iloc[0])} |")
    for col in ("nvi_above",):
        m = df.groupby(col)["fwd_excess"].mean()
        lines.append(f"| {col} (False / True) | {pct(m.get(False, 0))} | | | | {pct(m.get(True, 0))} | {pct(m.get(True, 0) - m.get(False, 0))} |")
    buy = df[df["congress_buyers"] > df["congress_sellers"]]["fwd_excess"].mean()
    sell = df[df["congress_sellers"] > df["congress_buyers"]]["fwd_excess"].mean()
    none = df[df["congress_buyers"] == df["congress_sellers"]]["fwd_excess"].mean()
    lines.append(f"| congreso (neto vende / neutro / neto compra) | {pct(sell)} | | {pct(none)} | | {pct(buy)} | {pct(buy - sell)} |")
    return "\n".join(lines)


def grid_table(df: pd.DataFrame, direction: str, min_score: float) -> str:
    sel = df[df[f"{direction}_score"] >= min_score]
    lines = [f"Señales {direction} con score ≥ {min_score} (N={len(sel)})\n", "| Stop ATR \\ Objetivo ATR | " + " | ".join(str(t) for t in (2.0, 3.0, 4.0)) + " |", "|---|---|---|---|"]
    for sa in (1.5, 2.0, 2.5):
        cells = [pct(sel[f"{direction}_ret_{sa}_{ta}"].mean()) if len(sel) else "—" for ta in (2.0, 3.0, 4.0)]
        lines.append(f"| {sa} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def block_table(df: pd.DataFrame, direction: str) -> str:
    s = 1 if direction == "long" else -1
    cols = [c for c in df.columns if c.startswith(f"{direction}_") and c.split("_", 1)[1] in ("acumulacion", "distribucion", "momentum", "compresion", "volumen", "congreso")]
    lines = ["| Bloque | Exceso medio si bloque ≥ mitad de su máximo | si no | Diferencia |", "|---|---|---|---|"]
    maxes = {"acumulacion": 30, "distribucion": 30, "momentum": 30, "compresion": 10, "volumen": 10, "congreso": 20}
    for c in cols:
        name = c.split("_", 1)[1]
        on = df[df[c] >= maxes[name] / 2]["fwd_excess"] * s
        off = df[df[c] < maxes[name] / 2]["fwd_excess"] * s
        if len(on) < 20:
            continue
        lines.append(f"| {name} (N={len(on)}) | {pct(on.mean())} | {pct(off.mean())} | {pct(on.mean() - off.mean())} |")
    return "\n".join(lines)


def congress_section(cdf: pd.DataFrame) -> str:
    if cdf.empty:
        return "_Sin datos._"
    cdf = cdf.assign(q=pd.qcut(cdf["fwd_excess"], 4, labels=["Peor 25%", "Q2", "Q3", "Mejor 25%"]))
    cols = ["fwd_excess", "long_score", "rsi", "cmf", "obv_slope", "mfi", "bbw_pct", "rs60", "dist_hi52", "rel_vol", "atr_pct"]
    t = cdf.groupby("q", observed=True)[cols].mean()
    t["nvi_above"] = cdf.groupby("q", observed=True)["nvi_above"].mean()
    lines = ["| Cuartil resultado | N | " + " | ".join(cols[1:] + ["nvi_above"]) + " | exceso 20d |", "|---" * (len(cols) + 3) + "|"]
    for q, r in t.iterrows():
        n = (cdf["q"] == q).sum()
        lines.append(f"| {q} | {n} | " + " | ".join(f"{r[c]:.2f}" for c in cols[1:] + ["nvi_above"]) + f" | {pct(r['fwd_excess'])} |")
    hi = cdf[cdf["long_score"] >= 50]["fwd_excess"]
    lo = cdf[cdf["long_score"] < 50]["fwd_excess"]
    lines.append(f"\nCompras de congresistas con score largo ≥ 50: N={len(hi)}, exceso medio {pct(hi.mean())}; con score < 50: N={len(lo)}, {pct(lo.mean())}.")
    lines.append(f"Todas las compras (desde la fecha de *disclosure*): N={len(cdf)}, exceso medio {pct(cdf['fwd_excess'].mean())}.")
    return "\n".join(lines)


def write_report(df: pd.DataFrame, cdf: pd.DataFrame):
    ins, oos = df[df["date"] < SPLIT_DATE], df[df["date"] >= SPLIT_DATE]
    parts = [
        f"# Backtest de setups — {datetime.now():%Y-%m-%d %H:%M}",
        f"\nUniverso: {df['ticker'].nunique()} tickers (operados ≥{MIN_TRADES} veces por el Congreso desde 2021 + ETFs de commodities/sectores), "
        f"liquidez ≥ ${setups.MIN_DOLLAR_VOLUME / 1e6:.0f}M/día. Muestras cada {SAMPLE_EVERY} sesiones: {len(df)} "
        f"({df['date'].min()} → {df['date'].max()}). Horizonte {setups.HORIZON_BARS} sesiones. "
        f"Plan por defecto: stop {setups.STOP_ATR} ATR, objetivo {setups.TARGET_ATR} ATR, entrada en la apertura siguiente.",
        "\n**Sesgos conocidos:** supervivencia (solo tickers que Yahoo aún sirve), universo sesgado a large caps, "
        "muestras solapadas (no son independientes), sin comisiones ni slippage.",
        f"\nReferencia: exceso medio de *cualquier* muestra = {pct(df['fwd_excess'].mean())}.",
    ]
    for name, part in (("In-sample (< 2025)", ins), ("Out-of-sample (≥ 2025)", oos)):
        parts.append(f"\n## {name} — {len(part)} muestras")
        for direction in ("long", "short"):
            parts.append(f"\n### {'Alcista' if direction == 'long' else 'Bajista'}: rendimiento por score\n")
            parts.append(score_table(part, direction))
    parts.append("\n## Qué bloque aporta (todo el periodo)")
    for direction in ("long", "short"):
        parts.append(f"\n### {direction}\n")
        parts.append(block_table(df, direction))
    parts.append("\n## Indicadores sueltos: exceso 20d por quintil (todo el periodo)\n")
    parts.append(feature_table(df))
    parts.append("\n## Rejilla stop/objetivo (ret. medio por operación)\n")
    for direction in ("long", "short"):
        parts.append(grid_table(df, direction, 60) + "\n")
    parts.append("\n## Compras de congresistas: qué marcaban los indicadores en las que funcionaron\n")
    parts.append(congress_section(cdf))
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    log.info("report written to %s", REPORT_PATH)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    df, cdf = run(args.limit, args.refresh)
    if df.empty:
        log.error("no samples")
        sys.exit(1)
    df.to_pickle(os.path.join(HERE, ".cache", "samples.pkl"))
    cdf.to_pickle(os.path.join(HERE, ".cache", "congress.pkl"))
    write_report(df, cdf)
