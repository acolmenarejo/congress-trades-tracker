import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trade } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";
import { sectorsForTicker } from "../../lib/conflictOfInterest";

export default function SectorActivityChart({ trades, dark }: { trades: Trade[]; dark: boolean }) {
  const colors = chartColors(dark);

  const counts = new Map<string, number>();
  for (const t of trades) {
    for (const sector of sectorsForTicker(t.ticker)) {
      counts.set(sector, (counts.get(sector) ?? 0) + 1);
    }
  }
  const data = Array.from(counts.entries())
    .sort(([, a], [, b]) => b - a)
    .map(([sector, count]) => ({ sector, count }));

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
        <h3 className="mb-3 font-serif text-base font-semibold">Actividad por sector</h3>
        <p className="text-sm text-ink/60 dark:text-slate-400">
          Sin tickers reconocidos en el mapeo de sectores todavía.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <h3 className="mb-1 font-serif text-base font-semibold">Actividad por sector</h3>
      <p className="mb-3 text-xs text-ink/50 dark:text-slate-400">
        Trades sobre tickers de sectores con jurisdicción de comité reconocida (ver Feed).
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid stroke={colors.grid} horizontal={false} />
          <XAxis type="number" tick={{ fill: colors.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="sector" tick={{ fill: colors.textSecondary, fontSize: 12 }} axisLine={false} tickLine={false} width={140} />
          <Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.grid}`, fontSize: 12 }} />
          <Bar dataKey="count" fill={colors.series1} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
