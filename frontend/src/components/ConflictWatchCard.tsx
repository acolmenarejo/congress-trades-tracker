import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { Trade } from "../lib/api";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict, sectorsForTicker } from "../lib/conflictOfInterest";
import { formatDate } from "../lib/format";

// Scans the loaded trade sample for possible conflicts of interest and
// surfaces them front-and-center — only fetches committees for the (much
// smaller) subset of members who traded a ticker in a tracked sector, to
// keep this cheap.
export default function ConflictWatchCard({ trades }: { trades: Trade[] }) {
  const candidates = useMemo(
    () => trades.filter((t) => t.transaction_type === "purchase" && sectorsForTicker(t.ticker).length > 0),
    [trades],
  );
  const committees = useCommitteesForMembers(candidates.map((t) => t.member_match_key));

  const conflicts = useMemo(() => {
    return candidates
      .map((t) => ({ trade: t, match: detectConflict(t.ticker, committees[t.member_match_key] ?? null) }))
      .filter((c): c is { trade: Trade; match: NonNullable<ReturnType<typeof detectConflict>> } => c.match !== null)
      .slice(0, 10);
  }, [candidates, committees]);

  if (conflicts.length === 0) return null;

  return (
    <div className="rounded-lg border-2 border-red-600 bg-red-600/5 p-4 dark:border-red-500 dark:bg-red-500/10">
      <h3 className="mb-1 font-mono text-sm font-bold uppercase tracking-wide text-red-700 dark:text-red-400">
        ⚠ Posibles conflictos de interés detectados
      </h3>
      <p className="mb-3 text-xs text-ink/60 dark:text-slate-400">
        Compras de miembros con asiento en un comité con competencia sobre el sector de la empresa. Señal
        heurística automática, no una acusación — ver metodología en el Feed.
      </p>
      <ul className="space-y-1.5">
        {conflicts.map(({ trade, match }) => (
          <li key={trade.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              <Link to={`/members/${trade.member_match_key}`} className="font-medium hover:underline">
                {trade.member_name}
              </Link>{" "}
              compró{" "}
              <Link to={`/tickers/${trade.ticker}`} className="font-mono font-medium hover:underline">
                ${trade.ticker}
              </Link>{" "}
              <span className="text-ink/50 dark:text-slate-400">({match.sectors.join(", ")})</span>
            </span>
            <span className="font-mono text-xs text-ink/50 dark:text-slate-400">{formatDate(trade.transaction_date)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
