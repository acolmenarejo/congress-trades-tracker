import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
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

function TradeMarkerShape(props: any) {
  const { cx, cy, payload } = props as { cx: number; cy: number; payload: { type: string } };
  const isBuy = payload.type === "purchase";
  const color = isBuy ? UP_COLOR : DOWN_COLOR;
  const size = 6;
  // Small triangle: up-pointing for buys, down-pointing for sells.
  const points = isBuy
    ? `${cx},${cy - size} ${cx - size},${cy + size} ${cx + size},${cy + size}`
    : `${cx},${cy + size} ${cx - size},${cy - size} ${cx + size},${cy - size}`;
  return <polygon points={points} fill={color} stroke="white" strokeWidth={0.5} />;
}

const MAX_MARKER_SNAP_DAYS = 5;

// Snap a trade to the nearest candle within the chart's own date range — a
// trade far outside the visible window (e.g. a 2019 trade on a 6-month chart)
// must be dropped, not clamped to the nearest edge candle (that piles up
// unrelated markers on one date and drags the x-axis domain along with it).
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
  const markers = trades
    .filter((t) => t.transaction_date)
    .map((t) => {
      const snapped = nearestCandle(prices, t.transaction_date as string);
      if (!snapped) return null;
      // Jitter stacked markers on the same date so each stays hoverable
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
    .filter((m) => m !== null);

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

              const markerEntry = payload.find((p: any) => p.payload && "member" in p.payload);
              if (markerEntry) {
                const m = markerEntry.payload as {
                  member: string;
                  type: string | null;
                  amount: string;
                  transactionDate: string | null;
                };
                const isBuy = m.type === "purchase";
                return (
                  <div
                    className="rounded border p-2 text-xs"
                    style={{ background: colors.surface, borderColor: colors.grid }}
                  >
                    <div className="font-medium" style={{ color: isBuy ? UP_COLOR : DOWN_COLOR }}>
                      {isBuy ? "🟢 Compra" : "🔴 Venta"}
                    </div>
                    <div>{m.member}</div>
                    <div>{m.amount}</div>
                    <div className="text-slate-500 dark:text-slate-400">{formatDate(m.transactionDate)}</div>
                  </div>
                );
              }

              const d = payload[0].payload as CandleDatum;
              return (
                <div
                  className="rounded border p-2 text-xs"
                  style={{ background: colors.surface, borderColor: colors.grid }}
                >
                  <div className="font-medium">{formatDate(d.date)}</div>
                  <div>Apertura: ${d.open.toFixed(2)}</div>
                  <div>Cierre: ${d.close.toFixed(2)}</div>
                  <div>Máx: ${d.high.toFixed(2)} · Mín: ${d.low.toFixed(2)}</div>
                </div>
              );
            }}
          />
          <Bar dataKey="range" shape={CandlestickShape} isAnimationActive={false} />
          <Scatter data={markers} dataKey="price" shape={TradeMarkerShape} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
