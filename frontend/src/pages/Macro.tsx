import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { api, type MacroIndicator, type MacroPolymarket, type MacroSnapshot } from "../lib/api";
import { formatUSD } from "../lib/format";
import { SkeletonRows } from "../components/Skeleton";
import { chartColors } from "../lib/chartTheme";
import { useDarkMode } from "../hooks/useDarkMode";

const STATUS: Record<MacroIndicator["status"], { label: string; cls: string }> = {
  ok: { label: "Normal", cls: "bg-buy/15 text-buy-dim dark:text-buy" },
  watch: { label: "Vigilar", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  stress: { label: "Tensión", cls: "bg-sell/15 text-sell-dim dark:text-sell" },
};

const REGIME: Record<MacroSnapshot["regime"], string> = {
  favorable: "border-buy/60 bg-buy/5",
  mixto: "border-amber-500/60 bg-amber-500/5",
  tenso: "border-sell/60 bg-sell/5",
};

function fmt(v: number | null, unit: string): string {
  if (v === null) return "—";
  const n = Math.abs(v) >= 100 ? v.toLocaleString("es-ES", { maximumFractionDigits: 0 }) : v.toFixed(2);
  return unit === "%" || unit === "pp" ? `${n}${unit === "%" ? "%" : " pp"}` : unit ? `${n} ${unit}` : n;
}

function Card({ i, dark }: { i: MacroIndicator; dark: boolean }) {
  const colors = chartColors(dark);
  const st = STATUS[i.status];
  return (
    <div className="flex flex-col rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-serif text-base font-semibold">{i.name}</h3>
          <p className="tabular-figures font-mono text-xl font-bold">{fmt(i.value, i.unit)}</p>
          {i.change !== null && (
            <p className="font-mono text-xs text-ink/50 dark:text-slate-400">
              {i.change > 0 ? "+" : ""}
              {Math.abs(i.change) >= 100 ? i.change.toLocaleString("es-ES", { maximumFractionDigits: 0 }) : i.change.toFixed(i.unit === "%" || i.unit === "pp" ? 2 : 0)}{" "}
              {i.change_label}
            </p>
          )}
        </div>
        <span className={`shrink-0 rounded px-2 py-0.5 font-mono text-xs font-bold uppercase ${st.cls}`}>{st.label}</span>
      </div>
      {i.history.length > 1 && (
        <div className="mt-2 h-16">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={i.history}>
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: colors.surface, border: `1px solid ${colors.grid}`, fontSize: 12 }}
                labelFormatter={(_, p) => p?.[0]?.payload?.date ?? ""}
                formatter={(v) => [fmt(Number(v), i.unit), i.name]}
              />
              <Line type="monotone" dataKey="value" stroke={colors.series1} dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-sm">{i.reading}</p>
      <p className="mt-2 rounded bg-ink/5 px-3 py-2 text-sm dark:bg-slate-100/5">
        <span className="font-semibold">Qué implica:</span> {i.action}
      </p>
      {i.as_of && <p className="mt-2 font-mono text-[11px] text-ink/40 dark:text-slate-500">Dato del {i.as_of}</p>}
    </div>
  );
}

function PolymarketCheck({ pm }: { pm: MacroPolymarket }) {
  if (pm.odds.length === 0) return null;
  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <h3 className="font-serif text-lg font-semibold">Lo que apuesta Polymarket</h3>
      <p className="mb-3 text-xs text-ink/50 dark:text-slate-400">
        Probabilidades implícitas en dinero real, comparadas con lo que dicen los bonos y el crédito.
      </p>
      <div className="space-y-2">
        {pm.checks.map((c, n) => (
          <p
            key={n}
            className={`rounded px-3 py-2 text-sm ${
              c.status === "watch" ? "bg-amber-500/10 text-amber-800 dark:text-amber-300" : "bg-buy/10"
            }`}
          >
            {c.status === "watch" ? "⚠️ " : "✓ "}
            {c.text}
          </p>
        ))}
      </div>
      <ul className="mt-3 grid gap-2 md:grid-cols-2">
        {pm.odds.map((o) => (
          <li key={o.key} className="rounded border border-ink/10 p-3 text-sm dark:border-slate-100/10">
            <p className="font-medium">
              {o.url ? (
                <a href={o.url} target="_blank" rel="noreferrer" className="underline">
                  {o.title}
                </a>
              ) : (
                o.title
              )}
            </p>
            <p className="font-mono text-xs">{o.text}</p>
            {o.change !== null && (
              <p className="font-mono text-[11px] text-ink/50 dark:text-slate-400">
                {o.change > 0 ? "+" : ""}
                {o.change} {o.change_label}
              </p>
            )}
          </li>
        ))}
      </ul>
      {pm.bets.length > 0 && (
        <>
          <h4 className="mt-4 font-mono text-xs uppercase tracking-wide text-ink/50 dark:text-slate-400">
            Apuestas sospechosas en mercados financieros (7 días)
          </h4>
          <ul className="mt-1 space-y-1 text-sm">
            {pm.bets.map((b) => (
              <li key={b.id}>
                <span className="font-mono text-xs font-bold">{Math.round(b.score)}/100</span> {formatUSD(b.size_usd)} a «
                {b.outcome}» ({Math.round((b.price ?? 0) * 100)}¢) en{" "}
                {b.slug ? (
                  <a href={`https://polymarket.com/event/${b.slug}`} target="_blank" rel="noreferrer" className="underline">
                    {b.question}
                  </a>
                ) : (
                  b.question
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function Macro() {
  const [dark] = useDarkMode();
  const [snap, setSnap] = useState<MacroSnapshot | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.macro().then(setSnap).catch(() => setFailed(true));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Macro: tipos, volatilidad y liquidez</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          Lo que mueve a toda la bolsa a la vez: tipos de interés, curva, volatilidad de bonos (MOVE) y de
          acciones (VIX), crédito y la "fontanería" de la Fed (liquidez neta, reservas, repo). Cada tarjeta dice
          qué está pasando y qué suele implicar. Las reglas son las habituales del mercado, no un modelo
          ajustado, y no son asesoramiento. Datos de FRED y Yahoo, actualizados cada día laborable.
        </p>
      </div>

      {!snap && !failed && <SkeletonRows rows={6} />}
      {failed && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          No se pudieron cargar los datos macro.
        </div>
      )}

      {snap && snap.indicators.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Todavía no hay datos macro: se cargan en la primera ejecución diaria.
        </div>
      )}

      {snap && snap.indicators.length > 0 && (
        <>
          <div className={`rounded-lg border-2 p-4 ${REGIME[snap.regime]}`}>
            <p className="font-mono text-xs uppercase tracking-wide text-ink/50 dark:text-slate-400">Entorno</p>
            <p className="font-serif text-xl font-semibold capitalize">{snap.regime}</p>
            <p className="text-sm">{snap.summary}</p>
            <p className="mt-1 font-mono text-xs text-ink/50 dark:text-slate-400">
              {snap.stress} en tensión · {snap.watch} a vigilar · {snap.indicators.length - snap.stress - snap.watch} normales
            </p>
          </div>
          <PolymarketCheck pm={snap.polymarket} />
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {snap.indicators.map((i) => (
              <Card key={i.key} i={i} dark={dark} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
