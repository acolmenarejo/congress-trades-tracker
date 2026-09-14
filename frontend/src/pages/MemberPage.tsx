import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Member, type MemberBestTrade, type Trade } from "../lib/api";
import { formatAmountRange, formatDate, formatPct, formatUSD } from "../lib/format";

const CHAMBER_LABEL: Record<string, string> = { house: "Cámara de Representantes", senate: "Senado" };
const PARTY_LABEL: Record<string, string> = { D: "Demócrata", R: "Republicano", I: "Independiente" };

function MemberPhoto({ member }: { member: Member }) {
  const [failed, setFailed] = useState(false);
  const initial = member.name.charAt(0).toUpperCase();

  if (!member.photo_url || failed) {
    return (
      <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full bg-slate-200 text-3xl font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        {initial}
      </div>
    );
  }
  return (
    <img
      src={member.photo_url}
      alt={member.name}
      onError={() => setFailed(true)}
      className="h-24 w-24 shrink-0 rounded-full object-cover"
    />
  );
}

function BestTradeRow({ trade }: { trade: MemberBestTrade }) {
  const isPositive = trade.return_pct >= 0;
  return (
    <li className="flex items-center justify-between p-3 text-sm">
      <div>
        <span className="font-medium">
          {trade.transaction_type === "purchase" ? "Compró" : "Vendió"}{" "}
          <Link to={`/tickers/${trade.ticker}`} className="hover:underline">
            ${trade.ticker}
          </Link>
        </span>
        {trade.asset_name && <span className="text-slate-500 dark:text-slate-400"> — {trade.asset_name}</span>}
        <div className="text-slate-500 dark:text-slate-400">
          {formatAmountRange(trade.amount_range_low, trade.amount_range_high)} · {formatDate(trade.transaction_date)}
          {!trade.closed && " · aún en cartera"}
        </div>
      </div>
      <div
        className={`text-right font-semibold ${
          isPositive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
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
    return <p className="text-sm text-slate-500">No se encontró a este miembro.</p>;
  }
  if (!member) {
    return <p className="text-sm text-slate-500">Cargando…</p>;
  }

  const committeeList = member.committees ? member.committees.split(", ") : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <MemberPhoto member={member} />
        <div>
          <h2 className="text-2xl font-semibold">{member.name}</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
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
                  className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
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
              className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <p className="text-xs text-slate-500 dark:text-slate-400">{item.label}</p>
              <p className="mt-1 text-lg font-semibold">{item.value}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          Sin retorno estimado calculable todavía (pocos trades cerrados en los últimos 2 años, o
          el cálculo diario aún no ha corrido para este miembro).
        </div>
      )}

      {bestTrades.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Mejores trades</h3>
          <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {bestTrades.map((t, i) => (
              <BestTradeRow key={i} trade={t} />
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Gráfico de rendimiento simulado (comparado con S&P 500) — pendiente,
        backlog: simulador "qué hubiera pasado si copio a X".
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Timeline de operaciones ({trades.length})
        </h3>
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {trades.map((t) => (
            <li key={t.id} className="flex items-center justify-between p-3 text-sm">
              <div>
                <span className="font-medium">
                  {t.transaction_type === "purchase" ? "Compró" : "Vendió"}{" "}
                  <Link to={`/tickers/${t.ticker}`} className="hover:underline">
                    ${t.ticker}
                  </Link>
                </span>
                {t.asset_name && (
                  <span className="text-slate-500 dark:text-slate-400"> — {t.asset_name}</span>
                )}
              </div>
              <div className="text-right text-slate-500 dark:text-slate-400">
                <div>{formatAmountRange(t.amount_range_low, t.amount_range_high)}</div>
                <div>{formatDate(t.transaction_date)}</div>
              </div>
            </li>
          ))}
          {trades.length === 0 && (
            <li className="p-3 text-sm text-slate-500">Sin trades registrados todavía.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
