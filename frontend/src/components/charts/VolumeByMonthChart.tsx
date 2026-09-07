import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Trade } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";
import { formatUSD } from "../../lib/format";

export default function VolumeByMonthChart({
  trades,
  dark,
}: {
  trades: Trade[];
  dark: boolean;
}) {
  const colors = chartColors(dark);

  const byMonth = new Map<string, number>();
  for (const t of trades) {
    if (!t.transaction_date || !t.amount_mid) continue;
    const month = t.transaction_date.slice(0, 7); // YYYY-MM
    byMonth.set(month, (byMonth.get(month) ?? 0) + t.amount_mid);
  }
  const data = Array.from(byMonth.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, volume]) => ({ month, volume }));

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Volumen operado por mes
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ left: 8, right: 8 }}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={{ stroke: colors.axis }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => formatUSD(v)}
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            formatter={(value) => formatUSD(Number(value))}
            contentStyle={{
              background: colors.surface,
              border: `1px solid ${colors.grid}`,
              fontSize: 12,
            }}
          />
          <Bar dataKey="volume" fill={colors.series1} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
