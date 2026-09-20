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

// Same hues as lib/chartTheme.ts (dark-mode variants) so the party accent on
// list rows/cards matches the color used for that party in the charts.
const PARTY_COLORS: Record<string, string> = {
  D: "#3987e5",
  R: "#e66767",
  I: "#9085e9",
};

export function partyColor(party: string | null): string {
  return party ? PARTY_COLORS[party] ?? "#89877f" : "#89877f";
}

export function partyLabel(party: string | null): string {
  return party === "D" ? "Demócrata" : party === "R" ? "Republicano" : party === "I" ? "Independiente" : "—";
}
