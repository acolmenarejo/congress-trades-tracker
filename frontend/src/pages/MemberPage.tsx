import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Member, type MemberBestTrade, type Trade } from "../lib/api";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import HighValueBadge from "../components/HighValueBadge";
import OptionBadge from "../components/OptionBadge";
import Avatar from "../components/Avatar";
import WatchButton from "../components/WatchButton";
import CopySimulator from "../components/CopySimulator";
import { SkeletonRows, Skeleton } from "../components/Skeleton";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import { formatAmountRange, formatDate, formatPct, formatUSD, partyColor } from "../lib/format";

const CHAMBER_LABEL: Record<string, string> = { house: "Cámara de Representantes", senate: "Senado" };
const PARTY_LABEL: Record<string, string> = { D: "Demócrata", R: "Republicano", I: "Independiente" };

function BestTradeRow({ trade, committees }: { trade: MemberBestTrade; committees: string | null }) {
  const isPositive = trade.return_pct >= 0;
  const conflict = detectConflict(trade.ticker, committees);
  return (
    <li className="flex items-center justify-between p-3 text-sm">
      <div>
        <span className="flex flex-wrap items-center gap-2 font-medium">
          <TransactionBadge type={trade.transaction_type} />
          <Link to={`/tickers/${trade.ticker}`} className="font-mono hover:underline">
            ${trade.ticker}
          </Link>
          <ConflictBadge match={conflict} />
        </span>
        {trade.asset_name && <span className="text-ink/60 dark:text-slate-400"> — {trade.asset_name}</span>}
        <div className="font-mono text-xs text-ink/60 dark:text-slate-400">
          {formatAmountRange(trade.amount_range_low, trade.amount_range_high)} · {formatDate(trade.transaction_date)}
          {!trade.closed && " · aún en cartera"}
        </div>
      </div>
      <div
        className={`tabular-figures text-right font-mono font-semibold ${
          isPositive ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
        }`}
      >
        {formatPct(trade.return_pct)}
      </div>
    </li>
  );
}

export default function MemberPage() {
  const { matchKey } = useParams<{ matchKey: string }>();
  const [member, setMember] = useState<Member | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [bestTrades, setBestTrades] = useState<MemberBestTrade[]>([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!matchKey) return;
    api.member(matchKey).then(setMember).catch(() => setNotFound(true));
    api.memberTrades(matchKey).then(setTrades).catch(() => {});
    api.memberBestTrades(matchKey, 5).then(setBestTrades).catch(() => {});
  }, [matchKey]);

  if (notFound) {
    return <p className="text-sm text-ink/60 dark:text-slate-400">No se encontró a este miembro.</p>;
  }
  if (!member) {
    return (
      <div className="space-y-6">
        <div className="flex items-start gap-4">
          <Skeleton className="h-24 w-24 shrink-0 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
        <SkeletonRows rows={5} />
      </div>
    );
  }

  const committeeList = member.committees ? member.committees.split(", ") : [];

  return (
    <div className="space-y-6">
      <div
        className="flex items-start gap-4 border-l-[3px] pl-4"
        style={{ borderLeftColor: partyColor(member.party) }}
      >
        <Avatar photoUrl={member.photo_url} name={member.name} size={96} />
        <div>
          <h2 className="flex items-center gap-2 font-serif text-2xl font-semibold">
            {member.name}
            <WatchButton item={{ kind: "member", key: member.match_key, label: member.name }} size="md" />
          </h2>
          <p className="text-sm text-ink/60 dark:text-slate-400">
            {CHAMBER_LABEL[member.chamber ?? ""] ?? "—"}
            {member.party ? ` · ${PARTY_LABEL[member.party] ?? member.party}` : ""}
            {member.state ? ` · ${member.state}` : ""}
            {member.district ? ` (${member.district})` : ""}
          </p>
          {committeeList.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {committeeList.map((c) => (
                <span
                  key={c}
                  className="rounded-full bg-ink/5 px-2.5 py-0.5 font-mono text-xs text-ink/70 dark:bg-slate-100/10 dark:text-slate-300"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {member.ranking ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {[
            { label: "Trades (2A)", value: member.ranking.trade_count.toLocaleString("es-ES") },
            { label: "Volumen", value: formatUSD(member.ranking.volume_estimate) },
            { label: "Retorno total", value: formatPct(member.ranking.total_return_pct) },
            { label: "Alpha vs S&P 500", value: formatPct(member.ranking.alpha_vs_sp500_pct) },
            { label: "Aciertos", value: formatPct(member.ranking.win_rate_pct) },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-lg border border-ink/10 bg-paper-dim p-3 dark:border-slate-100/10 dark:bg-slate-100/[0.03]"
            >
              <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                {item.label}
              </p>
              <p className="tabular-figures mt-1 font-mono text-lg font-semibold">{item.value}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-ink/20 p-4 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Sin retorno estimado calculable todavía (pocos trades cerrados en los últimos 2 años, o
          el cálculo diario aún no ha corrido para este miembro).
        </div>
      )}

      {bestTrades.length > 0 && (
        <div>
          <h3 className="mb-2 font-serif text-base font-semibold">Mejores trades</h3>
          <ul className="divide-y divide-ink/10 rounded-lg border border-ink/10 dark:divide-slate-100/10 dark:border-slate-100/10">
            {bestTrades.map((t, i) => (
              <BestTradeRow key={i} trade={t} committees={member.committees} />
            ))}
          </ul>
        </div>
      )}

      <CopySimulator trades={trades} memberName={member.name} />

      <div>
        <h3 className="mb-2 font-serif text-base font-semibold">
          Timeline de operaciones ({trades.length})
        </h3>
        <ul className="divide-y divide-ink/10 rounded-lg border border-ink/10 dark:divide-slate-100/10 dark:border-slate-100/10">
          {trades.map((t) => {
            const tier = highValueTier(t);
            return (
              <li key={t.id} className={`flex items-center justify-between p-3 text-sm ${tier ? "bg-amber-500/5" : ""}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <TransactionBadge type={t.transaction_type} />
                  <OptionBadge assetType={t.asset_type} />
                  <Link to={`/tickers/${t.ticker}`} className="font-mono font-medium hover:underline">
                    ${t.ticker}
                  </Link>
                  <ConflictBadge match={detectConflict(t.ticker, member.committees)} />
                  <HighValueBadge tier={tier} />
                  {t.asset_name && (
                    <span className="text-ink/60 dark:text-slate-400"> — {t.asset_name}</span>
                  )}
                </div>
                <div
                  className={`tabular-figures text-right font-mono ${
                    tier ? "font-bold text-ink dark:text-slate-100" : "text-ink/60 dark:text-slate-400"
                  }`}
                >
                  <div>{formatAmountRange(t.amount_range_low, t.amount_range_high)}</div>
                  <div className="font-normal text-ink/60 dark:text-slate-400">{formatDate(t.transaction_date)}</div>
                </div>
              </li>
            );
          })}
          {trades.length === 0 && (
            <li className="p-3 text-sm text-ink/60 dark:text-slate-400">Sin trades registrados todavía.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
