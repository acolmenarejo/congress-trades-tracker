import { useCallback, useEffect, useState } from "react";

export interface WatchItem {
  kind: "member" | "ticker";
  key: string; // match_key or ticker symbol
  label: string; // display name
}

const STORAGE_KEY = "watchlist";

function load(): WatchItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save(items: WatchItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // ignore (private mode, storage disabled, etc.)
  }
}

// This is a personal, single-user tool (no accounts/backend) — the
// watchlist lives in this browser's localStorage. Every mounted instance
// re-reads on a "watchlist-changed" event so all components stay in sync
// without prop drilling or a context provider.
export function useWatchlist() {
  const [items, setItems] = useState<WatchItem[]>(load);

  useEffect(() => {
    function onChange() {
      setItems(load());
    }
    window.addEventListener("watchlist-changed", onChange);
    return () => window.removeEventListener("watchlist-changed", onChange);
  }, []);

  const isWatched = useCallback(
    (kind: WatchItem["kind"], key: string) => items.some((i) => i.kind === kind && i.key === key),
    [items],
  );

  const toggle = useCallback((item: WatchItem) => {
    const current = load();
    const exists = current.some((i) => i.kind === item.kind && i.key === item.key);
    const next = exists
      ? current.filter((i) => !(i.kind === item.kind && i.key === item.key))
      : [...current, item];
    save(next);
    window.dispatchEvent(new Event("watchlist-changed"));
  }, []);

  return { items, isWatched, toggle };
}
