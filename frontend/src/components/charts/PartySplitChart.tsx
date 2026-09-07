import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Trade } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";

const PARTY_LABEL: Record<string, string> = { D: "Demócratas", R: "Republicanos", I: "Independientes" };

export default function PartySplitChart({
  trades,
  dark,
}: {
  trades: Trade[];
  dark: boolean;
}) {
  const colors = chartColors(dark);

  const counts: Record<string, { party: string; Compras: number; Ventas: number }> = {};
  for (const t of trades) {
    if (!t.party) continue;
    const key = t.party;
    counts[key] ??= { party: PARTY_LABEL[key] ?? key, Compras: 0, Ventas: 0 };
    if (t.transaction_type === "purchase") counts[key].Compras += 1;
    else if (t.transaction_type === "sale") counts[key].Ventas += 1;
  }
  const data = Object.values(counts);

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Compra/venta por partido
        </h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Sin datos de partido disponibles todavía.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Compra/venta por partido
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ left: 8, right: 8 }}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis
            dataKey="party"
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={{ stroke: colors.axis }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: colors.surface,
              border: `1px solid ${colors.grid}`,
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Compras" fill={colors.series1} radius={[4, 4, 0, 0]} />
          <Bar dataKey="Ventas" fill={colors.series2} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
