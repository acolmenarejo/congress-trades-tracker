import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type InsiderBuy, type InsiderGroup } from "../lib/api";
import { SkeletonRows } from "../components/Skeleton";
import { formatDate, formatUSD } from "../lib/format";

function posLabel(b: InsiderBuy): string | null {
  if (b.position_increase_pct === null) return null;
  if (b.position_increase_pct < 0) return "posición nueva";
  return `+${b.position_increase_pct.toFixed(0)}% su posición`;
}

export default function Insiders() {
  const [onlyRelevant, setOnlyRelevant] = useState(true);
  const [days, setDays] = useState(60);
  const [groups, setGroups] = useState<InsiderGroup[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .insiders(days, onlyRelevant)
      .then((g) => alive && setGroups(g))
      .catch(() => alive && setGroups([]));
    return () => {
      alive = false;
    };
  }, [days, onlyRelevant]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold">Compras de directivos</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink/60 dark:text-slate-400">
          Compras en mercado abierto con su propio dinero (SEC Form 4). "Relevantes" aplica el mismo filtro que
          las alertas de Telegram: directivos o consejeros de empresas operativas que aumentan su posición un
          20% o más (CEO/CFO 10%), o 3 o más directivos comprando en 30 días. Fuera fondos, accionistas del 10%,
          acciones de menos de 5 $ y compras en la salida a bolsa.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div className="flex rounded-md border border-ink/20 dark:border-slate-100/20">
          {[
            [true, "Relevantes"],
            [false, "Todas"],
          ].map(([v, label]) => (
            <button
              key={String(v)}
              type="button"
              onClick={() => {
                setGroups(null);
                setOnlyRelevant(v as boolean);
              }}
              className={`px-3 py-1.5 font-mono text-xs uppercase ${onlyRelevant === v ? "bg-ink text-paper dark:bg-buy dark:text-ledger" : ""}`}
            >
              {label as string}
            </button>
          ))}
        </div>
        <select
          value={days}
          onChange={(e) => {
            setGroups(null);
            setDays(Number(e.target.value));
          }}
          className="rounded-md border border-ink/20 bg-transparent px-2 py-1.5 font-mono text-xs dark:border-slate-100/20"
        >
          {[30, 60, 90, 180].map((d) => (
            <option key={d} value={d}>
              Últimos {d} días
            </option>
          ))}
        </select>
      </div>

      {groups === null && <SkeletonRows rows={6} />}
      {groups !== null && groups.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink/20 p-6 text-sm text-ink/60 dark:border-slate-100/20 dark:text-slate-400">
          Ninguna compra en este periodo.
        </div>
      )}

      {groups !== null && groups.length > 0 && (
        <ul className="space-y-3">
          {groups.map((g) => (
            <li key={g.ticker} className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <Link to={`/tickers/${g.ticker}`} className="font-mono text-base font-semibold hover:underline">
                    {g.ticker}
                  </Link>
                  <span className="text-sm text-ink/70 dark:text-slate-300">{g.company}</span>
                  {g.n_insiders >= 3 && (
                    <span className="rounded bg-buy/15 px-1.5 py-0.5 font-mono text-[11px] uppercase text-buy-dim dark:text-buy">
                      {g.n_insiders} directivos
                    </span>
                  )}
                </div>
                <span className="font-mono text-sm">
                  {formatUSD(g.total_usd)} · {formatDate(g.last_date)}
                </span>
              </div>
              <ul className="mt-2 space-y-1">
                {g.buys.map((b, i) => {
                  const pos = posLabel(b);
                  return (
                    <li key={i} className="flex flex-wrap justify-between gap-2 text-sm">
                      <span>
                        <span className="font-medium">{b.insider}</span>{" "}
                        <span className="text-ink/60 dark:text-slate-400">({b.role})</span>
                        {!b.company_insider && (
                          <span className="ml-1 font-mono text-[11px] text-ink/40 dark:text-slate-500">filtrado</span>
                        )}
                      </span>
                      <span className="font-mono text-xs text-ink/70 dark:text-slate-300">
                        {formatUSD(b.value_usd)}
                        {b.avg_price ? ` a $${b.avg_price.toFixed(2)}` : ""}
                        {pos ? ` · ${pos}` : ""} · {formatDate(b.date)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
