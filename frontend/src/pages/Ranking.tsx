import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type MemberRanking } from "../lib/api";
import { formatPct, formatUSD, partyColor } from "../lib/format";

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "total_return_pct", label: "Retorno total" },
  { value: "annualized_return_pct", label: "Retorno anualizado" },
  { value: "alpha_vs_sp500_pct", label: "Alpha vs S&P 500" },
  { value: "volume_estimate", label: "Volumen operado" },
  { value: "trade_count", label: "Nº de trades" },
  { value: "win_rate_pct", label: "Ratio de aciertos" },
];

export default function Ranking() {
  const [sortBy, setSortBy] = useState("total_return_pct");
  const [rows, setRows] = useState<MemberRanking[]>([]);

  useEffect(() => {
    api.ranking(sortBy).then(setRows);
  }, [sortBy]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Ranking de traders del Congreso</h2>
        <select
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              Ordenar por: {o.label}
            </option>
          ))}
        </select>
      </div>

      {rows.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          Todavía no hay métricas de rendimiento calculadas (Fase 3, pendiente:
          cálculo diario de retorno estimado vía yfinance). Esta tabla se
          rellenará sola en cuanto ese job corra.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">Miembro</th>
                <th className="px-3 py-2">Trades</th>
                <th className="px-3 py-2">Volumen</th>
                <th className="px-3 py-2">Retorno total</th>
                <th className="px-3 py-2">Anualizado</th>
                <th className="px-3 py-2">Alpha vs S&P 500</th>
                <th className="px-3 py-2">Aciertos</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {rows.map((r) => (
                <tr key={r.match_key}>
                  <td className="px-3 py-2">
                    <Link to={`/members/${r.match_key}`} className="hover:underline">
                      <span
                        className="mr-1.5 inline-block h-2 w-2 rounded-full"
                        style={{ background: partyColor(r.party) }}
                      />
                      {r.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{r.trade_count}</td>
                  <td className="px-3 py-2">{formatUSD(r.volume_estimate)}</td>
                  <td className="px-3 py-2">{formatPct(r.total_return_pct)}</td>
                  <td className="px-3 py-2">{formatPct(r.annualized_return_pct)}</td>
                  <td className="px-3 py-2">{formatPct(r.alpha_vs_sp500_pct)}</td>
                  <td className="px-3 py-2">{formatPct(r.win_rate_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
