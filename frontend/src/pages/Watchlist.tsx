import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Trade } from "../lib/api";
import { useWatchlist } from "../hooks/useWatchlist";
import WatchButton from "../components/WatchButton";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import HighValueBadge from "../components/HighValueBadge";
import { SkeletonRows } from "../components/Skeleton";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

export default function Watchlist() {
  const { items } = useWatchlist();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(false);
  const committees = useCommitteesForMembers(trades.map((t) => t.member_match_key));

  useEffect(() => {
    if (items.length === 0) {
      setTrades([]);
      return;
    }
    setLoading(true);
    Promise.all(
      items.map((item) =>
        item.kind === "member"
          ? api.memberTrades(item.key, 25).catch(() => [] as Trade[])
          : api.trades({ ticker: item.key, limit: 25 }).then((r) => r.items).catch(() => [] as Trade[]),
      ),
    )
      .then((lists) => {
        const merged = new Map<number, Trade>();
        for (const list of lists) for (const t of list) merged.set(t.id, t);
        const sorted = Array.from(merged.values()).sort((a, b) =>
          (b.transaction_date ?? "").localeCompare(a.transaction_date ?? ""),
        );
        setTrades(sorted);
      })
      .finally(() => setLoading(false));
  }, [items]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Mi watchlist</h2>
        <p className="mt-1 text-sm text-ink/60 dark:text-slate-400">
          Congresistas y tickers marcados con ★ en cualquier parte de la app. Se guarda solo en este
          navegador.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Todavía no sigues a nadie. Pulsa el ☆ junto al nombre de un congresista o de un ticker
          para añadirlo aquí.
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <div
              key={`${item.kind}:${item.key}`}
              className="flex items-center gap-1.5 rounded-full border border-ink/15 bg-paper-dim px-3 py-1 text-sm dark:border-slate-100/15 dark:bg-slate-100/5"
            >
              <Link
                to={item.kind === "member" ? `/members/${item.key}` : `/tickers/${item.key}`}
                className="hover:underline"
              >
                {item.kind === "ticker" ? `$${item.label}` : item.label}
              </Link>
              <WatchButton item={item} />
            </div>
          ))}
        </div>
      )}

      {items.length > 0 && (
        <div>
          <h3 className="mb-2 font-serif text-base font-semibold">Actividad reciente</h3>
          {loading && <SkeletonRows rows={6} />}
          {!loading && trades.length === 0 && (
            <p className="text-sm text-ink/60 dark:text-slate-400">Sin trades recientes para lo que sigues.</p>
          )}
          {!loading && trades.length > 0 && (
            <ul className="divide-y divide-ink/10 rounded-lg border border-ink/10 dark:divide-slate-100/10 dark:border-slate-100/10">
              {trades.map((t) => {
                const tier = highValueTier(t);
                return (
                  <li
                    key={t.id}
                    className={`flex flex-wrap items-center justify-between gap-2 border-l-[3px] p-3 text-sm ${
                      tier ? "bg-amber-500/5" : ""
                    }`}
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
                      <ConflictBadge match={detectConflict(t.ticker, committees[t.member_match_key] ?? null)} />
                      <HighValueBadge tier={tier} />
                    </div>
                    <div className="tabular-figures text-right font-mono text-xs text-ink/60 dark:text-slate-400">
                      {formatAmountRange(t.amount_range_low, t.amount_range_high)} · {formatDate(t.transaction_date)}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
