import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Trade } from "../lib/api";
import { useWatchlist } from "../hooks/useWatchlist";
import TransactionBadge from "./TransactionBadge";
import { formatDate } from "../lib/format";

export default function WatchlistTeaser() {
  const { items } = useWatchlist();
  const [trades, setTrades] = useState<Trade[]>([]);

  useEffect(() => {
    if (items.length === 0) {
      setTrades([]);
      return;
    }
    Promise.all(
      items.map((item) =>
        item.kind === "member"
          ? api.memberTrades(item.key, 5).catch(() => [] as Trade[])
          : api.trades({ ticker: item.key, limit: 5 }).then((r) => r.items).catch(() => [] as Trade[]),
      ),
    ).then((lists) => {
      const merged = new Map<number, Trade>();
      for (const list of lists) for (const t of list) merged.set(t.id, t);
      setTrades(
        Array.from(merged.values())
          .sort((a, b) => (b.transaction_date ?? "").localeCompare(a.transaction_date ?? ""))
          .slice(0, 5),
      );
    });
  }, [items]);

  if (items.length === 0) return null;

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-serif text-base font-semibold">★ Tu watchlist</h3>
        <Link to="/watchlist" className="font-mono text-xs uppercase tracking-wide text-buy-dim hover:underline dark:text-buy">
          Ver todo →
        </Link>
      </div>
      {trades.length === 0 ? (
        <p className="text-sm text-ink/60 dark:text-slate-400">Sin actividad reciente en lo que sigues.</p>
      ) : (
        <ul className="space-y-1.5">
          {trades.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
              <div className="flex items-center gap-1.5">
                <Link to={`/members/${t.member_match_key}`} className="hover:underline">
                  {t.member_name}
                </Link>
                <TransactionBadge type={t.transaction_type} />
                <Link to={`/tickers/${t.ticker}`} className="font-mono hover:underline">
                  ${t.ticker}
                </Link>
              </div>
              <span className="font-mono text-xs text-ink/50 dark:text-slate-400">{formatDate(t.transaction_date)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
