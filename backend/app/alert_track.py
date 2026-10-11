"""Live accuracy of the alerts that claim to know something (Polymarket bets,
Kalshi moves, insider buys). Each is recorded when stored/sent, and settled
later: prediction markets when they resolve, insider buys by their return
after 30/90 days against SPY. `summary_lines` compares results with what the
price implied (a 20¢ bet should win 20% of the time; only more is an edge).
Nothing here changes what gets alerted: it only measures."""
import json
import logging
from datetime import date, datetime, timedelta

import requests
from sqlalchemy.orm import Session

from .models import AlertOutcome

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
MIN_SAMPLE = 20  # fewer settled alerts than this say nothing


def record(db: Session, ref: str, source: str, price0: float | None, title: str = "", ticker: str | None = None,
           direction: str | None = None, score: float | None = None, alerted: bool = False) -> None:
    """Idempotent: a repeat only upgrades `alerted`."""
    if price0 is None:
        return
    row = db.get(AlertOutcome, ref)
    if row:
        row.alerted = row.alerted or alerted
        return
    db.add(AlertOutcome(ref=ref, source=source, title=(title or "")[:200], ticker=ticker, direction=direction,
                        score=score, price0=price0, created=date.today(), alerted=alerted, status="open"))


def backfill_polymarket(db: Session) -> None:
    """Bets stored before tracking existed (idempotent)."""
    from .models import PolymarketAlert

    for a in db.query(PolymarketAlert).filter(PolymarketAlert.score.isnot(None)).all():
        if db.get(AlertOutcome, a.tx_hash) is None and a.tx_hash.startswith("pos:"):
            record(db, a.tx_hash, "polymarket", a.price, a.market_question, score=a.score, alerted=bool(a.notified))
            db.flush()
            row = db.get(AlertOutcome, a.tx_hash)
            if row and a.detected_at:
                row.created = a.detected_at.date()


def mark_alerted(db: Session, ref: str) -> None:
    row = db.get(AlertOutcome, ref)
    if row:
        row.alerted = True


def _polymarket_result(ref: str) -> str | None:
    """'win' | 'lose' | None (still open). ref = pos:wallet:conditionId:outcomeIndex."""
    try:
        _, _, cid, oidx = ref.split(":")
        r = requests.get(f"{GAMMA}/markets", params={"condition_ids": cid}, timeout=20)
        r.raise_for_status()
        m = (r.json() or [None])[0]
        if not m or not m.get("closed"):
            return None
        p = float(json.loads(m["outcomePrices"])[int(oidx)])
    except Exception:
        return None
    return "win" if p >= 0.99 else "lose" if p <= 0.01 else None


def _kalshi_result(ticker: str, direction: str) -> str | None:
    from .polymarket_macro import KALSHI

    try:
        r = requests.get(f"{KALSHI}/markets/{ticker}", timeout=20)
        r.raise_for_status()
        res = (r.json().get("market") or {}).get("result")
    except Exception:
        return None
    if res not in ("yes", "no"):
        return None
    return "win" if res == direction else "lose"


def _insider_returns(db: Session, row: AlertOutcome) -> None:
    from .prices import get_price_series, price_on_or_after

    for days, ret, bench in ((30, "ret30", "bench30"), (90, "ret90", "bench90")):
        end = row.created + timedelta(days=days)
        if getattr(row, ret) is not None or end > date.today() - timedelta(days=3):
            continue
        out = {}
        for t in (row.ticker, "SPY"):
            ser = get_price_series(db, t, row.created - timedelta(days=5), end + timedelta(days=5))
            out[t] = (price_on_or_after(ser, row.created), price_on_or_after(ser, end))
        (a0, a1), (b0, b1) = out[row.ticker], out["SPY"]
        if all((a0, a1, b0, b1)):
            setattr(row, ret, a1 / a0 - 1)
            setattr(row, bench, b1 / b0 - 1)
    if row.ret90 is not None:
        row.status = "done"


def settle(db: Session, sources: tuple[str, ...]) -> int:
    """Settle open rows of `sources`; returns how many changed."""
    n = 0
    for row in db.query(AlertOutcome).filter(AlertOutcome.source.in_(sources), AlertOutcome.status == "open").all():
        before = (row.status, row.ret30, row.ret90)
        if row.source == "polymarket":
            row.status = _polymarket_result(row.ref) or "open"
        elif row.source == "kalshi":
            row.status = _kalshi_result(row.ticker, row.direction) or "open"
        elif row.source in ("insider", "edgar_flag"):
            try:
                _insider_returns(db, row)
            except Exception:
                logger.exception("alert_track: returns for %s failed", row.ref)
        if before != (row.status, row.ret30, row.ret90):
            row.updated = datetime.utcnow()
            n += 1
    db.commit()
    return n


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def summary_lines(db: Session) -> list[str]:
    """Daily-digest block; empty until there is something settled."""
    rows = db.query(AlertOutcome).all()
    out = []
    for src, name in (("polymarket", "Polymarket"), ("kalshi", "Kalshi")):
        done = [r for r in rows if r.source == src and r.status in ("win", "lose")]
        if not done:
            continue
        wins = sum(r.status == "win" for r in done)
        # Expected wins if the price were right: the sum of entry prices
        # (Kalshi: the probability of the side the alert points to).
        exp = sum(r.price0 if src == "polymarket" else (r.price0 if r.direction == "yes" else 1 - r.price0) for r in done)
        note = "" if len(done) >= MIN_SAMPLE else f" · muestra pequeña (se concluye con ≥{MIN_SAMPLE})"
        out.append(f"  • {name}: {wins}/{len(done)} acertadas, el precio implicaba {exp:.1f}{note}")
    groups = (("insider", "Directivos", None), ("insider", "Directivos atípicos", "opportunistic"),
              ("insider", "Directivos de rutina", "routine"), ("edgar_flag", "Alarmas EDGAR (si baja, acierta)", None))
    for src, name, pat in groups:
        sel = [r for r in rows if r.source == src and r.ret30 is not None and r.bench30 is not None
               and (pat is None or r.direction == pat)]
        if sel:
            ex = [r.ret30 - r.bench30 for r in sel]
            note = "" if len(sel) >= MIN_SAMPLE else f" · muestra pequeña (se concluye con ≥{MIN_SAMPLE})"
            out.append(f"  • {name} a 30 días: {_pct(sum(ex) / len(ex))} de media sobre el S&P ({len(sel)} casos){note}")
    return (["📏 <b>Acierto real de los avisos</b>"] + out) if out else []
