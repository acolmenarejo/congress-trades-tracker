import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type SetupSignal } from "../lib/api";
import { formatDate } from "../lib/format";

const STATUS: Record<SetupSignal["status"], { label: string; cls: string }> = {
  target: { label: "Objetivo ✓", cls: "text-emerald-700 dark:text-emerald-400" },
  stop: { label: "Stop ✗", cls: "text-sell dark:text-sell" },
  time: { label: "Cerrada (1 mes)", cls: "text-ink/70 dark:text-slate-300" },
  open: { label: "Abierta", cls: "text-buy-dim dark:text-buy" },
};

function pct(x: number | null) {
  return x === null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}

function price(x: number) {
  return x >= 100 ? `$${x.toFixed(0)}` : `$${x.toFixed(2)}`;
}

// Live track record of the technical setup alerts sent by Telegram
// (backend/app/setups.py): did each one reach its target or its stop?
export default function SetupSignalsCard() {
  const [signals, setSignals] = useState<SetupSignal[] | null>(null);

  useEffect(() => {
    api.setupSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  if (signals !== null && signals.length === 0) return null;

  const closed = (signals ?? []).filter((s) => s.status !== "open");
  const wins = closed.filter((s) => (s.return_pct ?? 0) > 0).length;
  const avg = closed.length ? closed.reduce((a, s) => a + (s.return_pct ?? 0), 0) / closed.length : null;

  return (
    <div className="rounded-lg border border-ink/10 p-4 dark:border-slate-100/10">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-serif text-base font-semibold">Señales técnicas: resultado real</h3>
        {closed.length > 0 && (
          <span className="font-mono text-xs text-ink/60 dark:text-slate-400">
            {wins}/{closed.length} en positivo · media {pct(avg)} (backtest: +1,5%)
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-ink/60 dark:text-slate-400">
        Cada alerta de Telegram (señal por nota ≥ 70 o ruptura) con su entrada, objetivo y stop. Se cierra al tocar uno de los dos o al mes.
      </p>
      {signals === null && <p className="text-sm text-ink/60 dark:text-slate-400">Cargando…</p>}
      {signals !== null && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="text-left font-mono text-xs uppercase tracking-wide text-ink/50 dark:text-slate-500">
                <th className="py-1 pr-3 font-normal">Ticker</th>
                <th className="py-1 pr-3 font-normal">Señal</th>
                <th className="py-1 pr-3 font-normal">Entrada → objetivo / stop</th>
                <th className="py-1 pr-3 font-normal">Estado</th>
                <th className="py-1 text-right font-normal">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => {
                const st = STATUS[s.status];
                return (
                  <tr key={`${s.ticker}-${s.signal_date}`} className="border-t border-ink/5 dark:border-slate-100/5">
                    <td className="py-1.5 pr-3 font-medium">
                      <Link to={`/tickers/${s.ticker}`} className="hover:underline">
                        {s.ticker}
                      </Link>
                      <span className="ml-1 font-mono text-xs text-ink/50 dark:text-slate-500">
                        {s.kind === "breakout" ? "ruptura" : s.score.toFixed(0)}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{formatDate(s.signal_date)}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">
                      {price(s.entry)} → {price(s.target)} / {price(s.stop)}
                    </td>
                    <td className={`py-1.5 pr-3 text-xs font-medium ${st.cls}`}>
                      {st.label}
                      {s.exit_date && (
                        <span className="ml-1 font-normal text-ink/50 dark:text-slate-500">
                          {formatDate(s.exit_date)}
                        </span>
                      )}
                    </td>
                    <td className={`py-1.5 text-right font-mono ${(s.return_pct ?? 0) >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-sell"}`}>
                      {pct(s.return_pct)}
                      {s.status === "open" && <span className="ml-1 text-xs text-ink/50 dark:text-slate-500">hoy</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
