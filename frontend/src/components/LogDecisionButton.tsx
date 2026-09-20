import { useState } from "react";
import { useDecisionLog, type DecisionAction } from "../hooks/useDecisionLog";
import type { Trade } from "../lib/api";

export default function LogDecisionButton({ trade }: { trade: Trade }) {
  const { add } = useDecisionLog();
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<DecisionAction>("compré");
  const [stake, setStake] = useState("1000");
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

  function save() {
    add({
      tradeId: trade.id,
      ticker: trade.ticker ?? "",
      memberName: trade.member_name,
      action,
      stakeUsd: action === "pasé" ? null : stake ? Number(stake) : null,
      entryPrice: price ? Number(price) : null,
      loggedDate: new Date().toISOString().slice(0, 10),
      note,
    });
    setSaved(true);
    setTimeout(() => {
      setOpen(false);
      setSaved(false);
    }, 700);
  }

  if (!trade.ticker) return null;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        title="Anotar qué hice yo con esto"
        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-ink/25 hover:text-ink/60 dark:text-slate-600 dark:hover:text-slate-300"
      >
        📝
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-6 z-40 w-64 rounded-lg border border-ink/15 bg-paper p-3 shadow-xl dark:border-slate-100/15 dark:bg-ledger"
        >
          {saved ? (
            <p className="text-center text-sm text-buy-dim dark:text-buy">Guardado ✓</p>
          ) : (
            <div className="space-y-2">
              <p className="font-mono text-[11px] uppercase tracking-wide text-ink/50 dark:text-slate-400">
                ${trade.ticker} — {trade.member_name}
              </p>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value as DecisionAction)}
                className="w-full rounded border border-ink/20 bg-paper px-2 py-1 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
              >
                <option value="compré">Compré</option>
                <option value="vendí">Vendí</option>
                <option value="pasé">Pasé</option>
              </select>
              {action !== "pasé" && (
                <>
                  <input
                    type="number"
                    placeholder="Importe ($)"
                    value={stake}
                    onChange={(e) => setStake(e.target.value)}
                    className="w-full rounded border border-ink/20 bg-paper px-2 py-1 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
                  />
                  <input
                    type="number"
                    placeholder="Precio de entrada (opcional)"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    className="w-full rounded border border-ink/20 bg-paper px-2 py-1 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
                  />
                </>
              )}
              <textarea
                placeholder="Nota (opcional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                className="w-full rounded border border-ink/20 bg-paper px-2 py-1 text-sm dark:border-slate-100/20 dark:bg-slate-100/5"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setOpen(false)} className="font-mono text-xs text-ink/50 dark:text-slate-400">
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={save}
                  className="rounded bg-ink px-2 py-1 font-mono text-xs text-paper dark:bg-buy dark:text-ledger"
                >
                  Guardar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </span>
  );
}
