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

export default function TopTickersChart({
  trades,
  dark,
}: {
  trades: Trade[];
  dark: boolean;
}) {
  const colors = chartColors(dark);

  const byTicker = new Map<string, number>();
  for (const t of trades) {
    if (!t.ticker || !t.amount_mid) continue;
    byTicker.set(t.ticker, (byTicker.get(t.ticker) ?? 0) + t.amount_mid);
  }
  const data = Array.from(byTicker.entries())
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
    .map(([ticker, volume]) => ({ ticker, volume }))
    .reverse(); // largest on top in a horizontal bar

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Top 10 tickers más operados
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid stroke={colors.grid} horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v) => formatUSD(v)}
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="ticker"
            tick={{ fill: colors.textSecondary, fontSize: 12 }}
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
          <Bar dataKey="volume" fill={colors.series1} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
