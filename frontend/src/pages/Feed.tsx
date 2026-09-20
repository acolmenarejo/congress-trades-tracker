import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fetchTradeSample, BASE, type Trade, type TradeFilters } from "../lib/api";
import TransactionBadge from "../components/TransactionBadge";
import ConflictBadge from "../components/ConflictBadge";
import HighValueBadge from "../components/HighValueBadge";
import { SkeletonRows } from "../components/Skeleton";
import { useCommitteesForMembers } from "../hooks/useCommittees";
import { detectConflict } from "../lib/conflictOfInterest";
import { highValueTier } from "../lib/highValue";
import { formatAmountRange, formatDate, partyColor } from "../lib/format";

const PAGE_SIZE = 30;
const FILTER_KEYS = [
  "chamber",
  "party",
  "transaction_type",
  "ticker",
  "member",
  "date_from",
  "date_to",
] as const;

function rssQuery(filters: TradeFilters): string {
  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const v = filters[key];
    if (v) params.set(key, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

function filtersFromParams(params: URLSearchParams): TradeFilters {
  const f: TradeFilters = {};
  for (const key of FILTER_KEYS) {
    const v = params.get(key);
    if (v) f[key] = v;
  }
  return f;
}

export default function Feed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<TradeFilters>(() => filtersFromParams(searchParams));
  const [trades, setTrades] = useState<Trade[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const committees = useCommitteesForMembers(trades.map((t) => t.member_match_key));

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
    setFilters((f) => {
      const next = { ...f, [key]: value || undefined };
      const params = new URLSearchParams();
      for (const k of FILTER_KEYS) {
        const v = next[k];
        if (v) params.set(k, String(v));
      }
      setSearchParams(params, { replace: true });
      return next;
    });
  }

  async function exportCsv() {
    setExporting(true);
    try {
      const items = await fetchTradeSample(5000, filters);
      const header = ["Miembro", "Partido", "Camara", "Ticker", "Tipo", "Importe min", "Importe max", "Fecha op.", "Disclosure", "Retraso (d)"];
      const rows = items.map((t) => [
        t.member_name,
        t.party ?? "",
        t.chamber ?? "",
        t.ticker ?? "",
        t.transaction_type ?? "",
        t.amount_range_low ?? "",
        t.amount_range_high ?? "",
        t.transaction_date ?? "",
        t.disclosure_date ?? "",
        t.disclosure_lag_days ?? "",
      ]);
      const csv = [header, ...rows]
        .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
        .join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `congress-trades-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Feed de transacciones</h2>
        <p className="mt-1 max-w-2xl text-xs text-ink/50 dark:text-slate-400">
          La etiqueta <span className="font-mono font-bold text-red-600 dark:text-red-500">⚠ Conflicto de interés</span>{" "}
          marca trades de un miembro que forma parte de un comité con competencia sobre el sector de la empresa
          operada (ej. Energy and Commerce + $MSFT). Es una señal heurística automática, no una acusación.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <select
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          value={filters.chamber ?? ""}
          onChange={(e) => updateFilter("chamber", e.target.value)}
        >
          <option value="">Ambas cámaras</option>
          <option value="house">Cámara de Representantes</option>
          <option value="senate">Senado</option>
        </select>
        <select
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          value={filters.party ?? ""}
          onChange={(e) => updateFilter("party", e.target.value)}
        >
          <option value="">Cualquier partido</option>
          <option value="D">Demócratas</option>
          <option value="R">Republicanos</option>
          <option value="I">Independientes</option>
        </select>
        <select
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
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
          defaultValue={filters.ticker ?? ""}
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          onChange={(e) => updateFilter("ticker", e.target.value.toUpperCase())}
        />
        <input
          type="text"
          placeholder="Miembro (ej. Pelosi)"
          defaultValue={filters.member ?? ""}
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          onChange={(e) => updateFilter("member", e.target.value)}
        />
        <input
          type="date"
          defaultValue={filters.date_from ?? ""}
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          onChange={(e) => updateFilter("date_from", e.target.value)}
        />
        <input
          type="date"
          defaultValue={filters.date_to ?? ""}
          className="rounded-md border border-ink/20 bg-paper px-2 py-1.5 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
          onChange={(e) => updateFilter("date_to", e.target.value)}
        />
        <a
          href={`${BASE}/feed.rss${rssQuery(filters)}`}
          target="_blank"
          rel="noreferrer"
          className="ml-auto flex items-center rounded-md border border-ink/20 px-3 py-1.5 font-mono text-xs uppercase tracking-wide dark:border-slate-100/20"
        >
          RSS
        </a>
        <button
          type="button"
          onClick={exportCsv}
          disabled={exporting}
          className="rounded-md border border-ink/20 px-3 py-1.5 font-mono text-xs uppercase tracking-wide disabled:opacity-50 dark:border-slate-100/20"
        >
          {exporting ? "Exportando…" : "Exportar CSV ↓"}
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-ink/10 dark:border-slate-100/10">
        <table className="w-full text-sm">
          <thead className="bg-paper-dim text-left font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:bg-slate-100/[0.03] dark:text-slate-400">
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
          <tbody className="divide-y divide-ink/10 dark:divide-slate-100/10">
            {trades.map((t) => {
              const conflict = detectConflict(t.ticker, committees[t.member_match_key] ?? null);
              const tier = highValueTier(t);
              return (
              <tr
                key={t.id}
                className={`border-l-[3px] ${tier ? "bg-amber-500/5" : ""}`}
                style={{ borderLeftColor: partyColor(t.party) }}
              >
                <td className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Link to={`/members/${t.member_match_key}`} className="hover:underline">
                      {t.member_name}
                    </Link>
                    <ConflictBadge match={conflict} />
                    <HighValueBadge tier={tier} />
                  </div>
                </td>
                <td className="px-3 py-2 text-ink/60 dark:text-slate-400">
                  {t.chamber === "house" ? "Cámara" : t.chamber === "senate" ? "Senado" : "—"}
                </td>
                <td className="px-3 py-2 font-mono font-medium">
                  <Link to={`/tickers/${t.ticker}`} className="hover:underline">
                    ${t.ticker}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <TransactionBadge type={t.transaction_type} />
                </td>
                <td className={`tabular-figures px-3 py-2 font-mono ${tier ? "font-bold" : ""}`}>
                  {formatAmountRange(t.amount_range_low, t.amount_range_high)}
                </td>
                <td className="px-3 py-2 font-mono text-ink/60 dark:text-slate-400">{formatDate(t.transaction_date)}</td>
                <td className="px-3 py-2 font-mono text-ink/60 dark:text-slate-400">{formatDate(t.disclosure_date)}</td>
                <td className="px-3 py-2 font-mono text-ink/60 dark:text-slate-400">
                  {t.disclosure_lag_days !== null ? `${t.disclosure_lag_days}d` : "—"}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
        {loading && <div className="p-3"><SkeletonRows rows={6} /></div>}
        {!loading && trades.length === 0 && (
          <p className="p-3 text-sm text-ink/60 dark:text-slate-400">Sin resultados para estos filtros.</p>
        )}
      </div>

      <div className="flex items-center justify-between font-mono text-xs text-ink/60 dark:text-slate-400">
        <span>
          {total.toLocaleString("es-ES")} resultados — mostrando {offset + 1}-
          {Math.min(offset + PAGE_SIZE, total)}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            className="rounded-md border border-ink/20 px-3 py-1 disabled:opacity-40 dark:border-slate-100/20"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            className="rounded-md border border-ink/20 px-3 py-1 disabled:opacity-40 dark:border-slate-100/20"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
