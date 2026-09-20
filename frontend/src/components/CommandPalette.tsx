import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSearchIndex, type SearchItem } from "../hooks/useSearchIndex";
import { partyColor } from "../lib/format";

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { items } = useSearchIndex();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items.slice(0, 8);
    return items
      .filter((it) => (it.kind === "member" ? it.name.toLowerCase().includes(q) : it.ticker.toLowerCase().includes(q)))
      .slice(0, 20);
  }, [items, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  function go(item: SearchItem) {
    navigate(item.kind === "member" ? `/members/${item.matchKey}` : `/tickers/${item.ticker}`);
    onClose();
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 pt-24 backdrop-blur-sm dark:bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-lg border border-ink/10 bg-paper shadow-2xl dark:border-slate-100/10 dark:bg-ledger"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            }
            if (e.key === "Enter" && results[active]) go(results[active]);
          }}
          placeholder="Buscar congresista o ticker…"
          className="w-full border-b border-ink/10 bg-transparent px-4 py-3 font-mono text-sm outline-none dark:border-slate-100/10"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {results.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink/50 dark:text-slate-400">Sin resultados.</li>
          )}
          {results.map((item, i) => (
            <li key={item.kind === "member" ? `m:${item.matchKey}` : `t:${item.ticker}`}>
              <button
                type="button"
                onClick={() => go(item)}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-center gap-2 px-4 py-2 text-left text-sm ${
                  i === active ? "bg-ink/5 dark:bg-slate-100/10" : ""
                }`}
              >
                {item.kind === "member" ? (
                  <>
                    <span
                      className="inline-block h-2 w-2 shrink-0 rounded-full"
                      style={{ background: partyColor(item.party) }}
                    />
                    {item.name}
                  </>
                ) : (
                  <span className="font-mono font-medium">${item.ticker}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
