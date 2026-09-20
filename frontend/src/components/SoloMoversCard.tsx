import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { Trade } from "../lib/api";
import OptionBadge from "./OptionBadge";
import { formatAmountRange, formatDate } from "../lib/format";

// A ticker only one member has touched in the loaded sample is a different
// kind of signal than one 15 members bought at once (which usually just
// means "popular large-cap", correlated, not much information in any one
// of those trades). This surfaces the opposite: someone moving alone.
export default function SoloMoversCard({ trades }: { trades: Trade[] }) {
  const solo = useMemo(() => {
    const byTicker = new Map<string, Set<string>>();
    for (const t of trades) {
      if (!t.ticker) continue;
      const set = byTicker.get(t.ticker) ?? new Set();
      set.add(t.member_match_key);
      byTicker.set(t.ticker, set);
    }
    const soloTickers = new Set(
      Array.from(byTicker.entries())
        .filter(([, members]) => members.size === 1)
        .map(([ticker]) => ticker),
    );
    return trades
      .filter((t) => t.ticker && soloTickers.has(t.ticker) && t.transaction_type === "purchase")
      .sort((a, b) => (b.transaction_date ?? "").localeCompare(a.transaction_date ?? ""))
      .slice(0, 8);
  }, [trades]);

  if (solo.length === 0) return null;

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <h3 className="mb-1 font-serif text-base font-semibold">🔍 Movimientos en solitario</h3>
      <p className="mb-3 text-xs text-ink/50 dark:text-slate-400">
        Compras en tickers que, en la muestra cargada, solo ha tocado ese congresista — menos "efecto
        rebaño" (large-cap popular) que cuando compran 15 a la vez.
      </p>
      <ul className="space-y-1.5">
        {solo.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <div className="flex items-center gap-1.5">
              <Link to={`/members/${t.member_match_key}`} className="font-medium hover:underline">
                {t.member_name}
              </Link>
              <Link to={`/tickers/${t.ticker}`} className="font-mono hover:underline">
                ${t.ticker}
              </Link>
              <OptionBadge assetType={t.asset_type} />
            </div>
            <span className="font-mono text-xs text-ink/50 dark:text-slate-400">
              {formatAmountRange(t.amount_range_low, t.amount_range_high)} · {formatDate(t.transaction_date)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
