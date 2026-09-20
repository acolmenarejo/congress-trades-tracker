import type { ValueTier } from "../lib/highValue";

export default function HighValueBadge({ tier }: { tier: ValueTier }) {
  if (!tier) return null;
  if (tier === "very-high") {
    return (
      <span
        title="Operación en el tramo más alto de importe declarado (STOCK Act: $1,000,001+)"
        className="inline-flex items-center gap-1 rounded bg-gradient-to-r from-amber-500 to-amber-600 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-ledger shadow-sm"
      >
        💰💰 Importe muy alto
      </span>
    );
  }
  return (
    <span
      title="Operación en un tramo de importe alto (STOCK Act: $250,001+)"
      className="inline-flex items-center gap-1 rounded border border-amber-500 bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-buy-dim dark:text-buy"
    >
      💰 Importe alto
    </span>
  );
}
