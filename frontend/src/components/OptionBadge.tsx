export default function OptionBadge({ assetType }: { assetType: string | null }) {
  if (assetType !== "Stock Option") return null;
  return (
    <span
      title="Apuesta apalancada — históricamente una señal de mayor convicción que una compra de acciones normal."
      className="inline-flex items-center gap-1 rounded border border-violet-500/50 bg-violet-500/15 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide text-violet-700 dark:text-violet-400"
    >
      ⚡ Opción
    </span>
  );
}
