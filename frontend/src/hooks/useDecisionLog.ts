import { useCallback, useEffect, useState } from "react";

export type DecisionAction = "compré" | "pasé" | "vendí";

export interface DecisionEntry {
  id: string;
  tradeId: number;
  ticker: string;
  memberName: string;
  action: DecisionAction;
  stakeUsd: number | null;
  entryPrice: number | null;
  loggedDate: string; // YYYY-MM-DD
  note: string;
  createdAt: string;
}

const STORAGE_KEY = "decision-log";

function load(): DecisionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save(entries: DecisionEntry[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // ignore
  }
}

// Personal decision journal, single-user/localStorage like the watchlist —
// closes the loop between "an alert fired" and "what I actually did about
// it", so you can compare your real track record against the simulator's
// hypothetical one.
export function useDecisionLog() {
  const [entries, setEntries] = useState<DecisionEntry[]>(load);

  useEffect(() => {
    function onChange() {
      setEntries(load());
    }
    window.addEventListener("decision-log-changed", onChange);
    return () => window.removeEventListener("decision-log-changed", onChange);
  }, []);

  const add = useCallback((entry: Omit<DecisionEntry, "id" | "createdAt">) => {
    const current = load();
    const next: DecisionEntry = { ...entry, id: crypto.randomUUID(), createdAt: new Date().toISOString() };
    save([next, ...current]);
    window.dispatchEvent(new Event("decision-log-changed"));
  }, []);

  const remove = useCallback((id: string) => {
    const current = load();
    save(current.filter((e) => e.id !== id));
    window.dispatchEvent(new Event("decision-log-changed"));
  }, []);

  return { entries, add, remove };
}
