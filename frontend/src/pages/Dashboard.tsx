import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Kpis, type MemberRanking, type Trade } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import KpiCards from "../components/KpiCards";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import ConflictWatchCard from "../components/ConflictWatchCard";
import BigTradesCard from "../components/BigTradesCard";
import SoloMoversCard from "../components/SoloMoversCard";
import HighValueBadge from "../components/HighValueBadge";
import OptionBadge from "../components/OptionBadge";
import WatchlistTeaser from "../components/WatchlistTeaser";
import PolymarketTeaser from "../components/PolymarketTeaser";
import { SkeletonRows, Skeleton } from "../components/Skeleton";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import VolumeByMonthChart from "../components/charts/VolumeByMonthChart";
import TopTickersChart from "../components/charts/TopTickersChart";
import PartySplitChart from "../components/charts/PartySplitChart";
import AssetTypeChart from "../components/charts/AssetTypeChart";
import SectorActivityChart from "../components/charts/SectorActivityChart";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const RECENT_LIMIT = 15;

// Most recent first; same-day ties broken by size (biggest first), then by
// the member's own track record (best total return first) — so on a quiet
// day the top of the list is still the most interesting trade, not just
// whoever's alphabetically/DB-order first.
function sortRecent(trades: Trade[], returnByMember: Map<string, number>): Trade[] {
  return [...trades].sort((a, b) => {
    const dateCmp = (b.transaction_date ?? "").localeCompare(a.transaction_date ?? "");
    if (dateCmp !== 0) return dateCmp;
    const amtCmp = (b.amount_mid ?? 0) - (a.amount_mid ?? 0);
    if (amtCmp !== 0) return amtCmp;
    const ra = returnByMember.get(a.member_match_key) ?? -Infinity;
    const rb = returnByMember.get(b.member_match_key) ?? -Infinity;
    return rb - ra;
  });
}

export default function Dashboard() {
  const [dark] = useDarkMode();
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [recent, setRecent] = useState<Trade[]>([]);
  const [ranking, setRanking] = useState<MemberRanking[]>([]);
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
      .trades({ limit: 30 })
      .then((res) => setRecent(res.items))
      .catch(() => {});
    api.ranking("total_return_pct", 200).then(setRanking).catch(() => {});
  }, []);

  if (error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        {error}. El backend público todavía no está desplegado (ver README) —
        si estás en local, ¿está corriendo en http://127.0.0.1:8000?
      </p>
    );
  }

  const returnByMember = new Map(ranking.map((r) => [r.match_key, r.total_return_pct ?? -Infinity]));
  const recentSorted = sortRecent(recent, returnByMember).slice(0, RECENT_LIMIT);

  return (
    <div className="space-y-6">
      {kpis ? <KpiCards kpis={kpis} /> : <Skeleton className="h-20 w-full" />}

      <div className="rounded-lg border border-ink/10 dark:border-slate-100/10">
        <div className="flex items-center justify-between border-b border-ink/10 p-4 dark:border-slate-100/10">
          <h3 className="font-serif text-base font-semibold">Trades más recientes</h3>
          <Link to="/feed" className="font-mono text-xs uppercase tracking-wide text-buy-dim hover:underline dark:text-buy">
            Ver feed completo →
          </Link>
        </div>
        {recentSorted.length === 0 && <div className="p-3"><SkeletonRows rows={6} /></div>}
        <ul className="divide-y divide-ink/10 dark:divide-slate-100/10">
          {recentSorted.map((t) => {
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
                  <OptionBadge assetType={t.asset_type} />
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
                  <div className="font-normal text-slate-500 dark:text-slate-400">{formatDate(t.transaction_date)}</div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <ConflictWatchCard trades={trades} />

      <SoloMoversCard trades={trades} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <WatchlistTeaser />
        <PolymarketTeaser />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <VolumeByMonthChart trades={trades} dark={dark} />
        <TopTickersChart trades={trades} dark={dark} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PartySplitChart trades={trades} dark={dark} />
        <AssetTypeChart trades={trades} dark={dark} />
      </div>
      <SectorActivityChart trades={trades} dark={dark} />

      <BigTradesCard trades={trades} />
    </div>
  );
}
