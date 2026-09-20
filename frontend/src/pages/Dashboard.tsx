import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Kpis, type Trade } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import KpiCards from "../components/KpiCards";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import ConflictWatchCard from "../components/ConflictWatchCard";
import BigTradesCard from "../components/BigTradesCard";
import HighValueBadge from "../components/HighValueBadge";
import { SkeletonRows, Skeleton } from "../components/Skeleton";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import VolumeByMonthChart from "../components/charts/VolumeByMonthChart";
import TopTickersChart from "../components/charts/TopTickersChart";
import PartySplitChart from "../components/charts/PartySplitChart";
import AssetTypeChart from "../components/charts/AssetTypeChart";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

export default function Dashboard() {
  const [dark] = useDarkMode();
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [recent, setRecent] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const recentCommittees = useCommitteesForMembers(recent.map((t) => t.member_match_key));

  useEffect(() => {
    api.kpis().then(setKpis).catch(() => setError("No se pudo conectar con la API"));
    // A larger sample for the charts below; the feed page has full filtering/pagination.
    api
      .trades({ limit: 500 })
      .then((res) => setTrades(res.items))
      .catch(() => setError("No se pudo conectar con la API"));
    api
      .trades({ limit: 8 })
      .then((res) => setRecent(res.items))
      .catch(() => {});
  }, []);

  if (error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        {error}. El backend público todavía no está desplegado (ver README) —
        si estás en local, ¿está corriendo en http://127.0.0.1:8000?
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {kpis ? <KpiCards kpis={kpis} /> : <Skeleton className="h-20 w-full" />}

      <BigTradesCard trades={trades} />

      <ConflictWatchCard trades={trades} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <VolumeByMonthChart trades={trades} dark={dark} />
        <TopTickersChart trades={trades} dark={dark} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PartySplitChart trades={trades} dark={dark} />
        <AssetTypeChart trades={trades} dark={dark} />
      </div>

      <div className="rounded-lg border border-ink/10 dark:border-slate-100/10">
        <div className="flex items-center justify-between border-b border-ink/10 p-4 dark:border-slate-100/10">
          <h3 className="font-serif text-base font-semibold">Últimas transacciones</h3>
          <Link to="/feed" className="font-mono text-xs uppercase tracking-wide text-buy-dim hover:underline dark:text-buy">
            Ver feed completo →
          </Link>
        </div>
        {recent.length === 0 && <div className="p-3"><SkeletonRows rows={4} /></div>}
        <ul className="divide-y divide-ink/10 dark:divide-slate-100/10">
          {recent.map((t) => {
            const tier = highValueTier(t);
            return (
              <li
                key={t.id}
                className={`flex items-center justify-between gap-3 border-l-[3px] p-3 text-sm ${
                  tier ? "bg-amber-500/5" : ""
                }`}
                style={{ borderLeftColor: partyColor(t.party) }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/members/${t.member_match_key}`} className="font-medium hover:underline">
                    {t.member_name}
                  </Link>
                  <TransactionBadge type={t.transaction_type} />
                  <span className="font-mono text-slate-500 dark:text-slate-400">${t.ticker}</span>
                  <ConflictBadge match={detectConflict(t.ticker, recentCommittees[t.member_match_key] ?? null)} />
                  <HighValueBadge tier={tier} />
                </div>
                <div
                  className={`tabular-figures text-right font-mono ${
                    tier ? "font-bold text-ink dark:text-slate-100" : "text-slate-500 dark:text-slate-400"
                  }`}
                >
                  <div>{formatAmountRange(t.amount_range_low, t.amount_range_high)}</div>
                  <div className="font-normal text-slate-500 dark:text-slate-400">{formatDate(t.disclosure_date)}</div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
