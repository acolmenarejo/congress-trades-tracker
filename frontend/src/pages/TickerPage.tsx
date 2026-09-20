import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type PricePoint, type TickerSummary } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import CandlestickChart from "../components/charts/CandlestickChart";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import HighValueBadge from "../components/HighValueBadge";
import OptionBadge from "../components/OptionBadge";
import LogDecisionButton from "../components/LogDecisionButton";
import WatchButton from "../components/WatchButton";
import EarningsBadge from "../components/EarningsBadge";
import { SkeletonRows, Skeleton } from "../components/Skeleton";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import { nearestEarningsGapDays } from "../lib/earnings";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const MAX_DAYS = 1825; // backend cap (5 years)

const RANGE_OPTIONS = [
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1A", days: 365 },
  { label: "2A", days: 730 },
];

export default function TickerPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [dark] = useDarkMode();
  const [summary, setSummary] = useState<TickerSummary | null>(null);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [days, setDays] = useState(180);
  const [notFound, setNotFound] = useState(false);
  const [earningsDates, setEarningsDates] = useState<string[]>([]);
  const committees = useCommitteesForMembers((summary?.trades ?? []).map((t) => t.member_match_key));

  useEffect(() => {
    if (!ticker) return;
    api.ticker(ticker).then(setSummary).catch(() => setNotFound(true));
    api.tickerEarnings(ticker).then(setEarningsDates).catch(() => setEarningsDates([]));
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    api.tickerPrices(ticker, days).then(setPrices).catch(() => setPrices([]));
  }, [ticker, days]);

  // How far back the earliest trade goes, so "Todo" can cover every trade
  // this ticker has instead of getting stuck at the 3M/6M/1A/2A presets —
  // those alone silently dropped markers for trades older than 2 years,
  // which read as a bug ("11 trades but way fewer triangles") when it was
  // really just an out-of-range price window.
  const maxTradeDays = useMemo(() => {
    if (!summary || summary.trades.length === 0) return 730;
    const oldest = summary.trades.reduce(
      (min, t) => (t.transaction_date && t.transaction_date < min ? t.transaction_date : min),
      summary.trades[0].transaction_date ?? new Date().toISOString().slice(0, 10),
    );
    const diffDays = Math.ceil((Date.now() - new Date(oldest).getTime()) / 86_400_000);
    return Math.min(Math.max(diffDays + 10, 730), MAX_DAYS);
  }, [summary]);

  const visibleTradeCount = useMemo(() => {
    if (!summary) return 0;
    const cutoff = Date.now() - days * 86_400_000;
    return summary.trades.filter((t) => t.transaction_date && new Date(t.transaction_date).getTime() >= cutoff)
      .length;
  }, [summary, days]);

  if (notFound) {
    return <p className="text-sm text-ink/60 dark:text-slate-400">Sin trades registrados para este ticker.</p>;
  }
  if (!summary) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-64 w-full" />
        <SkeletonRows rows={5} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="flex items-center gap-2 font-serif text-2xl font-semibold">
          <span className="font-mono">${summary.ticker}</span>
          <WatchButton item={{ kind: "ticker", key: summary.ticker, label: summary.ticker }} size="md" />
        </h2>
        <p className="font-mono text-sm text-ink/60 dark:text-slate-400">
          {summary.trade_count} trades · {summary.distinct_members} congresistas ·{" "}
          <span className="text-buy-dim dark:text-buy">{summary.buy_count} compras</span>
          {" / "}
          <span className="text-sell-dim dark:text-sell">{summary.sell_count} ventas</span>
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              type="button"
              onClick={() => setDays(opt.days)}
              className={`rounded-md px-3 py-1 font-mono text-sm ${
                days === opt.days
                  ? "bg-ink text-paper dark:bg-buy dark:text-ledger"
                  : "border border-ink/20 dark:border-slate-100/20"
              }`}
            >
              {opt.label}
            </button>
          ))}
          {maxTradeDays > 730 && (
            <button
              type="button"
              onClick={() => setDays(maxTradeDays)}
              className={`rounded-md px-3 py-1 font-mono text-sm ${
                days === maxTradeDays
                  ? "bg-ink text-paper dark:bg-buy dark:text-ledger"
                  : "border border-ink/20 dark:border-slate-100/20"
              }`}
            >
              Todo
            </button>
          )}
        </div>
        {summary.trade_count > visibleTradeCount && (
          <span className="text-xs text-ink/60 dark:text-slate-400">
            Mostrando {visibleTradeCount} de {summary.trade_count} operaciones en este rango — algunas son más
            antiguas que el histórico de precio cargado.
            {maxTradeDays > days && (
              <>
                {" "}
                <button type="button" onClick={() => setDays(maxTradeDays)} className="underline">
                  Ver todas
                </button>
              </>
            )}
          </span>
        )}
      </div>

      <CandlestickChart prices={prices} trades={summary.trades} dark={dark} />

      <div>
        <h3 className="mb-2 font-serif text-base font-semibold">
          Congresistas que han operado ${summary.ticker}
        </h3>
        <div className="overflow-x-auto rounded-lg border border-ink/10 dark:border-slate-100/10">
          <table className="w-full text-sm">
            <thead className="bg-paper-dim text-left font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:bg-slate-100/[0.03] dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">Miembro</th>
                <th className="px-3 py-2">Tipo</th>
                <th className="px-3 py-2">Importe</th>
                <th className="px-3 py-2">Fecha</th>
                <th className="px-3 py-2">Mío</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/10 dark:divide-slate-100/10">
              {summary.trades.map((t) => {
                const tier = highValueTier(t);
                const gapDays = t.transaction_date ? nearestEarningsGapDays(earningsDates, t.transaction_date) : null;
                return (
                  <tr
                    key={t.id}
                    className={`border-l-[3px] ${tier ? "bg-amber-500/5" : ""}`}
                    style={{ borderLeftColor: partyColor(t.party) }}
                  >
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Link to={`/members/${t.member_match_key}`} className="hover:underline">
                          {t.member_name}
                        </Link>
                        <ConflictBadge match={detectConflict(t.ticker, committees[t.member_match_key] ?? null)} />
                        <HighValueBadge tier={tier} />
                        <EarningsBadge gapDays={gapDays} />
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <TransactionBadge type={t.transaction_type} />
                        <OptionBadge assetType={t.asset_type} />
                      </div>
                    </td>
                    <td className={`tabular-figures px-3 py-2 font-mono ${tier ? "font-bold" : ""}`}>
                      {formatAmountRange(t.amount_range_low, t.amount_range_high)}
                    </td>
                    <td className="px-3 py-2 font-mono text-ink/60 dark:text-slate-400">{formatDate(t.transaction_date)}</td>
                    <td className="px-3 py-2">
                      <LogDecisionButton trade={t} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
