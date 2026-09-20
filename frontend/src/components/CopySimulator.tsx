import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Trade, type PricePoint } from "../lib/api";
import { formatPct, formatUSD } from "../lib/format";

const PER_TRADE_STAKE = 1000;
const MAX_DAYS = 1825; // backend cap (5 years)

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

interface SimRow {
  trade: Trade;
  entryPrice: number;
  currentPrice: number;
  valueNow: number;
}

export default function CopySimulator({ trades, memberName }: { trades: Trade[]; memberName: string }) {
  const [running, setRunning] = useState(false);
  const [ran, setRan] = useState(false);
  const [rows, setRows] = useState<SimRow[]>([]);
  const [skipped, setSkipped] = useState(0);

  async function run() {
    setRunning(true);
    const buys = trades.filter((t) => t.transaction_type === "purchase" && t.ticker && t.transaction_date);
    const tickers = Array.from(new Set(buys.map((t) => t.ticker as string)));

    const seriesByTicker = new Map<string, PricePoint[]>();
    await Promise.all(
      tickers.map((ticker) =>
        api
          .tickerPrices(ticker, MAX_DAYS)
          .then((series) => seriesByTicker.set(ticker, series))
          .catch(() => seriesByTicker.set(ticker, [])),
      ),
    );

    const result: SimRow[] = [];
    let missed = 0;
    for (const trade of buys) {
      const series = seriesByTicker.get(trade.ticker as string) ?? [];
      const entryPrice = priceOnOrAfter(series, trade.transaction_date as string);
      const currentPrice = latestPrice(series);
      if (entryPrice === null || currentPrice === null || entryPrice <= 0) {
        missed++;
        continue;
      }
      result.push({ trade, entryPrice, currentPrice, valueNow: PER_TRADE_STAKE * (currentPrice / entryPrice) });
    }
    result.sort((a, b) => b.valueNow - a.valueNow);
    setRows(result);
    setSkipped(missed);
    setRunning(false);
    setRan(true);
  }

  const totalInvested = rows.length * PER_TRADE_STAKE;
  const totalNow = rows.reduce((s, r) => s + r.valueNow, 0);
  const returnPct = totalInvested > 0 ? (totalNow / totalInvested - 1) * 100 : null;

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-serif text-base font-semibold">Simulador: ¿y si copio a {memberName}?</h3>
          <p className="mt-1 max-w-xl text-xs text-ink/50 dark:text-slate-400">
            Invierte ${PER_TRADE_STAKE.toLocaleString("es-ES")} hipotéticos en cada compra suya y los mantiene hasta
            hoy — no simula ventas ni reinversión, es una aproximación de "seguir cada señal de compra".
          </p>
        </div>
        {!ran && (
          <button
            type="button"
            onClick={run}
            disabled={running}
            className="shrink-0 rounded-md bg-ink px-3 py-1.5 font-mono text-xs uppercase tracking-wide text-paper disabled:opacity-50 dark:bg-buy dark:text-ledger"
          >
            {running ? "Calculando…" : "Simular"}
          </button>
        )}
      </div>

      {ran && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-1 divide-y divide-ink/10 overflow-hidden rounded-lg border border-ink/10 bg-paper-dim sm:grid-cols-3 sm:divide-x sm:divide-y-0 dark:divide-slate-100/10 dark:border-slate-100/10 dark:bg-slate-100/[0.03]">
            <div className="p-3">
              <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                Invertido ({rows.length} compras)
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
                Retorno simulado
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

          {skipped > 0 && (
            <p className="text-xs text-ink/50 dark:text-slate-400">
              {skipped} compra(s) sin histórico de precio suficiente, excluida(s) del cálculo.
            </p>
          )}

          <div className="overflow-x-auto rounded-lg border border-ink/10 dark:border-slate-100/10">
            <table className="w-full text-sm">
              <thead className="bg-paper-dim text-left font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:bg-slate-100/[0.03] dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">Ticker</th>
                  <th className="px-3 py-2">Entrada</th>
                  <th className="px-3 py-2">Precio hoy</th>
                  <th className="px-3 py-2">${PER_TRADE_STAKE} hoy valdrían</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink/10 dark:divide-slate-100/10">
                {rows.map((r) => (
                  <tr key={r.trade.id}>
                    <td className="px-3 py-2 font-mono font-medium">
                      <Link to={`/tickers/${r.trade.ticker}`} className="hover:underline">
                        ${r.trade.ticker}
                      </Link>
                    </td>
                    <td className="tabular-figures px-3 py-2 font-mono">${r.entryPrice.toFixed(2)}</td>
                    <td className="tabular-figures px-3 py-2 font-mono">${r.currentPrice.toFixed(2)}</td>
                    <td
                      className={`tabular-figures px-3 py-2 font-mono font-medium ${
                        r.valueNow >= PER_TRADE_STAKE ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"
                      }`}
                    >
                      {formatUSD(r.valueNow)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
