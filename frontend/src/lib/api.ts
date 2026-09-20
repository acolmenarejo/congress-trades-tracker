// In dev, Vite proxies /api to the local backend (see vite.config.ts). In
// production, set VITE_API_BASE to the deployed backend's public URL.
const BASE = import.meta.env.VITE_API_BASE || "/api";

export interface Trade {
  id: number;
  unique_id: string;
  member_match_key: string;
  member_name: string;
  chamber: "house" | "senate" | null;
  party: "D" | "R" | "I" | null;
  state: string | null;
  ticker: string | null;
  asset_name: string | null;
  asset_type: string | null;
  transaction_type: "purchase" | "sale" | "exchange" | null;
  owner: string | null;
  amount_range_low: number | null;
  amount_range_high: number | null;
  amount_mid: number | null;
  transaction_date: string | null;
  disclosure_date: string | null;
  disclosure_lag_days: number | null;
  source: string;
  filing_url: string | null;
}

export interface TradeListResponse {
  total: number;
  items: Trade[];
}

export interface Kpis {
  total_trades: number;
  total_volume_estimate: number;
  active_filers: number;
}

export interface MemberRankingSummary {
  trade_count: number;
  volume_estimate: number;
  total_return_pct: number | null;
  annualized_return_pct: number | null;
  win_rate_pct: number | null;
  alpha_vs_sp500_pct: number | null;
  avg_disclosure_lag_days: number | null;
}

export interface Member {
  id: number;
  match_key: string;
  name: string;
  chamber: string | null;
  party: string | null;
  state: string | null;
  district: string | null;
  bioguide_id: string | null;
  committees: string | null;
  photo_url: string | null;
  ranking: MemberRankingSummary | null;
}

export interface MemberBestTrade {
  ticker: string;
  asset_name: string | null;
  transaction_type: "purchase" | "sale" | "exchange" | null;
  transaction_date: string | null;
  amount_range_low: number | null;
  amount_range_high: number | null;
  return_pct: number;
  entry_price: number | null;
  exit_price: number | null;
  closed: boolean;
  filing_url: string | null;
}

export interface MemberRanking {
  match_key: string;
  name: string;
  chamber: string | null;
  party: string | null;
  state: string | null;
  photo_url: string | null;
  trade_count: number;
  volume_estimate: number;
  total_return_pct: number | null;
  annualized_return_pct: number | null;
  win_rate_pct: number | null;
  alpha_vs_sp500_pct: number | null;
  avg_disclosure_lag_days: number | null;
  last_calculated: string | null;
}

export interface PricePoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface TickerSummary {
  ticker: string;
  trade_count: number;
  volume_estimate: number;
  distinct_members: number;
  buy_count: number;
  sell_count: number;
  trades: Trade[];
}

export interface TradeFilters {
  member?: string;
  ticker?: string;
  chamber?: string;
  party?: string;
  transaction_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | undefined;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json();
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// /trades caps `limit` at 500 server-side (HTTP 422 above that) — this pages
// through it to build a larger client-side sample for dashboards/exports.
export async function fetchTradeSample(
  maxItems: number,
  filters: TradeFilters = {},
): Promise<Trade[]> {
  const pageSize = 500;
  const out: Trade[] = [];
  let offset = 0;
  while (out.length < maxItems) {
    const res = await api.trades({ ...filters, limit: pageSize, offset });
    out.push(...res.items);
    if (res.items.length < pageSize || out.length >= res.total) break;
    offset += pageSize;
  }
  return out.slice(0, maxItems);
}

export const api = {
  health: () => getJSON<{ status: string }>("/health"),
  kpis: () => getJSON<Kpis>("/kpis"),
  trades: (filters: TradeFilters = {}) =>
    getJSON<TradeListResponse>(`/trades${qs(filters)}`),
  ranking: (sortBy = "total_return_pct", limit = 100) =>
    getJSON<MemberRanking[]>(`/members/ranking${qs({ sort_by: sortBy, limit })}`),
  member: (matchKey: string) => getJSON<Member>(`/members/${matchKey}`),
  memberTrades: (matchKey: string, limit = 500) =>
    getJSON<Trade[]>(`/members/${matchKey}/trades${qs({ limit })}`),
  memberBestTrades: (matchKey: string, limit = 5, worst = false) =>
    getJSON<MemberBestTrade[]>(`/members/${matchKey}/best-trades${qs({ limit, worst })}`),
  ticker: (ticker: string) => getJSON<TickerSummary>(`/tickers/${ticker}`),
  tickerPrices: (ticker: string, days = 180) =>
    getJSON<PricePoint[]>(`/tickers/${ticker}/prices${qs({ days })}`),
};
