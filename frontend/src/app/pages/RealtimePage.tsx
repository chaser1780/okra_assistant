import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RealtimePayload } from "../../lib/types";
import { asNumber, lines, signedMoney, signedPct, text } from "../../lib/format";
import { styleLabel, valueLabel } from "../../lib/display";
import { Badge, Button, Card, DetailDrawer, EmptyState, MetricCard, SectionTitle } from "../../components/ui";

type RealtimeViewRow = {
  raw: Record<string, unknown>;
  code: string;
  name: string;
  styleGroup: string;
  change: number;
  estimate: number;
  proxy: number;
  pnl: number;
  anomaly: number;
  stale: boolean;
  changeText: string;
  pnlText: string;
  weightText: string;
  anomalyText: string;
};

const chartColors = ["#22d3ee", "#34d399", "#f59e0b", "#fb7185", "#818cf8", "#2dd4bf"];

function toneForChange(value: unknown) {
  const parsed = asNumber(value);
  if (parsed > 0) return "success" as const;
  if (parsed < 0) return "danger" as const;
  return "neutral" as const;
}

function numeric(item: Record<string, unknown>, key: string) {
  return asNumber(item[key]);
}

export function RealtimePage({
  realtime,
  onOpenFundDetail
}: {
  realtime: RealtimePayload;
  onOpenFundDetail: (fundCode: string) => void;
}) {
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [hovered, setHovered] = useState<RealtimeViewRow | null>(null);
  const rows = realtime.items;
  const viewRows = useMemo<RealtimeViewRow[]>(
    () =>
      rows
        .map((item) => ({
          raw: item,
          code: text(item.fund_code, ""),
          name: text(item.fund_name, text(item.fund_code, "基金")),
          styleGroup: text(item.style_group, ""),
          change: numeric(item, "effective_change_pct"),
          estimate: numeric(item, "estimate_change_pct"),
          proxy: numeric(item, "proxy_change_pct"),
          pnl: numeric(item, "estimated_intraday_pnl_amount"),
          anomaly: numeric(item, "anomaly_score"),
          stale: Boolean(item.stale),
          changeText: signedPct(item.effective_change_pct),
          pnlText: signedMoney(item.estimated_intraday_pnl_amount),
          weightText: signedPct(item.position_weight_pct).replace("+", ""),
          anomalyText: asNumber(item.anomaly_score).toFixed(2)
        }))
        .sort((a, b) => Math.abs(b.change) - Math.abs(a.change)),
    [rows]
  );
  const modeRows = useMemo(() => {
    const grouped = new Map<string, number>();
    rows.forEach((item) => grouped.set(modeText(item.mode), (grouped.get(modeText(item.mode)) ?? 0) + 1));
    return Array.from(grouped, ([name, value]) => ({ name, value }));
  }, [rows]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {realtime.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} />
        ))}
      </div>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-4">
          <SectionTitle title="实时摘要" meta={realtime.meta} />
          <ul className="space-y-2">
            {lines(realtime.summary_text).map((item) => (
              <li key={item} className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-300">
                {item}
              </li>
            ))}
          </ul>
        </Card>

        <Card className="col-span-7 p-4">
          <SectionTitle title={`今日估值与收益（${viewRows.length} 只全量基金）`} meta="按涨跌幅绝对值排序；悬停可同时查看涨跌和金额" />
          <RealtimeStripChart rows={viewRows} hovered={hovered} onHover={setHovered} />
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-8 p-4">
          <SectionTitle title="基金实时监控" meta="点击任意基金进入详情页" />
          {viewRows.length ? (
            <div className="max-h-[72vh] overflow-auto rounded-md border border-slate-800">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-slate-900 text-xs text-slate-500">
                  <tr>
                    <th className="px-3 py-3 text-left">基金</th>
                    <th className="px-3 py-3 text-right">采用涨跌幅</th>
                    <th className="px-3 py-3 text-right">今日收益金额</th>
                    <th className="px-3 py-3 text-right">权重</th>
                    <th className="px-3 py-3 text-right">异常分数</th>
                    <th className="px-3 py-3 text-left">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {viewRows.map((item, index) => (
                    <tr
                      key={`${item.code || "rt"}-${index}`}
                      className="cursor-pointer border-t border-slate-800 text-slate-300 transition hover:bg-cyan-950/20"
                      onClick={() => setSelected(item.raw)}
                      onMouseEnter={() => setHovered(item)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <td className="px-3 py-3">
                        <div className="font-semibold text-slate-100">{item.name}</div>
                        <div className="text-xs text-slate-500">
                          {item.code} | {styleLabel(item.styleGroup)}
                        </div>
                      </td>
                      <td className="metric-number px-3 py-3 text-right">
                        <Badge tone={toneForChange(item.change)}>{item.changeText}</Badge>
                      </td>
                      <td className="metric-number px-3 py-3 text-right">{item.pnlText}</td>
                      <td className="metric-number px-3 py-3 text-right">{item.weightText}</td>
                      <td className="metric-number px-3 py-3 text-right">{item.anomalyText}</td>
                      <td className="px-3 py-3">
                        <Badge tone={item.stale ? "warning" : "success"}>{item.stale ? "滞后" : "新鲜"}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="暂无实时估值" body="点击左侧实时刷新后，会显示每只基金的估值、收益、异常分数和数据时效。" />
          )}
        </Card>

        <Card className="col-span-4 p-4">
          <SectionTitle title="估值模式分布" meta="用于判断实时数据可靠性" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modeRows} layout="vertical" margin={{ left: 18, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis dataKey="name" type="category" width={105} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {modeRows.map((entry, index) => (
                    <Cell key={entry.name} fill={chartColors[index % chartColors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      <DetailDrawer
        open={Boolean(selected)}
        title={selected ? text(selected.fund_name, text(selected.fund_code, "基金详情")) : "基金详情"}
        subtitle={selected ? `${text(selected.fund_code, "")} | ${styleLabel(selected.style_group)}` : ""}
        onClose={() => setSelected(null)}
      >
        {selected ? <RealtimeDetail item={selected} onOpenFundDetail={onOpenFundDetail} /> : null}
      </DetailDrawer>
    </div>
  );
}

function RealtimeStripChart({
  rows,
  hovered,
  onHover
}: {
  rows: RealtimeViewRow[];
  hovered: RealtimeViewRow | null;
  onHover: (row: RealtimeViewRow | null) => void;
}) {
  const maxAbs = Math.max(1, ...rows.map((item) => Math.abs(item.change)));
  const barGap = rows.length <= 20 ? "gap-2.5" : rows.length <= 40 ? "gap-1.5" : "gap-1";
  return (
    <div className="space-y-3">
      <div className="relative h-60 overflow-hidden rounded-md border border-slate-800 bg-slate-950/45 px-4 py-4">
        <div className="absolute left-4 right-4 top-1/2 h-px bg-slate-700" />
        <div
          className={`grid h-full items-center ${barGap}`}
          style={{ gridTemplateColumns: `repeat(${Math.max(1, rows.length)}, minmax(0, 1fr))` }}
        >
          {rows.map((item) => {
            const height = Math.max(4, (Math.abs(item.change) / maxAbs) * 102);
            const positive = item.change >= 0;
            const isHovered = hovered?.code === item.code;
            return (
              <button
                key={item.code}
                type="button"
                title={`${item.name} ${item.changeText} ${item.pnlText}`}
                className="group relative flex h-full min-w-0 items-center justify-center focus:outline-none"
                onMouseEnter={() => onHover(item)}
                onMouseLeave={() => onHover(null)}
              >
                <span
                  className={`absolute left-1/2 -translate-x-1/2 rounded-sm transition ${
                    positive ? "bottom-1/2 bg-emerald-400" : "top-1/2 bg-rose-400"
                  } ${isHovered ? "ring-2 ring-white" : "group-hover:ring-2 group-hover:ring-white"}`}
                  style={{ height, width: "clamp(10px, 72%, 34px)" }}
                />
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex items-start justify-between gap-3 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm border border-slate-600" style={{ background: "linear-gradient(135deg, #34d399 0 50%, #fb7185 50% 100%)" }} />
          <span className="text-cyan-100">采用涨跌幅</span>
        </div>
        <div className="min-h-12 max-w-[68%] rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-right leading-5">
          {hovered ? (
            <>
              <div className="font-semibold text-slate-100">
                {hovered.name} ({hovered.code})
              </div>
              <div>
                <span className={hovered.change >= 0 ? "text-emerald-300" : "text-rose-300"}>采用涨跌幅 {hovered.changeText}</span>
                <span className="mx-2 text-slate-600">|</span>
                <span className="text-cyan-200">今日收益 {hovered.pnlText}</span>
              </div>
            </>
          ) : (
            <span>悬停柱子查看单只基金的涨跌和金额</span>
          )}
        </div>
      </div>
    </div>
  );
}

function RealtimeDetail({
  item,
  onOpenFundDetail
}: {
  item: Record<string, unknown>;
  onOpenFundDetail: (fundCode: string) => void;
}) {
  const rows = [
    ["采用涨跌幅", signedPct(item.effective_change_pct)],
    ["估算涨跌", signedPct(item.estimate_change_pct)],
    ["代理涨跌", signedPct(item.proxy_change_pct)],
    ["今日估算收益", signedMoney(item.estimated_intraday_pnl_amount)],
    ["估算持仓市值", text(item.estimated_position_value)],
    ["估算总收益率", signedPct(item.estimated_total_return_pct)],
    ["持仓权重", signedPct(item.position_weight_pct).replace("+", "")],
    ["异常分数", asNumber(item.anomaly_score).toFixed(2)],
    ["置信度", asNumber(item.confidence).toFixed(2)],
    ["估算模式", modeText(item.mode)],
    ["官方净值", text(item.official_nav)],
    ["官方净值日期", text(item.official_nav_date)],
    ["有效净值", text(item.effective_nav)],
    ["持有份额", text(item.holding_units)],
    ["估值时间", text(item.estimate_time)],
    ["代理时间", text(item.proxy_time)]
  ];
  return (
    <div className="space-y-4">
      <Button variant="primary" className="w-full" onClick={() => onOpenFundDetail(text(item.fund_code, ""))} disabled={!text(item.fund_code, "")}>
        查看完整详情
      </Button>
      <div className="grid grid-cols-2 gap-3">
        {rows.slice(0, 8).map(([label, value]) => (
          <div key={label} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="metric-number mt-1 text-sm font-bold text-slate-100">{value}</div>
          </div>
        ))}
      </div>
      <Card className="p-4">
        <SectionTitle title="估值依据" />
        <p className="text-sm leading-6 text-slate-300">{valueLabel(item.reason)}</p>
      </Card>
      <Card className="p-4">
        <SectionTitle title="完整字段" meta="用于排查估值来源和时效" />
        <div className="space-y-2">
          {rows.slice(8).map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-3 border-b border-slate-800/70 pb-2 text-sm">
              <span className="text-slate-500">{label}</span>
              <span className="metric-number text-right text-slate-200">{value}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function modeText(value: unknown) {
  return valueLabel(value);
}
