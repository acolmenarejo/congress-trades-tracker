import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Member, type Trade } from "../lib/api";
import { formatAmountRange, formatDate } from "../lib/format";

const CHAMBER_LABEL: Record<string, string> = { house: "Cámara de Representantes", senate: "Senado" };
const PARTY_LABEL: Record<string, string> = { D: "Demócrata", R: "Republicano", I: "Independiente" };

export default function MemberPage() {
  const { matchKey } = useParams<{ matchKey: string }>();
  const [member, setMember] = useState<Member | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!matchKey) return;
    api.member(matchKey).then(setMember).catch(() => setNotFound(true));
    api.memberTrades(matchKey).then(setTrades).catch(() => {});
  }, [matchKey]);

  if (notFound) {
    return <p className="text-sm text-slate-500">No se encontró a este miembro.</p>;
  }
  if (!member) {
    return <p className="text-sm text-slate-500">Cargando…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{member.name}</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {CHAMBER_LABEL[member.chamber ?? ""] ?? "—"}
          {member.party ? ` · ${PARTY_LABEL[member.party] ?? member.party}` : ""}
          {member.state ? ` · ${member.state}` : ""}
          {member.district ? ` (${member.district})` : ""}
        </p>
      </div>

      <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Gráfico de rendimiento simulado (comparado con S&P 500) pendiente de
        Fase 3 — necesita el cálculo de retorno estimado por trade vía yfinance.
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
