import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { Trade } from "../lib/api";
import HighValueBadge from "./HighValueBadge";
import TransactionBadge from "./TransactionBadge";
import { highValueTier, tradeValue } from "../lib/highValue";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const RECENT_WINDOW_DAYS = 90;

export default function BigTradesCard({ trades }: { trades: Trade[] }) {
  const big = useMemo(() => {
    const cutoff = Date.now() - RECENT_WINDOW_DAYS * 86_400_000;
    return trades
      .filter((t) => highValueTier(t) !== null)
      .filter((t) => t.transaction_date && new Date(t.transaction_date).getTime() >= cutoff)
      .sort((a, b) => tradeValue(b) - tradeValue(a))
      .slice(0, 8);
  }, [trades]);

  if (big.length === 0) return null;

  return (
    <div className="rounded-lg border-2 border-amber-500 bg-amber-500/5 p-4 dark:bg-amber-500/10">
      <h3 className="mb-1 font-serif text-base font-semibold">💰 Grandes operaciones</h3>
      <p className="mb-3 text-xs text-ink/50 dark:text-slate-400">
        Últimos {RECENT_WINDOW_DAYS} días por fecha de operación — no cuenta trades antiguos que
        simplemente se declararon tarde.
      </p>
      <ul className="space-y-2">
        {big.map((t) => (
          <li
            key={t.id}
            className="flex flex-wrap items-center justify-between gap-2 border-l-[3px] py-1 pl-3 text-sm"
            style={{ borderLeftColor: partyColor(t.party) }}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <Link to={`/members/${t.member_match_key}`} className="font-medium hover:underline">
                {t.member_name}
              </Link>
              <TransactionBadge type={t.transaction_type} />
              <Link to={`/tickers/${t.ticker}`} className="font-mono hover:underline">
                ${t.ticker}
              </Link>
              <HighValueBadge tier={highValueTier(t)} />
            </div>
            <div className="tabular-figures text-right font-mono text-xs text-ink/60 dark:text-slate-400">
              <span className="font-bold text-ink dark:text-slate-100">
                {formatAmountRange(t.amount_range_low, t.amount_range_high)}
              </span>{" "}
              · {formatDate(t.transaction_date)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
