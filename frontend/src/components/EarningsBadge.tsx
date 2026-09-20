import { EARNINGS_PROXIMITY_DAYS } from "../lib/earnings";

export default function EarningsBadge({ gapDays }: { gapDays: number | null }) {
  if (gapDays === null || Math.abs(gapDays) > EARNINGS_PROXIMITY_DAYS) return null;
  const label =
    gapDays === 0
      ? "el día de earnings"
      : gapDays > 0
        ? `${gapDays}d antes de earnings`
        : `${Math.abs(gapDays)}d después de earnings`;
  return (
    <span
      title="Operación cerca de la fecha de resultados de la empresa — más señal que una compra cualquiera."
      className="inline-flex items-center gap-1 rounded border border-sky-500/50 bg-sky-500/15 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-sky-700 dark:text-sky-400"
    >
      📅 {label}
    </span>
  );
}
