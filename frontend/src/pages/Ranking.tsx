import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type MemberRanking } from "../lib/api";
import { formatPct, formatUSD, partyColor } from "../lib/format";
import { SkeletonRows } from "../components/Skeleton";
import Avatar from "../components/Avatar";

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "total_return_pct", label: "Retorno total" },
  { value: "annualized_return_pct", label: "Retorno anualizado" },
  { value: "alpha_vs_sp500_pct", label: "Alpha vs S&P 500" },
  { value: "volume_estimate", label: "Volumen operado" },
  { value: "trade_count", label: "Nº de trades" },
  { value: "win_rate_pct", label: "Ratio de aciertos" },
  { value: "avg_disclosure_lag_days", label: "⚠️ Peor cumplimiento (retraso disclosure)" },
];

export default function Ranking() {
  const [sortBy, setSortBy] = useState("total_return_pct");
  const [rows, setRows] = useState<MemberRanking[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .ranking(sortBy)
      .then(setRows)
      .finally(() => setLoading(false));
  }, [sortBy]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-2xl font-semibold">Ranking de traders del Congreso</h2>
        <select
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
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
      <p className="max-w-2xl text-xs text-ink/50 dark:text-slate-400">
        El rendimiento se calcula solo sobre trades de los últimos 2 años — un miembro con
        historial más antiguo puede mostrar pocos trades aquí aunque tenga muchos más en su
        timeline completo (ver su página de perfil).
      </p>

      {loading && <SkeletonRows rows={8} />}

      {!loading && rows.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Todavía no hay métricas de rendimiento calculadas (Fase 3, pendiente:
          cálculo diario de retorno estimado vía yfinance). Esta tabla se
          rellenará sola en cuanto ese job corra.
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-ink/10 dark:border-slate-100/10">
          <table className="w-full text-sm">
            <thead className="bg-paper-dim text-left font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:bg-slate-100/[0.03] dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">Miembro</th>
                <th className="px-3 py-2" title="Solo trades de los últimos 2 años — ventana usada para calcular el rendimiento">
                  Trades (2A)
                </th>
                <th className="px-3 py-2">Volumen</th>
                <th className="px-3 py-2">Retorno total</th>
                <th className="px-3 py-2">Anualizado</th>
                <th className="px-3 py-2">Alpha vs S&P 500</th>
                <th className="px-3 py-2">Aciertos</th>
                <th className="px-3 py-2">Retraso disclosure</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink/10 dark:divide-slate-100/10">
              {rows.map((r) => (
                <tr key={r.match_key} className="border-l-[3px]" style={{ borderLeftColor: partyColor(r.party) }}>
                  <td className="px-3 py-2">
                    <Link to={`/members/${r.match_key}`} className="flex items-center gap-2 hover:underline">
                      <Avatar photoUrl={r.photo_url} name={r.name} size={28} />
                      {r.name}
                    </Link>
                  </td>
                  <td className="tabular-figures px-3 py-2 font-mono">{r.trade_count}</td>
                  <td className="tabular-figures px-3 py-2 font-mono">{formatUSD(r.volume_estimate)}</td>
                  <td
                    className={`tabular-figures px-3 py-2 font-mono ${
                      (r.total_return_pct ?? 0) >= 0 ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
                    }`}
                  >
                    {formatPct(r.total_return_pct)}
                  </td>
                  <td className="tabular-figures px-3 py-2 font-mono">{formatPct(r.annualized_return_pct)}</td>
                  <td className="tabular-figures px-3 py-2 font-mono">{formatPct(r.alpha_vs_sp500_pct)}</td>
                  <td className="tabular-figures px-3 py-2 font-mono">{formatPct(r.win_rate_pct)}</td>
                  <td
                    className={`tabular-figures px-3 py-2 font-mono ${
                      r.avg_disclosure_lag_days !== null && r.avg_disclosure_lag_days > 45
                        ? "font-medium text-sell-dim dark:text-sell"
                        : ""
                    }`}
                    title={
                      r.avg_disclosure_lag_days !== null && r.avg_disclosure_lag_days > 45
                        ? "Por encima del límite legal de 45 días de la Ley STOCK"
                        : undefined
                    }
                  >
                    {r.avg_disclosure_lag_days !== null ? `${r.avg_disclosure_lag_days.toFixed(0)}d` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
