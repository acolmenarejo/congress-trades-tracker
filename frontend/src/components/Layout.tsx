import { NavLink, Outlet } from "react-router-dom";
import { useDarkMode } from "../hooks/useDarkMode";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/feed", label: "Feed" },
  { to: "/ranking", label: "Ranking" },
];

export default function Layout() {
  const [dark, toggleDark] = useDarkMode();

  return (
    <div className="min-h-svh bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold">
              Congress Trades Tracker
            </span>
            <nav className="flex gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <button
            type="button"
            onClick={toggleDark}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700"
            aria-label="Cambiar tema"
          >
            {dark ? "☀️ Claro" : "🌙 Oscuro"}
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
