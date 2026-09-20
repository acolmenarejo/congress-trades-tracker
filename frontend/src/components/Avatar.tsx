import { useState } from "react";

export default function Avatar({
  photoUrl,
  name,
  size = 32,
}: {
  photoUrl: string | null;
  name: string;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const initial = name.charAt(0).toUpperCase();

  if (!photoUrl || failed) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full bg-slate-200 font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
        style={{ width: size, height: size, fontSize: size * 0.4 }}
      >
        {initial}
      </div>
    );
  }
  return (
    <img
      src={photoUrl}
      alt={name}
      onError={() => setFailed(true)}
      className="shrink-0 rounded-full object-cover"
      style={{ width: size, height: size }}
    />
  );
}
