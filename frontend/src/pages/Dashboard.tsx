import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Kpis, type Trade } from "../lib/api";
import { useDarkMode } from "../hooks/useDarkMode";
import KpiCards from "../components/KpiCards";
import VolumeByMonthChart from "../components/charts/VolumeByMonthChart";
import TopTickersChart from "../components/charts/TopTickersChart";
import PartySplitChart from "../components/charts/PartySplitChart";
import { formatAmountRange, formatDate } from "../lib/format";

export default function Dashboard() {
  const [dark] = useDarkMode();
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [recent, setRecent] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.kpis().then(setKpis).catch(() => setError("No se pudo conectar con la API"));
    // A larger sample for the charts below; the feed page has full filtering/pagination.
    api
      .trades({ limit: 500 })
      .then((res) => setTrades(res.items))
      .catch(() => setError("No se pudo conectar con la API"));
    api
      .trades({ limit: 8 })
      .then((res) => setRecent(res.items))
      .catch(() => {});
  }, []);

  if (error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        {error}. ¿Está corriendo el backend en http://127.0.0.1:8000?
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {kpis && <KpiCards kpis={kpis} />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <VolumeByMonthChart trades={trades} dark={dark} />
        <TopTickersChart trades={trades} dark={dark} />
      </div>
      <PartySplitChart trades={trades} dark={dark} />

      <div className="rounded-lg border border-slate-200 dark:border-slate-800">
        <div className="flex items-center justify-between border-b border-slate-200 p-4 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            Últimas transacciones
          </h3>
          <Link to="/feed" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
            Ver feed completo →
          </Link>
        </div>
        <ul className="divide-y divide-slate-200 dark:divide-slate-800">
          {recent.map((t) => (
            <li key={t.id} className="flex items-center justify-between p-3 text-sm">
              <div>
                <Link
                  to={`/members/${t.member_match_key}`}
                  className="font-medium hover:underline"
                >
                  {t.member_name}
                </Link>
                <span className="text-slate-500 dark:text-slate-400">
                  {" "}
                  · {t.transaction_type === "purchase" ? "Compró" : "Vendió"} ${t.ticker}
                </span>
              </div>
              <div className="text-right text-slate-500 dark:text-slate-400">
                <div>{formatAmountRange(t.amount_range_low, t.amount_range_high)}</div>
                <div>{formatDate(t.disclosure_date)}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
