import { useEffect, useState } from "react";
import { api, fetchTradeSample } from "../lib/api";

export interface SearchMember {
  kind: "member";
  matchKey: string;
  name: string;
  party: string | null;
}

export interface SearchTicker {
  kind: "ticker";
  ticker: string;
}

export type SearchItem = SearchMember | SearchTicker;

let cache: SearchItem[] | null = null;

// Best-effort index built from the ranking (most active members) and a
// large recent-trades sample (covers most-traded tickers) — there's no
// "list all members/tickers" endpoint, so this favors what people actually
// search for over completeness.
export function useSearchIndex() {
  const [items, setItems] = useState<SearchItem[]>(cache ?? []);
  const [loading, setLoading] = useState(!cache);

  useEffect(() => {
    if (cache) return;
    setLoading(true);
    Promise.all([api.ranking("total_return_pct", 100), fetchTradeSample(1000)])
      .then(([ranking, sample]) => {
        const members = new Map<string, SearchMember>();
        for (const r of ranking) {
          members.set(r.match_key, { kind: "member", matchKey: r.match_key, name: r.name, party: r.party });
        }
        const tickers = new Set<string>();
        for (const t of sample) {
          if (!members.has(t.member_match_key)) {
            members.set(t.member_match_key, {
              kind: "member",
              matchKey: t.member_match_key,
              name: t.member_name,
              party: t.party,
            });
          }
          if (t.ticker) tickers.add(t.ticker);
        }
        const built: SearchItem[] = [
          ...members.values(),
          ...Array.from(tickers).map((ticker): SearchTicker => ({ kind: "ticker", ticker })),
        ];
        cache = built;
        setItems(built);
      })
      .finally(() => setLoading(false));
  }, []);

  return { items, loading };
}
