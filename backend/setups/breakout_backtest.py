"""Backtest of the breakout alert (app/setups.breakout_at): after a close
above a tight base on high volume, does the stop/target plan make money,
and does it beat the plain score >= 70 signal? Reuses backtest.py's price
cache and simulation. Prints a markdown report to stdout.

    python breakout_backtest.py [--limit 50]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

import backtest as bt  # noqa: E402
from app import setups  # noqa: E402

VARIANTS = [(v, w) for v in (1.3, 1.5, 2.0) for w in (0.15, 0.25, 0.35)]


def run(limit):
    universe, events, _ = bt.load_universe_and_events(limit)
    spy = {b["date"]: b["close"] for b in bt.load_bars("SPY", False)}
    rows = []
    for k, tk in enumerate(universe, 1):
        try:
            bars = [b for b in bt.load_bars(tk, False) if b.get("close") and b.get("high") and b.get("low")]
        except Exception:
            continue
        if len(bars) < setups.WARMUP_BARS + 40:
            continue
        feats = setups.compute_features(bars, spy, events.get(tk))
        last_hit = {}
        for i in range(setups.WARMUP_BARS + 1, len(bars) - setups.HORIZON_BARS - 1):
            f = feats[i]
            if f is None or f["dollar_vol"] < setups.MIN_DOLLAR_VOLUME:
                continue
            for v, w in VARIANTS:
                hit = setups.breakout_at(bars, feats, i, v, w)
                if not hit or i - last_hit.get((v, w), -99) < 10:  # one per base
                    continue
                last_hit[(v, w)] = i
                j = i + setups.HORIZON_BARS
                d0, d1 = bars[i]["date"], bars[j]["date"]
                fx = (bars[j]["close"] / bars[i]["close"] - 1) - (spy[d1] / spy[d0] - 1) if d0 in spy and d1 in spy else None
                r, outcome = bt.simulate(bars, i, f, "long", setups.STOP_ATR, setups.TARGET_ATR)
                rows.append({"ticker": tk, "date": d0, "vol": v, "bbw": w, "ret": r, "outcome": outcome, "fx": fx,
                             "score": setups.score(f, "long").score, "atr_pct": f["atr_pct"]})
        if k % 50 == 0:
            print(f"<!-- {k}/{len(universe)} -->", file=sys.stderr)
    return pd.DataFrame(rows)


def table(df):
    out = ["| Volumen ≥ | Base bbw ≤ | Periodo | N | Señales/semana | Ret. medio plan | % objetivo | % stop | Exceso 20d vs SPY |", "|---|---|---|---|---|---|---|---|---|"]
    for (v, w), g in df.groupby(["vol", "bbw"]):
        for name, sub in (("< 2025", g[g.date < bt.SPLIT_DATE]), ("≥ 2025", g[g.date >= bt.SPLIT_DATE])):
            if sub.empty:
                continue
            weeks = max(1, (sub.date.max() - sub.date.min()).days / 7)
            out.append(f"| {v} | {w} | {name} | {len(sub)} | {len(sub) / weeks:.1f} | {sub.ret.mean() * 100:+.2f}% | "
                       f"{(sub.outcome == 'target').mean() * 100:.0f}% | {(sub.outcome == 'stop').mean() * 100:.0f}% | {sub.fx.mean() * 100:+.2f}% |")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    df = run(ap.parse_args().limit)
    print("# Backtest de rupturas\n")
    print("Referencia (backtest_report.md): señal score ≥ 70 = +1,76%/operación con el mismo plan; muestra cualquiera ≈ +0,3-0,6%.\n")
    print(table(df))
    d = df[(df.vol == setups.BREAKOUT_MIN_VOL_RATIO) & (df.bbw == setups.BASE_MAX_BBW_PCT)]
    if not d.empty:
        print("\n## Variante por defecto, por score y volatilidad\n")
        for name, sub in (("score < 50", d[d.score < 50]), ("score 50-69", d[(d.score >= 50) & (d.score < 70)]), ("score ≥ 70", d[d.score >= 70]),
                          ("ATR < 2,5%", d[d.atr_pct < 0.025]), ("ATR ≥ 2,5%", d[d.atr_pct >= 0.025])):
            if len(sub):
                print(f"- {name}: N={len(sub)}, ret. medio {sub.ret.mean() * 100:+.2f}%, objetivo {(sub.outcome == 'target').mean() * 100:.0f}%, exceso {sub.fx.mean() * 100:+.2f}%")
