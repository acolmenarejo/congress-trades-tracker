import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PolymarketAlert } from "../lib/api";
import { formatUSD } from "../lib/format";

export default function PolymarketTeaser() {
  const [alerts, setAlerts] = useState<PolymarketAlert[] | null>(null);

  useEffect(() => {
    api.polymarketWhaleBets(3).then(setAlerts).catch(() => setAlerts([]));
  }, []);

  if (alerts !== null && alerts.length === 0) return null;

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-serif text-base font-semibold">Polymarket</h3>
        <Link to="/polymarket" className="font-mono text-xs uppercase tracking-wide text-buy-dim hover:underline dark:text-buy">
          Ver todo →
        </Link>
      </div>
      {alerts === null && <p className="text-sm text-ink/60 dark:text-slate-400">Cargando…</p>}
      {alerts !== null && (
        <ul className="space-y-1.5">
          {alerts.map((a) => (
            <li key={a.id} className="text-sm">
              <span className="font-medium">{a.market_question}</span>{" "}
              <span className="font-mono text-xs text-ink/60 dark:text-slate-400">
                — {a.side === "BUY" ? "compró" : "vendió"} "{a.outcome}" por {formatUSD(a.size_usd)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
