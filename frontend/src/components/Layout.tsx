import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useDarkMode } from "../hooks/useDarkMode";
import CapitolWatermark from "./CapitolWatermark";
import CommandPalette from "./CommandPalette";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/feed", label: "Feed" },
  { to: "/ranking", label: "Ranking" },
  { to: "/compliance", label: "Cumplimiento" },
];

export default function Layout() {
  const [dark, toggleDark] = useDarkMode();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="min-h-svh bg-paper text-ink dark:bg-ledger dark:text-slate-100">
      <header className="relative overflow-hidden border-b border-ink/10 dark:border-slate-100/10">
        <CapitolWatermark className="pointer-events-none absolute -right-4 top-1/2 h-28 w-auto -translate-y-1/2 text-ink/[0.05] dark:text-slate-100/[0.06]" />
        <div className="relative mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex flex-wrap items-center gap-8">
            <span className="font-serif text-xl font-semibold tracking-tight">
              Congress Trades Tracker
            </span>
            <nav className="flex flex-wrap gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-1.5 font-mono text-xs font-medium uppercase tracking-wide transition-colors ${
                      isActive
                        ? "bg-ink text-paper dark:bg-buy dark:text-ledger"
                        : "text-ink/60 hover:bg-ink/5 dark:text-slate-400 dark:hover:bg-slate-100/10"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-2 rounded-md border border-ink/20 px-3 py-1.5 font-mono text-xs text-ink/60 dark:border-slate-100/20 dark:text-slate-400"
            >
              Buscar
              <kbd className="rounded border border-ink/20 px-1 text-[10px] dark:border-slate-100/20">⌘K</kbd>
            </button>
            <button
              type="button"
              onClick={toggleDark}
              className="rounded-md border border-ink/20 px-3 py-1.5 font-mono text-xs dark:border-slate-100/20"
              aria-label="Cambiar tema"
            >
              {dark ? "☀ CLARO" : "☾ OSCURO"}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
