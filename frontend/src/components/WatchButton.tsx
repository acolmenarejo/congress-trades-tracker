import { useWatchlist, type WatchItem } from "../hooks/useWatchlist";

export default function WatchButton({ item, size = "sm" }: { item: WatchItem; size?: "sm" | "md" }) {
  const { isWatched, toggle } = useWatchlist();
  const watched = isWatched(item.kind, item.key);

  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(item);
      }}
      title={watched ? "Quitar de mi watchlist" : "Añadir a mi watchlist"}
      aria-pressed={watched}
      className={`inline-flex shrink-0 items-center justify-center rounded transition-colors ${
        size === "sm" ? "h-5 w-5 text-sm" : "h-7 w-7 text-lg"
      } ${watched ? "text-buy" : "text-ink/25 hover:text-ink/50 dark:text-slate-600 dark:hover:text-slate-400"}`}
    >
      {watched ? "★" : "☆"}
    </button>
  );
}
