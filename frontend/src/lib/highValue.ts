// STOCK Act disclosures are reported in bands, not exact amounts — these
// thresholds line up with real reporting bands ($250,001-$500,000 and
// $1,000,001-$5,000,000 are both actual disclosure tiers), so "high value"
// here means "in a band regulators themselves treat as a bigger deal".
export const HIGH_VALUE_THRESHOLD = 250_000;
export const VERY_HIGH_VALUE_THRESHOLD = 1_000_000;

export type ValueTier = "very-high" | "high" | null;

export function tradeValue(t: { amount_range_low: number | null; amount_mid: number | null }): number {
  return t.amount_range_low ?? t.amount_mid ?? 0;
}

export function highValueTier(t: { amount_range_low: number | null; amount_mid: number | null }): ValueTier {
  const v = tradeValue(t);
  if (v >= VERY_HIGH_VALUE_THRESHOLD) return "very-high";
  if (v >= HIGH_VALUE_THRESHOLD) return "high";
  return null;
}
