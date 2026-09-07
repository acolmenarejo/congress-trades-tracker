import { useEffect, useState } from "react";

function getInitial(): boolean {
  try {
    const stored = localStorage.getItem("theme");
    if (stored) return stored === "dark";
  } catch {
    // ignore
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function useDarkMode(): [boolean, () => void] {
  const [dark, setDark] = useState(getInitial);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      // ignore
    }
  }, [dark]);

  return [dark, () => setDark((d) => !d)];
}
