import type { ConflictMatch } from "../lib/conflictOfInterest";

export default function ConflictBadge({ match }: { match: ConflictMatch | null }) {
  if (!match) return null;
  return (
    <span
      title={`Miembro de: ${match.committees.join(" · ")} (competencia sobre ${match.sectors.join(
        ", ",
      )}). Señal heurística basada en comités públicos y sector de la empresa — no implica ilegalidad ni mala conducta.`}
      className="inline-flex items-center gap-1 rounded bg-red-600 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-white shadow-sm dark:bg-red-500"
    >
      ⚠ Conflicto de interés
    </span>
  );
}
