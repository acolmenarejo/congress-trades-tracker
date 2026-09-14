import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import type { PricePoint, Trade } from "../../lib/api";
import { chartColors } from "../../lib/chartTheme";
import { formatAmountRange, formatDate } from "../../lib/format";

// Status colors (fixed, never themed) per the dataviz palette: up/down candles
// are a state signal, not a categorical series.
const UP_COLOR = "#0ca30c";
const DOWN_COLOR = "#d03b3b";

interface CandleDatum {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  range: [number, number];
}

interface TradeMarker {
  date: string;
  price: number;
  type: string | null;
  member: string;
  transactionDate: string | null;
  amount: string;
}

function CandlestickShape(props: any) {
  const { x, y, width, height, payload } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    payload: CandleDatum;
  };
  const { open, close, high, low } = payload;
  if (high === low || height <= 0) return null;

  const priceToY = (price: number) => y + (height * (high - price)) / (high - low);
  const openY = priceToY(open);
  const closeY = priceToY(close);
  const isUp = close >= open;
  const color = isUp ? UP_COLOR : DOWN_COLOR;
  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 1);
  const bodyWidth = Math.max(width * 0.6, 2);
  const bodyX = x + (width - bodyWidth) / 2;
  const wickX = x + width / 2;

  return (
    <g>
      <line x1={wickX} x2={wickX} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={bodyX} y={bodyTop} width={bodyWidth} height={bodyHeight} fill={color} />
    </g>
  );
}

const MAX_MARKER_SNAP_DAYS = 5;

// Snap a trade to the nearest candle within the chart's own date range — a
// trade far outside the visible window (e.g. a 2019 trade on a 6-month chart)
// must be dropped, not clamped to the nearest edge candle (that piles up
// unrelated markers on one date and drags the x-axis domain into nonsense).
function nearestCandle(prices: PricePoint[], targetDate: string): { date: string; close: number } | null {
  let best: PricePoint | null = null;
  let bestDiffDays = Infinity;
  const targetMs = new Date(targetDate).getTime();
  for (const p of prices) {
    if (p.close === null) continue;
    const diffDays = Math.abs(new Date(p.date).getTime() - targetMs) / 86_400_000;
    if (diffDays < bestDiffDays) {
      bestDiffDays = diffDays;
      best = p;
    }
  }
  if (!best || bestDiffDays > MAX_MARKER_SNAP_DAYS) return null;
  return { date: best.date, close: best.close as number };
}

/**
 * Trade markers are drawn manually with useXAxisScale/useYAxisScale instead
 * of <Scatter>. Recharts' Scatter builds its own category scale from the
 * size of *its own* `data` array rather than reusing the chart's shared
 * category axis, so with far fewer trades than price candles every marker
 * collapsed onto the left edge of the chart regardless of its real date
 * (confirmed against real data for $DASH: correct per-trade dates going into
 * Scatter, wrong pixels out). Reading the axes' own scale functions here
 * sidesteps that entirely — same coordinates the candlesticks use.
 *
 * No mouse handlers on the polygons themselves: Recharts' own full-chart
 * hover-tracking overlay sits above them and swallows the events before they
 * arrive. Hover is instead resolved in the shared <Tooltip> below by matching
 * its already-correctly-tracked active date against this same marker list.
 */
function TradeMarkersLayer({ markers }: { markers: TradeMarker[] }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale) return null;

  return (
    <g>
      {markers.map((m, i) => {
        const cx = xScale(m.date, { position: "middle" });
        const cy = yScale(m.price);
        if (cx === undefined || cy === undefined) return null;
        const isBuy = m.type === "purchase";
        const color = isBuy ? UP_COLOR : DOWN_COLOR;
        const size = 6;
        const points = isBuy
          ? `${cx},${cy - size} ${cx - size},${cy + size} ${cx + size},${cy + size}`
          : `${cx},${cy + size} ${cx - size},${cy - size} ${cx + size},${cy - size}`;
        return <polygon key={i} points={points} fill={color} stroke="white" strokeWidth={0.5} />;
      })}
    </g>
  );
}

export default function CandlestickChart({
  prices,
  trades,
  dark,
}: {
  prices: PricePoint[];
  trades: Trade[];
  dark: boolean;
}) {
  const colors = chartColors(dark);

  const candles: CandleDatum[] = prices
    .filter((p) => p.open !== null && p.high !== null && p.low !== null && p.close !== null)
    .map((p) => ({
      date: p.date,
      open: p.open as number,
      high: p.high as number,
      low: p.low as number,
      close: p.close as number,
      range: [p.low as number, p.high as number],
    }));

  const markersByDate = new Map<string, number>();
  const markers: TradeMarker[] = trades
    .filter((t) => t.transaction_date)
    .map((t): TradeMarker | null => {
      const snapped = nearestCandle(prices, t.transaction_date as string);
      if (!snapped) return null;
      // Jitter stacked markers on the same date so each stays visible
      // instead of perfectly overlapping.
      const occurrence = markersByDate.get(snapped.date) ?? 0;
      markersByDate.set(snapped.date, occurrence + 1);
      const jitter = occurrence * (snapped.close * 0.012);
      return {
        date: snapped.date,
        price: snapped.close + jitter,
        type: t.transaction_type,
        member: t.member_name,
        transactionDate: t.transaction_date,
        amount: formatAmountRange(t.amount_range_low, t.amount_range_high),
      };
    })
    .filter((m): m is TradeMarker => m !== null);

  const markersByCandleDate = new Map<string, TradeMarker[]>();
  for (const m of markers) {
    const list = markersByCandleDate.get(m.date) ?? [];
    list.push(m);
    markersByCandleDate.set(m.date, list);
  }

  if (candles.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        Sin histórico de precio disponible para este ticker.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Precio y operaciones del Congreso
        </h3>
        <div className="flex gap-3 text-xs text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1">
            <svg width="10" height="10">
              <polygon points="5,0 0,10 10,10" fill={UP_COLOR} />
            </svg>
            Compra
          </span>
          <span className="flex items-center gap-1">
            <svg width="10" height="10">
              <polygon points="5,10 0,0 10,0" fill={DOWN_COLOR} />
            </svg>
            Venta
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <ComposedChart data={candles} margin={{ left: 8, right: 8 }}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: colors.textMuted, fontSize: 11 }}
            axisLine={{ stroke: colors.axis }}
            tickLine={false}
            interval={Math.max(Math.floor(candles.length / 6), 0)}
            tickFormatter={(d) => formatDate(d)}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: colors.textMuted, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as CandleDatum;
              const tradesHere = markersByCandleDate.get(d.date);

              return (
                <div
                  className="max-w-[220px] rounded border p-2 text-xs"
                  style={{ background: colors.surface, borderColor: colors.grid }}
                >
                  <div className="font-medium">{formatDate(d.date)}</div>
                  <div>Apertura: ${d.open.toFixed(2)}</div>
                  <div>Cierre: ${d.close.toFixed(2)}</div>
                  <div>Máx: ${d.high.toFixed(2)} · Mín: ${d.low.toFixed(2)}</div>
                  {tradesHere && tradesHere.length > 0 && (
                    <div className="mt-2 space-y-1.5 border-t pt-2" style={{ borderColor: colors.grid }}>
                      {tradesHere.map((t, i) => (
                        <div key={i}>
                          <div
                            className="font-medium"
                            style={{ color: t.type === "purchase" ? UP_COLOR : DOWN_COLOR }}
                          >
                            {t.type === "purchase" ? "🟢 Compra" : "🔴 Venta"}
                          </div>
                          <div>{t.member}</div>
                          <div>{t.amount}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            }}
          />
          <Bar dataKey="range" shape={CandlestickShape} isAnimationActive={false} />
          <TradeMarkersLayer markers={markers} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
