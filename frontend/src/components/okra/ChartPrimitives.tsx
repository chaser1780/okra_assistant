import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPoint, PortfolioRiskPoint } from "../../lib/types";
import { compactMoney, signedMoney, signedPct } from "../../lib/format";
import { styleLabel } from "../../lib/display";

const chartText = { fill: "#718096", fontSize: 10 };
const grid = "#1b252d";

export function TrendChart({ data, benchmark = [], height = "100%", yFormatter = compactMoney, showArea = true }: { data: ChartPoint[]; benchmark?: ChartPoint[]; height?: string; yFormatter?: (value: number) => string; showArea?: boolean }) {
  const merged = mergeSeries(data, benchmark, "value", "benchmark");
  if (!merged.length) return <ChartEmpty label="暂无可用走势" />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="terminalTrendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.22} />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="date" tick={chartText} axisLine={false} tickLine={false} minTickGap={32} />
        <YAxis tick={chartText} axisLine={false} tickLine={false} tickFormatter={yFormatter} width={52} />
        <Tooltip content={<TerminalTooltip />} />
        {showArea ? <Area type="monotone" dataKey="value" name="本组合" stroke="#22d3ee" strokeWidth={2} fill="url(#terminalTrendFill)" dot={false} connectNulls /> : <Line type="monotone" dataKey="value" name="超额收益" stroke="#22d3ee" strokeWidth={1.8} dot={false} connectNulls />}
        {benchmark.length ? <Area type="monotone" dataKey="benchmark" name="基准" stroke="#8b949e" strokeWidth={1.25} fill="none" dot={false} connectNulls strokeDasharray="4 4" /> : null}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function DrawdownChart({ data, height = "100%" }: { data: ChartPoint[]; height?: string }) {
  if (!data.length) return <ChartEmpty label="暂无回撤序列" />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="terminalDrawdownFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fb7185" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#fb7185" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={grid} vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="date" tick={chartText} axisLine={false} tickLine={false} minTickGap={32} />
        <YAxis tick={chartText} axisLine={false} tickLine={false} tickFormatter={(value) => `${value}%`} width={46} />
        <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
        <Tooltip content={<TerminalTooltip percent />} />
        <Area type="monotone" dataKey="value" name="回撤" stroke="#fb7185" strokeWidth={1.7} fill="url(#terminalDrawdownFill)" dot={false} connectNulls />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RiskScatterChart({ points, height = "100%", onSelect }: { points: PortfolioRiskPoint[]; height?: string; onSelect?: (point: PortfolioRiskPoint) => void }) {
  if (!points.length) return <ChartEmpty label="暂无风险散点" />;
  const data = points.map((point) => ({ ...point, x: point.weightPct ?? 0, y: point.anomalyScore ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke={grid} strokeDasharray="2 4" />
        <XAxis type="number" dataKey="x" name="持仓权重" unit="%" tick={chartText} axisLine={false} tickLine={false} />
        <YAxis type="number" dataKey="y" name="异常分数" tick={chartText} axisLine={false} tickLine={false} width={42} />
        <ReferenceLine x={8} stroke="#4b5563" strokeDasharray="3 3" />
        <ReferenceLine y={1} stroke="#4b5563" strokeDasharray="3 3" />
        <Tooltip cursor={{ strokeDasharray: "3 3", stroke: "#22d3ee" }} content={<RiskTooltip />} />
        <Scatter name="持仓风险" data={data} onClick={(point) => onSelect?.(point as unknown as PortfolioRiskPoint)}>
          {data.map((point) => <Cell key={point.fundCode} fill={riskColor(point.y, point.x)} stroke="#050609" strokeWidth={1.5} r={5} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function ContributionBars({ points, height = "100%" }: { points: Array<{ name: string; value: number }>; height?: string }) {
  if (!points.length) return <ChartEmpty label="暂无收益贡献" />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={points} layout="vertical" margin={{ top: 0, right: 30, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={grid} horizontal={false} />
        <XAxis type="number" tick={chartText} axisLine={false} tickLine={false} tickFormatter={compactMoney} />
        <YAxis type="category" dataKey="name" width={90} tick={chartText} axisLine={false} tickLine={false} />
        <Tooltip content={<TerminalTooltip money />} />
        <Bar dataKey="value" name="收益贡献" fill="#22d3ee" radius={[0, 2, 2, 0]}>
          {points.map((point) => <Cell key={point.name} fill={point.value >= 0 ? "#fb7185" : "#34d399"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ data, positive = true, className = "h-5 w-24" }: { data: ChartPoint[]; positive?: boolean; className?: string }) {
  if (!data.length) return <span className={`${className} inline-block rounded-sm bg-slate-900`} />;
  return (
    <span className={`inline-block ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 1, right: 0, bottom: 1, left: 0 }}>
          <Area type="monotone" dataKey="value" stroke={positive ? "#fb7185" : "#34d399"} strokeWidth={1.2} fill="none" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </span>
  );
}

function mergeSeries(primary: ChartPoint[], secondary: ChartPoint[], primaryKey: string, secondaryKey: string) {
  const byDate = new Map<string, Record<string, unknown>>();
  for (const point of primary) byDate.set(point.date, { date: point.date, [primaryKey]: point.value });
  for (const point of secondary) byDate.set(point.date, { ...(byDate.get(point.date) ?? { date: point.date }), [secondaryKey]: point.value });
  return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function riskColor(anomaly: number, weight: number) {
  if (anomaly >= 1 && weight >= 8) return "#fb7185";
  if (anomaly >= 1) return "#f59e0b";
  if (weight >= 8) return "#34d399";
  return "#64748b";
}

function ChartEmpty({ label }: { label: string }) {
  return <div className="flex h-full min-h-28 items-center justify-center border border-dashed border-slate-800 text-xs text-slate-600">{label}</div>;
}

function TerminalTooltip({ active, payload, label, percent, money }: { active?: boolean; payload?: Array<{ name?: string; value?: unknown }>; label?: string; percent?: boolean; money?: boolean }) {
  if (!active || !payload?.length) return null;
  return <div className="terminal-tooltip"><div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</div>{payload.map((item) => <div key={item.name} className="mt-1 flex items-center justify-between gap-4 text-xs"><span className="text-slate-400">{item.name}</span><strong className="metric-number text-slate-100">{percent ? signedPct(item.value) : money ? signedMoney(item.value) : String(item.value ?? "-")}</strong></div>)}</div>;
}

function RiskTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: { fundName?: string; weightPct?: number; anomalyScore?: number; styleGroup?: string } }> }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return <div className="terminal-tooltip"><div className="font-semibold text-slate-100">{point.fundName}</div><div className="mt-1 text-xs text-slate-400">{styleLabel(point.styleGroup)} · 权重 {point.weightPct?.toFixed(2)}%</div><div className="text-xs text-slate-400">异常分数 {point.anomalyScore?.toFixed(2)}</div></div>;
}
