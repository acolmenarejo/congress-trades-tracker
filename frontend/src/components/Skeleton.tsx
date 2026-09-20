export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-ink/10 dark:bg-slate-100/10 ${className}`} />;
}

export function SkeletonRows({ rows = 5, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
