import { useEffect, useState } from "react";
import { api, type PolymarketAlert } from "../lib/api";
import { SkeletonRows } from "../components/Skeleton";
import { formatUSD } from "../lib/format";

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const hours = diffMs / 3_600_000;
  if (hours < 1) return `hace ${Math.round(diffMs / 60_000)}min`;
  if (hours < 48) return `hace ${Math.round(hours)}h`;
  return `hace ${Math.round(hours / 24)}d`;
}

export default function PolymarketWatch() {
  const [alerts, setAlerts] = useState<PolymarketAlert[] | null>(null);

  useEffect(() => {
    api.polymarketWhaleBets(100).then(setAlerts).catch(() => setAlerts([]));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Polymarket — apuestas grandes en incertidumbre</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          Apuestas individuales inusualmente grandes (≥5% de la liquidez del mercado) en mercados de
          predicción sobre política/geopolítica cuyo resultado todavía es incierto (precio entre 8% y
          92%). Sin relación con el Congreso — las wallets de Polymarket son anónimas, no hay forma de
          vincularlas a una persona real. Es una señal de "alguien apuesta muy fuerte a algo que no se
          sabe": alta convicción, o información que el mercado aún no tiene. Se actualiza cada ~3 horas.
        </p>
      </div>

      {alerts === null && <SkeletonRows rows={6} />}

      {alerts !== null && alerts.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Sin apuestas inusuales detectadas todavía en el último escaneo.
        </div>
      )}

      {alerts !== null && alerts.length > 0 && (
        <ul className="space-y-2">
          {alerts.map((a) => (
            <li
              key={a.id}
              className="rounded-lg border-2 border-amber-500 bg-amber-500/5 p-4 dark:bg-amber-500/10"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                    {a.event_title}
                  </p>
                  <p className="font-serif text-base font-semibold">{a.market_question}</p>
                </div>
                <span className="shrink-0 font-mono text-xs text-ink/50 dark:text-slate-400">
                  {timeAgo(a.trade_timestamp)}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                <span
                  className={`font-mono font-bold uppercase ${
                    a.side === "BUY" ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
                  }`}
                >
                  {a.side === "BUY" ? "Compró" : "Vendió"} "{a.outcome}"
                </span>
                <span className="tabular-figures font-mono font-bold text-ink dark:text-slate-100">
                  {formatUSD(a.size_usd)}
                </span>
                <span className="font-mono text-xs text-ink/60 dark:text-slate-400">
                  a {((a.price ?? 0) * 100).toFixed(1)}¢ · {((a.pct_of_liquidity ?? 0) * 100).toFixed(1)}% de la
                  liquidez del mercado
                </span>
                {a.market_slug && (
                  <a
                    href={`https://polymarket.com/event/${a.event_slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-xs text-buy-dim underline dark:text-buy"
                  >
                    Ver en Polymarket →
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
