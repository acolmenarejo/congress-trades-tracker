import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type PricePoint, type TickerSummary } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import CandlestickChart from "../components/charts/CandlestickChart";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const RANGE_OPTIONS = [
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1A", days: 365 },
  { label: "2A", days: 730 },
];

export default function TickerPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [dark] = useDarkMode();
  const [summary, setSummary] = useState<TickerSummary | null>(null);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [days, setDays] = useState(180);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    api.ticker(ticker).then(setSummary).catch(() => setNotFound(true));
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    api.tickerPrices(ticker, days).then(setPrices).catch(() => setPrices([]));
  }, [ticker, days]);

  if (notFound) {
    return <p className="text-sm text-slate-500">Sin trades registrados para este ticker.</p>;
  }
  if (!summary) {
    return <p className="text-sm text-slate-500">Cargando…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">${summary.ticker}</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {summary.trade_count} trades · {summary.distinct_members} congresistas ·{" "}
          {summary.buy_count} compras / {summary.sell_count} ventas
        </p>
      </div>

      <div className="flex gap-1">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.days}
            type="button"
            onClick={() => setDays(opt.days)}
            className={`rounded-md px-3 py-1 text-sm ${
              days === opt.days
                ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                : "border border-slate-300 dark:border-slate-700"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <CandlestickChart prices={prices} trades={summary.trades} dark={dark} />

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
          Congresistas que han operado ${summary.ticker}
        </h3>
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">Miembro</th>
                <th className="px-3 py-2">Tipo</th>
                <th className="px-3 py-2">Importe</th>
                <th className="px-3 py-2">Fecha</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {summary.trades.map((t) => (
                <tr key={t.id}>
                  <td className="px-3 py-2">
                    <Link to={`/members/${t.member_match_key}`} className="hover:underline">
                      <span
                        className="mr-1.5 inline-block h-2 w-2 rounded-full"
                        style={{ background: partyColor(t.party) }}
                      />
                      {t.member_name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {t.transaction_type === "purchase" ? "Compra" : t.transaction_type === "sale" ? "Venta" : t.transaction_type}
                  </td>
                  <td className="px-3 py-2">{formatAmountRange(t.amount_range_low, t.amount_range_high)}</td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{formatDate(t.transaction_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
