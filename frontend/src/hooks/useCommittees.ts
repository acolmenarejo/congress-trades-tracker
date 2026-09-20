import { useEffect, useState } from "react";
import { api } from "../lib/api";

// Module-level cache shared across every page that needs member committees —
// there's no bulk endpoint, so this avoids refetching the same member twice
// across Feed/Dashboard/TickerPage in one session.
const cache = new Map<string, string | null>();

export function useCommitteesForMembers(matchKeys: string[]): Record<string, string | null> {
  const [, bump] = useState(0);
  const key = Array.from(new Set(matchKeys)).sort().join(",");

  useEffect(() => {
    const missing = Array.from(new Set(matchKeys)).filter((k) => k && !cache.has(k));
    if (missing.length === 0) return;
    Promise.all(
      missing.map((k) =>
        api
          .member(k)
          .then((m) => cache.set(k, m.committees))
          .catch(() => cache.set(k, null)),
      ),
    ).then(() => bump((n) => n + 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const result: Record<string, string | null> = {};
  for (const k of matchKeys) result[k] = cache.get(k) ?? null;
  return result;
}
