import type { Kpis } from "../lib/api";
import { formatUSD } from "../lib/format";

export default function KpiCards({ kpis }: { kpis: Kpis }) {
  const items = [
    { label: "Trades registrados", value: kpis.total_trades.toLocaleString("es-ES") },
    { label: "Volumen estimado", value: formatUSD(kpis.total_volume_estimate) },
    { label: "Filers activos", value: kpis.active_filers.toLocaleString("es-ES") },
  ];

  return (
    <div className="grid grid-cols-1 divide-y divide-ink/10 overflow-hidden rounded-lg border border-ink/10 bg-paper-dim sm:grid-cols-3 sm:divide-x sm:divide-y-0 dark:divide-slate-100/10 dark:border-slate-100/10 dark:bg-slate-100/[0.03]">
      {items.map((item) => (
        <div key={item.label} className="p-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
            {item.label}
          </p>
          <p className="tabular-figures mt-1 font-mono text-2xl font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
