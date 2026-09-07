import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Trade, type TradeFilters } from "../lib/api";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const PAGE_SIZE = 30;

export default function Feed() {
  const [filters, setFilters] = useState<TradeFilters>({});
  const [trades, setTrades] = useState<Trade[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .trades({ ...filters, limit: PAGE_SIZE, offset })
      .then((res) => {
        setTrades(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [filters, offset]);

  function updateFilter<K extends keyof TradeFilters>(key: K, value: TradeFilters[K]) {
    setOffset(0);
    setFilters((f) => ({ ...f, [key]: value || undefined }));
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Feed de transacciones</h2>

      <div className="flex flex-wrap gap-2">
        <select
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          value={filters.chamber ?? ""}
          onChange={(e) => updateFilter("chamber", e.target.value)}
        >
          <option value="">Ambas cámaras</option>
          <option value="house">Cámara de Representantes</option>
          <option value="senate">Senado</option>
        </select>
        <select
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          value={filters.party ?? ""}
          onChange={(e) => updateFilter("party", e.target.value)}
        >
          <option value="">Cualquier partido</option>
          <option value="D">Demócratas</option>
          <option value="R">Republicanos</option>
          <option value="I">Independientes</option>
        </select>
        <select
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          value={filters.transaction_type ?? ""}
          onChange={(e) => updateFilter("transaction_type", e.target.value)}
        >
          <option value="">Compra/venta</option>
          <option value="purchase">Compra</option>
          <option value="sale">Venta</option>
          <option value="exchange">Canje</option>
        </select>
        <input
          type="text"
          placeholder="Ticker (ej. NVDA)"
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          onChange={(e) => updateFilter("ticker", e.target.value.toUpperCase())}
        />
        <input
          type="text"
          placeholder="Miembro (ej. Pelosi)"
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          onChange={(e) => updateFilter("member", e.target.value)}
        />
        <input
          type="date"
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          onChange={(e) => updateFilter("date_from", e.target.value)}
        />
        <input
          type="date"
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
          onChange={(e) => updateFilter("date_to", e.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">Miembro</th>
              <th className="px-3 py-2">Cámara</th>
              <th className="px-3 py-2">Ticker</th>
              <th className="px-3 py-2">Tipo</th>
              <th className="px-3 py-2">Importe</th>
              <th className="px-3 py-2">Fecha op.</th>
              <th className="px-3 py-2">Disclosure</th>
              <th className="px-3 py-2">Retraso</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {trades.map((t) => (
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
                <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                  {t.chamber === "house" ? "Cámara" : t.chamber === "senate" ? "Senado" : "—"}
                </td>
                <td className="px-3 py-2 font-medium">{t.ticker}</td>
                <td className="px-3 py-2">
                  {t.transaction_type === "purchase" ? "Compra" : t.transaction_type === "sale" ? "Venta" : t.transaction_type}
                </td>
                <td className="px-3 py-2">{formatAmountRange(t.amount_range_low, t.amount_range_high)}</td>
                <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{formatDate(t.transaction_date)}</td>
                <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{formatDate(t.disclosure_date)}</td>
                <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                  {t.disclosure_lag_days !== null ? `${t.disclosure_lag_days}d` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <p className="p-3 text-sm text-slate-500">Cargando…</p>}
        {!loading && trades.length === 0 && (
          <p className="p-3 text-sm text-slate-500">Sin resultados para estos filtros.</p>
        )}
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
        <span>
          {total.toLocaleString("es-ES")} resultados — mostrando {offset + 1}-
          {Math.min(offset + PAGE_SIZE, total)}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40 dark:border-slate-700"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-40 dark:border-slate-700"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
