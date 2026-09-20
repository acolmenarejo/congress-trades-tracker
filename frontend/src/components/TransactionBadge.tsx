const LABELS: Record<string, string> = {
  purchase: "Compra",
  sale: "Venta",
  exchange: "Canje",
};

export default function TransactionBadge({ type }: { type: string | null }) {
  const isBuy = type === "purchase";
  const isSale = type === "sale";
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${
        isBuy
          ? "border-buy/40 bg-buy/10 text-buy-dim dark:text-buy"
          : isSale
            ? "border-sell/40 bg-sell/10 text-sell-dim dark:text-sell"
            : "border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
      }`}
    >
      {type ? (LABELS[type] ?? type) : "—"}
    </span>
  );
}
