import type { KalshiCompanyEvent } from "../lib/api";

const pct = (p: number | null) => (p === null ? "—" : `${Math.round(p * 100)}%`);

function Move({ p, prev }: { p: number | null; prev: number | null }) {
  if (p === null || prev === null || prev <= 0) return null;
  const d = Math.round((p - prev) * 100);
  if (Math.abs(d) < 5) return null;
  return (
    <span className={`ml-1 text-[11px] ${d > 0 ? "text-buy-dim dark:text-buy" : "text-sell-dim dark:text-sell"}`}>
      ({d > 0 ? "+" : ""}
      {d} en 24 h)
    </span>
  );
}

// Kalshi markets on this company's next reported KPIs and earnings call
// (backend/app/kalshi_company.py). Renders nothing when Kalshi has none.
export default function KalshiCompanyCard({ events }: { events: KalshiCompanyEvent[] }) {
  if (events.length === 0) return null;
  const kpis = events.filter((e) => e.kind === "kpi");
  const calls = events.filter((e) => e.kind === "mention");
  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <h3 className="font-serif text-lg font-semibold">Qué espera Kalshi del próximo dato</h3>
      <p className="mb-3 text-xs text-ink/50 dark:text-slate-400">
        Apuestas con dinero real sobre las cifras que la empresa va a publicar. Hay poco dinero en cada una: tómalo
        como pista. Si alguien compra cuando el mercado espera un dato flojo, la compra va contra corriente.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {kpis.map((e) => (
          <div key={e.event} className="rounded border border-ink/10 p-3 text-sm dark:border-slate-100/10">
            <div className="flex items-start justify-between gap-2">
              <a href={e.url} target="_blank" rel="noreferrer" className="font-medium underline">
                {e.title}
              </a>
              {e.lean === "weak" && (
                <span className="shrink-0 rounded bg-sell/15 px-2 py-0.5 font-mono text-[11px] font-bold uppercase text-sell-dim dark:text-sell">
                  dato flojo
                </span>
              )}
            </div>
            {e.median_label && (
              <p className="font-mono text-sm font-bold">Lo más probable: ≈ {e.median_label}</p>
            )}
            {e.lean_text && <p className="mt-1 text-ink/70 dark:text-slate-300">{e.lean_text}</p>}
            <ul className="mt-2 space-y-0.5 font-mono text-xs">
              {e.markets.map((m) => (
                <li key={m.ticker} className="flex justify-between gap-2">
                  <span>{m.label}</span>
                  <span>
                    {pct(m.p)}
                    <Move p={m.p} prev={m.prev} />
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-ink/50 dark:text-slate-400">{e.oi.toLocaleString("es-ES")} contratos abiertos</p>
          </div>
        ))}
        {calls.map((e) => (
          <div key={e.event} className="rounded border border-ink/10 p-3 text-sm dark:border-slate-100/10">
            <a href={e.url} target="_blank" rel="noreferrer" className="font-medium underline">
              Qué dirán en la conferencia de resultados
            </a>
            {e.sub_title && <p className="text-xs text-ink/50 dark:text-slate-400">{e.sub_title}</p>}
            <ul className="mt-2 space-y-0.5 font-mono text-xs">
              {e.markets.map((m) => (
                <li key={m.ticker} className="flex justify-between gap-2">
                  <span>«{m.label}»</span>
                  <span>
                    {pct(m.p)}
                    <Move p={m.p} prev={m.prev} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
