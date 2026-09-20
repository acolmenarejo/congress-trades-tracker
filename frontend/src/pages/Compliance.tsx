import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fetchTradeSample, type MemberRanking, type Trade } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import { chartColors } from "../lib/chartTheme";
import { partyColor } from "../lib/format";
import { SkeletonRows } from "../components/Skeleton";

const STOCK_ACT_LIMIT_DAYS = 45;

const BUCKETS: { label: string; min: number; max: number }[] = [
  { label: "0-15d", min: 0, max: 15 },
  { label: "16-30d", min: 16, max: 30 },
  { label: "31-45d", min: 31, max: 45 },
  { label: "46-90d", min: 46, max: 90 },
  { label: "90d+", min: 91, max: Infinity },
];

export default function Compliance() {
  const [dark] = useDarkMode();
  const [ranking, setRanking] = useState<MemberRanking[] | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);

  useEffect(() => {
    api.ranking("avg_disclosure_lag_days", 100).then(setRanking).catch(() => setRanking([]));
    // /trades caps limit at 500 server-side (HTTP 422 above that) — pull a
    // few pages to get a bigger sample for the lag distribution.
    fetchTradeSample(1500).then(setTrades);
  }, []);

  const stats = useMemo(() => {
    const withLag = trades.filter((t) => t.disclosure_lag_days !== null) as (Trade & { disclosure_lag_days: number })[];
    const compliant = withLag.filter((t) => t.disclosure_lag_days <= STOCK_ACT_LIMIT_DAYS).length;
    const avgLag = withLag.length ? withLag.reduce((s, t) => s + t.disclosure_lag_days, 0) / withLag.length : null;
    const bucketData = BUCKETS.map((b) => ({
      label: b.label,
      count: withLag.filter((t) => t.disclosure_lag_days >= b.min && t.disclosure_lag_days <= b.max).length,
      overLimit: b.min > STOCK_ACT_LIMIT_DAYS,
    }));
    return {
      total: withLag.length,
      complianceRate: withLag.length ? (compliant / withLag.length) * 100 : null,
      avgLag,
      bucketData,
    };
  }, [trades]);

  const offenders = useMemo(() => {
    if (!ranking) return [];
    return ranking
      .filter((r) => r.avg_disclosure_lag_days !== null && r.avg_disclosure_lag_days > STOCK_ACT_LIMIT_DAYS)
      .sort((a, b) => (b.avg_disclosure_lag_days ?? 0) - (a.avg_disclosure_lag_days ?? 0))
      .slice(0, 20);
  }, [ranking]);

  const colors = chartColors(dark);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Cumplimiento de la Ley STOCK</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          La Ley STOCK obliga a declarar cualquier transacción en un máximo de{" "}
          {STOCK_ACT_LIMIT_DAYS} días. Esta vista mide, sobre la muestra de trades cargada,
          cuántos se declaran dentro de plazo y qué miembros acumulan más retraso.
        </p>
      </div>

      <div className="grid grid-cols-1 divide-y divide-ink/10 overflow-hidden rounded-lg border border-ink/10 bg-paper-dim sm:grid-cols-3 sm:divide-x sm:divide-y-0 dark:divide-slate-100/10 dark:border-slate-100/10 dark:bg-slate-100/[0.03]">
        <div className="p-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
            Tasa de cumplimiento
          </p>
          <p
            className={`tabular-figures mt-1 font-mono text-2xl font-semibold ${
              stats.complianceRate !== null && stats.complianceRate < 80 ? "text-sell-dim dark:text-sell" : ""
            }`}
          >
            {stats.complianceRate !== null ? `${stats.complianceRate.toFixed(1)}%` : "—"}
          </p>
        </div>
        <div className="p-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
            Retraso medio de declaración
          </p>
          <p className="tabular-figures mt-1 font-mono text-2xl font-semibold">
            {stats.avgLag !== null ? `${stats.avgLag.toFixed(0)}d` : "—"}
          </p>
        </div>
        <div className="p-4">
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
            Miembros por encima del límite
          </p>
          <p className="tabular-figures mt-1 font-mono text-2xl font-semibold">
            {ranking ? offenders.length : "—"}
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
        <h3 className="mb-3 font-serif text-base font-semibold">Distribución de retraso en la declaración</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={stats.bucketData} margin={{ left: 8, right: 8 }}>
            <CartesianGrid stroke={colors.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: colors.textMuted, fontSize: 12 }} axisLine={{ stroke: colors.axis }} tickLine={false} />
            <YAxis tick={{ fill: colors.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.grid}`, fontSize: 12 }} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {stats.bucketData.map((b, i) => (
                <Cell key={i} fill={b.overLimit ? colors.partyR : colors.series1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="mb-2 font-serif text-base font-semibold">Peor cumplimiento por miembro</h3>
        {!ranking && <SkeletonRows rows={6} />}
        {ranking && (
          <div className="overflow-x-auto rounded-lg border border-ink/10 dark:border-slate-100/10">
            <table className="w-full text-sm">
              <thead className="bg-paper-dim text-left font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:bg-slate-100/[0.03] dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">Miembro</th>
                  <th className="px-3 py-2">Trades</th>
                  <th className="px-3 py-2">Retraso medio</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink/10 dark:divide-slate-100/10">
                {offenders.map((r) => (
                  <tr key={r.match_key} className="border-l-[3px]" style={{ borderLeftColor: partyColor(r.party) }}>
                    <td className="px-3 py-2">
                      <Link to={`/members/${r.match_key}`} className="hover:underline">
                        {r.name}
                      </Link>
                    </td>
                    <td className="tabular-figures px-3 py-2 font-mono">{r.trade_count}</td>
                    <td className="tabular-figures px-3 py-2 font-mono font-medium text-sell-dim dark:text-sell">
                      {r.avg_disclosure_lag_days?.toFixed(0)}d
                    </td>
                  </tr>
                ))}
                {offenders.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-3 text-ink/60 dark:text-slate-400">
                      Nadie por encima del límite en la muestra actual.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
