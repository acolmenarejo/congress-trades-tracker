import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PricePoint } from "../lib/api";
import { useDecisionLog, type DecisionEntry } from "../hooks/useDecisionLog";
import { formatPct, formatUSD } from "../lib/format";

const MAX_DAYS = 1825;

function priceOnOrAfter(series: PricePoint[], date: string): number | null {
  const hit = series.find((p) => p.date >= date && p.close !== null);
  return hit?.close ?? null;
}

function latestPrice(series: PricePoint[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i].close !== null) return series[i].close;
  }
  return null;
}

interface Valued {
  entry: DecisionEntry;
  entryPrice: number | null;
  currentPrice: number | null;
  valueNow: number | null;
}

export default function MyTrackRecord() {
  const { entries, remove } = useDecisionLog();
  const [valued, setValued] = useState<Valued[] | null>(null);

  useEffect(() => {
    const actionable = entries.filter((e) => e.action === "compré" && e.ticker && e.stakeUsd);
    const tickers = Array.from(new Set(actionable.map((e) => e.ticker)));

    if (tickers.length === 0) {
      setValued([]);
      return;
    }

    Promise.all(
      tickers.map((ticker) => api.tickerPrices(ticker, MAX_DAYS).then((series) => [ticker, series] as const)),
    ).then((pairs) => {
      const seriesByTicker = new Map(pairs);
      const result: Valued[] = actionable.map((entry) => {
        const series = seriesByTicker.get(entry.ticker) ?? [];
        const entryPrice = entry.entryPrice ?? priceOnOrAfter(series, entry.loggedDate);
        const currentPrice = latestPrice(series);
        const valueNow =
          entryPrice && currentPrice && entry.stakeUsd ? entry.stakeUsd * (currentPrice / entryPrice) : null;
        return { entry, entryPrice, currentPrice, valueNow };
      });
      setValued(result);
    });
  }, [entries]);

  const totalInvested = (valued ?? []).reduce((s, v) => s + (v.entry.stakeUsd ?? 0), 0);
  const totalNow = (valued ?? []).reduce((s, v) => s + (v.valueNow ?? v.entry.stakeUsd ?? 0), 0);
  const returnPct = totalInvested > 0 ? (totalNow / totalInvested - 1) * 100 : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Mi seguimiento</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          Lo que anotaste con el botón 📝 en el Feed o en una página de ticker — tu decisión real, no la
          hipotética del simulador. Se guarda solo en este navegador.
        </p>
      </div>

      {entries.length === 0 ? (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Todavía no has anotado ninguna decisión. Pulsa 📝 junto a un trade en el Feed o en la página de
          un ticker.
        </div>
      ) : (
        <>
          {totalInvested > 0 && (
            <div className="grid grid-cols-1 divide-y divide-ink/10 overflow-hidden rounded-lg border border-ink/10 bg-paper-dim sm:grid-cols-3 sm:divide-x sm:divide-y-0 dark:divide-slate-100/10 dark:border-slate-100/10 dark:bg-slate-100/[0.03]">
              <div className="p-3">
                <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                  Invertido (real)
                </p>
                <p className="tabular-figures mt-1 font-mono text-xl font-semibold">{formatUSD(totalInvested)}</p>
              </div>
              <div className="p-3">
                <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                  Valor hoy
                </p>
                <p className="tabular-figures mt-1 font-mono text-xl font-semibold">{formatUSD(totalNow)}</p>
              </div>
              <div className="p-3">
                <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                  Retorno real
                </p>
                <p
                  className={`tabular-figures mt-1 font-mono text-xl font-semibold ${
                    (returnPct ?? 0) >= 0 ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
                  }`}
                >
                  {formatPct(returnPct)}
                </p>
              </div>
            </div>
          )}

          <ul className="divide-y divide-ink/10 rounded-lg border border-ink/10 dark:divide-slate-100/10 dark:border-slate-100/10">
            {entries.map((e) => {
              const v = valued?.find((x) => x.entry.id === e.id);
              return (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                  <div>
                    <span className="font-medium">{e.action}</span>{" "}
                    <Link to={`/tickers/${e.ticker}`} className="font-mono hover:underline">
                      ${e.ticker}
                    </Link>{" "}
                    <span className="text-ink/50 dark:text-slate-400">— por {e.memberName}</span>
                    {e.note && <div className="text-xs text-ink/50 dark:text-slate-400">"{e.note}"</div>}
                    <div className="font-mono text-xs text-ink/50 dark:text-slate-400">{e.loggedDate}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    {v && v.valueNow !== null && (
                      <span
                        className={`tabular-figures font-mono font-medium ${
                          v.valueNow >= (e.stakeUsd ?? 0) ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
                        }`}
                      >
                        {formatUSD(v.valueNow)}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => remove(e.id)}
                      className="font-mono text-xs text-ink/40 hover:text-sell dark:text-slate-500"
                    >
                      borrar
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
