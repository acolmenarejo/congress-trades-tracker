import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trade } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";

const LABELS: Record<string, string> = {
  stock: "Acciones",
  st: "Acciones",
  stock_option: "Opciones",
  corporate_bond: "Bonos corp.",
  municipal_security: "Bonos munic.",
  other_securities: "Otros valores",
};

export default function AssetTypeChart({ trades, dark }: { trades: Trade[]; dark: boolean }) {
  const colors = chartColors(dark);

  const byType = new Map<string, number>();
  for (const t of trades) {
    const key = t.asset_type ?? "unknown";
    if (key === "unknown") continue;
    byType.set(key, (byType.get(key) ?? 0) + 1);
  }
  const data = Array.from(byType.entries())
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)
    .map(([type, count]) => ({ type: LABELS[type] ?? type, count }));

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
        <h3 className="mb-3 font-serif text-base font-semibold">Tipos de activo operados</h3>
        <p className="text-sm text-ink/60 dark:text-slate-400">Sin datos de tipo de activo todavía.</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <h3 className="mb-3 font-serif text-base font-semibold">Tipos de activo operados</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid stroke={colors.grid} horizontal={false} />
          <XAxis type="number" tick={{ fill: colors.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="type" tick={{ fill: colors.textSecondary, fontSize: 12 }} axisLine={false} tickLine={false} width={90} />
          <Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.grid}`, fontSize: 12 }} />
          <Bar dataKey="count" fill={colors.series3} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
