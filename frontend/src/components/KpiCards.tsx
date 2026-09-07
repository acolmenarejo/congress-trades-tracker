import type { Kpis } from "../lib/api";
import { formatUSD } from "../lib/format";

export default function KpiCards({ kpis }: { kpis: Kpis }) {
  const items = [
    { label: "Trades registrados", value: kpis.total_trades.toLocaleString("es-ES") },
    { label: "Volumen estimado", value: formatUSD(kpis.total_volume_estimate) },
    { label: "Filers activos", value: kpis.active_filers.toLocaleString("es-ES") },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <p className="text-sm text-slate-500 dark:text-slate-400">{item.label}</p>
          <p className="mt-1 text-2xl font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
