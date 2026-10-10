import { useEffect, useState } from "react";
import { api, type PolymarketAlert, type PolymarketCategory } from "../lib/api";
import { SkeletonRows } from "../components/Skeleton";
import { formatUSD } from "../lib/format";

const CATEGORIES: { value: PolymarketCategory | ""; label: string }[] = [
  { value: "", label: "Todas" },
  { value: "mercados", label: "Mercados" },
  { value: "geopolitica", label: "Geopolítica" },
  { value: "otros", label: "Otros" },
];

const CATEGORY_LABEL: Record<string, string> = {
  mercados: "Mercados",
  geopolitica: "Geopolítica",
  otros: "Otros",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const hours = diffMs / 3_600_000;
  if (hours < 1) return `hace ${Math.round(diffMs / 60_000)}min`;
  if (hours < 48) return `hace ${Math.round(hours)}h`;
  return `hace ${Math.round(hours / 24)}d`;
}

function scoreClass(score: number): string {
  if (score >= 75) return "bg-sell/15 text-sell-dim dark:text-sell";
  if (score >= 55) return "bg-amber-500/15 text-amber-700 dark:text-amber-400";
  return "bg-ink/5 text-ink/60 dark:bg-slate-100/10 dark:text-slate-400";
}

function BetCard({ a }: { a: PolymarketAlert }) {
  const price = a.price ?? 0;
  const payout = price > 0 ? a.size_usd / price : null;
  return (
    <li className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
            {CATEGORY_LABEL[a.tag ?? ""] ?? a.tag} · {timeAgo(a.trade_timestamp)}
            {a.alerted && " · avisado por Telegram"}
          </p>
          <p className="font-serif text-base font-semibold">{a.market_question}</p>
        </div>
        <span className={`shrink-0 rounded px-2 py-1 font-mono text-sm font-bold ${scoreClass(a.score ?? 0)}`}>
          {Math.round(a.score ?? 0)}/100
        </span>
      </div>
      <p className="mt-2 text-sm">
        <span className="tabular-figures font-mono font-bold">{formatUSD(a.size_usd)}</span> a «{a.outcome}» a{" "}
        {(price * 100).toFixed(0)}¢
        {payout && (
          <span className="text-ink/60 dark:text-slate-400"> → cobraría {formatUSD(payout)} si acierta</span>
        )}
      </p>
      {a.reasons.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm text-ink/70 dark:text-slate-300">
          {a.reasons.map((r) => (
            <li key={r}>✓ {r}</li>
          ))}
        </ul>
      )}
      {a.implication && (
        <p className="mt-2 rounded bg-ink/5 px-3 py-2 text-sm dark:bg-slate-100/5">
          <span className="font-semibold">Qué podría implicar:</span> {a.implication}
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-3 font-mono text-xs text-ink/50 dark:text-slate-400">
        {a.event_slug && (
          <a
            href={`https://polymarket.com/event/${a.event_slug}`}
            target="_blank"
            rel="noreferrer"
            className="text-buy-dim underline dark:text-buy"
          >
            Ver mercado →
          </a>
        )}
        {a.wallet && (
          <a
            href={`https://polymarket.com/profile/${a.wallet}`}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            cartera {a.wallet.slice(0, 10)}…
          </a>
        )}
      </div>
    </li>
  );
}

export default function PolymarketWatch() {
  const [alerts, setAlerts] = useState<PolymarketAlert[] | null>(null);
  const [category, setCategory] = useState<PolymarketCategory | "">("");
  const [days, setDays] = useState(7);

  useEffect(() => {
    setAlerts(null);
    api
      .polymarketWhaleBets(100, days, category || undefined)
      .then(setAlerts)
      .catch(() => setAlerts([]));
  }, [category, days]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Polymarket: apuestas sospechosas</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          Apuestas de 10.000 $ o más que encajan con alguien que sabe algo: mucho dinero a un resultado que el
          mercado ve poco probable, en un mercado que se resuelve pronto y desde una cartera casi nueva. La nota
          (0-100) suma tamaño, lo improbable de la apuesta, la cercanía de la fecha, lo nueva que es la cartera y
          el peso sobre la liquidez. Se ignoran deportes y las apuestas de cripto a corto plazo. Por Telegram
          solo avisan las de mercados (nota ≥ 55) y geopolítica (nota ≥ 75). Las carteras son anónimas: no
          sabemos quién está detrás.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex overflow-hidden rounded border border-ink/15 dark:border-slate-100/15">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              onClick={() => setCategory(c.value)}
              className={`px-3 py-1.5 text-sm ${
                category === c.value ? "bg-ink text-paper dark:bg-buy dark:text-ledger" : ""
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded border border-ink/15 bg-transparent px-2 py-1.5 text-sm dark:border-slate-100/15"
        >
          {[1, 7, 30].map((d) => (
            <option key={d} value={d}>
              Últimos {d} {d === 1 ? "día" : "días"}
            </option>
          ))}
        </select>
      </div>

      {alerts === null && <SkeletonRows rows={6} />}

      {alerts !== null && alerts.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Ninguna apuesta sospechosa en este periodo.
        </div>
      )}

      {alerts !== null && alerts.length > 0 && (
        <ul className="space-y-3">
          {alerts.map((a) => (
            <BetCard key={a.id} a={a} />
          ))}
        </ul>
      )}
    </div>
  );
}
