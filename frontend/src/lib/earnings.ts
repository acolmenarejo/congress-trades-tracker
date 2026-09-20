export const EARNINGS_PROXIMITY_DAYS = 20;

// Positive = trade happened N days BEFORE the nearest earnings date;
// negative = N days after. null = no earnings data cached for this ticker
// (FMP's free plan only covers a curated large-cap list — see
// backend/app/earnings.py).
export function nearestEarningsGapDays(earningsDates: string[], tradeDate: string): number | null {
  if (earningsDates.length === 0) return null;
  let best: number | null = null;
  const tradeMs = new Date(tradeDate).getTime();
  for (const d of earningsDates) {
    const diffDays = Math.round((new Date(d).getTime() - tradeMs) / 86_400_000);
    if (best === null || Math.abs(diffDays) < Math.abs(best)) best = diffDays;
  }
  return best;
}
