export function formatUSD(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatAmountRange(low: number | null, high: number | null): string {
  if (low === null && high === null) return "—";
  if (high === null) return `> ${formatUSD(low)}`;
  if (low === high) return formatUSD(low);
  return `${formatUSD(low)} - ${formatUSD(high)}`;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value + "T00:00:00").toLocaleDateString("es-ES", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

const PARTY_COLORS: Record<string, string> = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#a855f7",
};

export function partyColor(party: string | null): string {
  return party ? PARTY_COLORS[party] ?? "#6b7280" : "#6b7280";
}
