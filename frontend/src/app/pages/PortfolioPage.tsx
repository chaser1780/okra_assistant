import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { PortfolioItem, PortfolioPayload } from "../../lib/types";
import { asNullableNumber, asNumber, compactMoney, signedMoney, signedPct, text } from "../../lib/format";
import { actionLabel, roleLabel, styleLabel } from "../../lib/display";
import { Badge, Button, Card, DetailDrawer, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { DrawdownChart, RiskScatterChart, TrendChart } from "../../components/okra/ChartPrimitives";
import { ChartFrame, TerminalPanel, TerminalState } from "../../components/okra/TerminalChrome";
import { ResearchDataContext, SimulationTrackRail } from "../../components/okra/ResearchContext";

const palette = ["#22d3ee", "#34d399", "#f59e0b", "#fb7185", "#818cf8", "#2dd4bf", "#a78bfa", "#f472b6"];

function actionTone(action: string) {
  if (action === "locked") return "warning" as const;
  if (action === "hold") return "neutral" as const;
  return "accent" as const;
}

function pnlTone(value: unknown) {
  const parsed = asNumber(value);
  if (parsed > 0) return "success" as const;
  if (parsed < 0) return "danger" as const;
  return "neutral" as const;
}

function officialDailyPnlLabel(item: PortfolioItem) {
  if (item.officialDailyPnlStatus === "ok" || item.officialDailyPnlStatus === "already_written") {
    return item.officialDailyPnlText;
  }
  return item.officialDailyPnlReason ? "待确认" : "暂无";
}

export function PortfolioPage({ portfolio, onOpenFundDetail }: { portfolio: PortfolioPayload; onOpenFundDetail: (fundCode: string) => void }) {
  const [selected, setSelected] = useState<PortfolioItem | null>(null);
  const returnBars = useMemo(
    () =>
      portfolio.items
        .map((item) => ({ code: item.fundCode, name: item.fundName || item.fundCode, value: asNullableNumber(item.holdingReturnPct), pnl: asNullableNumber(item.holdingPnl) }))
        .filter((item): item is typeof item & { value: number } => item.value !== null)
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
        .slice(0, 10),
    [portfolio.items]
  );

  return (
    <div className="space-y-4">
      <ResearchDataContext context={portfolio.dataContext} />
      <SimulationTrackRail simulation={portfolio.simulation} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="总资产" value={portfolio.totalValueText} body={`快照日期 ${portfolio.asOfDate || "暂无"}`} tone="accent" />
        <MetricCard title="持有盈亏" value={portfolio.holdingPnlText} body="基于当前持仓快照汇总" tone={pnlTone(portfolio.holdingPnl)} />
        <MetricCard title="持仓数量" value={String(portfolio.items.length)} body="当前组合覆盖的基金数量" tone="info" />
        <MetricCard title="现金" value={portfolio.cashText} body="用于下一次再平衡或补仓" tone="success" />
      </div>

      <TerminalPanel title="组合摘要" meta={`SNAPSHOT / ${portfolio.asOfDate || "暂无日期"}`}>
        <div className="grid grid-cols-2 gap-px bg-slate-800/60 lg:grid-cols-5">
          <TerminalReadout label="组合净值" value={portfolio.totalValueText} />
          <TerminalReadout label="持有盈亏" value={portfolio.holdingPnlText} tone={pnlTone(portfolio.holdingPnl)} />
          <TerminalReadout label="当前回撤" value={portfolio.riskSnapshot?.currentDrawdownPct == null ? "暂无" : `${portfolio.riskSnapshot.currentDrawdownPct.toFixed(2)}%`} tone="danger" />
          <TerminalReadout label="最大回撤" value={portfolio.riskSnapshot?.maxDrawdownPct == null ? "暂无" : `${portfolio.riskSnapshot.maxDrawdownPct.toFixed(2)}%`} tone="danger" />
          <TerminalReadout label="现金缓冲" value={portfolio.riskSnapshot?.cashWeightPct == null ? "暂无" : `${portfolio.riskSnapshot.cashWeightPct.toFixed(2)}%`} tone="success" />
        </div>
      </TerminalPanel>

      <section className="grid grid-cols-12 gap-4">
        <ChartFrame title="组合净值 / NORMALIZED" meta="portfolio_state 历史快照" height="h-80" className="col-span-12 xl:col-span-8">
          <TrendChart data={portfolio.history.totalValueNormalized ?? portfolio.history.totalValue} benchmark={portfolio.benchmark?.normalized ?? []} yFormatter={(value) => value.toFixed(2)} />
        </ChartFrame>

        <Card className="col-span-12 p-4 xl:col-span-4">
          <SectionTitle title="持仓风格分布" meta="按当前市值汇总" />
          <AllocationBars items={portfolio.styleAllocation} />
          <div className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-500">
            <span>基准状态</span>
            <TerminalState label={portfolio.benchmark?.status === "available" ? "已配置" : "未配置组合基准"} tone={portfolio.benchmark?.status === "available" ? "success" : "neutral"} />
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <ChartFrame title="回撤 / DRAWDOWN" meta={`最大 ${portfolio.riskSnapshot?.maxDrawdownPct?.toFixed(2) ?? "暂无"}%`} height="h-56" className="col-span-12 xl:col-span-7">
          <DrawdownChart data={portfolio.history.drawdownPct ?? []} />
        </ChartFrame>
        <ChartFrame title="持仓权重 VS 异常分数" meta="点击散点查看基金" height="h-56" className="col-span-12 xl:col-span-5">
          <RiskScatterChart points={portfolio.riskScatter ?? []} />
        </ChartFrame>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 lg:col-span-4">
          <SectionTitle title="角色配置" meta="核心、战术、现金、固定持有" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={portfolio.roleAllocation} layout="vertical" margin={{ left: 18, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={compactMoney} />
                <YAxis dataKey="name" type="category" width={98} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={roleLabel} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} formatter={(value) => [compactMoney(value), "市值"]} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {portfolio.roleAllocation.map((entry, index) => (
                    <Cell key={entry.name} fill={palette[index % palette.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="col-span-12 p-4 lg:col-span-8">
          <SectionTitle title="持仓收益结构" meta="收益率绝对值最高的前 10 只基金" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={returnBars} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="code" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(value) => `${value}%`} />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }}
                  formatter={(value, name) => [name === "pnl" ? signedMoney(value) : signedPct(value), name === "pnl" ? "持有盈亏" : "持有收益率"]}
                  labelFormatter={(label) => returnBars.find((item) => item.code === label)?.name ?? label}
                />
                <Bar dataKey="value" name="持有收益率" radius={[4, 4, 0, 0]}>
                  {returnBars.map((entry) => (
                    <Cell key={entry.code} fill={entry.value >= 0 ? "#fb7185" : "#34d399"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      <Card className="p-4">
        <SectionTitle title="持仓明细" meta="点击基金查看持仓、收益、净值与交易约束" />
        {portfolio.items.length ? (
          <div className="overflow-x-auto rounded-md border border-slate-800">
            <table className="min-w-[760px] w-full border-collapse text-sm">
              <thead className="bg-slate-900 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-3 text-left">基金</th>
                  <th className="px-3 py-3 text-right">市值</th>
                  <th className="px-3 py-3 text-right">占比</th>
                  <th className="px-3 py-3 text-right">持有盈亏</th>
                  <th className="px-3 py-3 text-right">官方日盈亏</th>
                  <th className="px-3 py-3 text-right">收益率</th>
                  <th className="px-3 py-3 text-left">角色</th>
                  <th className="px-3 py-3 text-left">状态</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.items.map((item) => (
                  <tr key={`${item.fundCode}-${item.fundName}`} className="cursor-pointer border-t border-slate-800 text-slate-300 transition hover:bg-cyan-950/20" onClick={() => setSelected(item)}>
                    <td className="px-3 py-3">
                      <div className="font-semibold text-slate-100">{item.fundName || item.fundCode}</div>
                      <div className="text-xs text-slate-500">
                        {item.fundCode} | {styleLabel(item.styleGroup || "未分组")}
                      </div>
                    </td>
                    <td className="metric-number px-3 py-3 text-right">{item.amountText}</td>
                    <td className="metric-number px-3 py-3 text-right">{item.weightText}</td>
                    <td className="metric-number px-3 py-3 text-right">
                      <Badge tone={pnlTone(item.holdingPnl)}>{item.holdingPnlText}</Badge>
                    </td>
                    <td className="metric-number px-3 py-3 text-right">
                      <Badge tone={item.officialDailyPnl == null ? "warning" : pnlTone(item.officialDailyPnl)}>{officialDailyPnlLabel(item)}</Badge>
                    </td>
                    <td className="metric-number px-3 py-3 text-right">{item.holdingReturnPctText}</td>
                    <td className="px-3 py-3">
                      <Badge tone="info">{roleLabel(item.role || "未标注")}</Badge>
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={(item.fixedDailyBuyAmount ?? 0) > 0 ? "success" : actionTone(item.action)}>
                        {(item.fixedDailyBuyAmount ?? 0) > 0 ? "每日定投" : actionLabel(item.action)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="暂无持仓数据" body="当前 API 没有读取到 portfolio_state 中的基金持仓，请检查组合快照或重新运行今日分析。" />
        )}
      </Card>

      <DetailDrawer open={Boolean(selected)} title={selected?.fundName || selected?.fundCode || "持仓详情"} subtitle={selected ? `${selected.fundCode} | ${styleLabel(selected.styleGroup || "未分组")}` : ""} onClose={() => setSelected(null)}>
        {selected ? <PortfolioDetail item={selected} onOpenFundDetail={onOpenFundDetail} /> : null}
      </DetailDrawer>
    </div>
  );
}

function AllocationBars({ items }: { items: PortfolioPayload["styleAllocation"] }) {
  const visible = items.slice(0, 8);
  return (
    <div className="space-y-3 pt-2">
      {visible.length ? visible.map((item, index) => {
        const weight = Math.max(0, Math.min(100, Number.parseFloat(String(item.weightText).replace("%", "")) || 0));
        return (
          <div key={item.name}>
            <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
              <div className="flex min-w-0 items-center gap-2">
                <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: palette[index % palette.length] }} />
                <span className="truncate text-slate-300">{styleLabel(item.name)}</span>
              </div>
              <span className="metric-number shrink-0 font-semibold text-slate-300">{item.weightText}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-sm bg-slate-900">
              <div className="h-full rounded-sm" style={{ width: `${weight}%`, background: palette[index % palette.length] }} />
            </div>
          </div>
        );
      }) : <EmptyState title="暂无风格分布" body="当前组合没有可展示的风格配置。" />}
      {items.length > visible.length ? <div className="pt-1 text-xs text-slate-600">其余 {items.length - visible.length} 个风格已收起</div> : null}
    </div>
  );
}

function TerminalReadout({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "success" | "danger" | "warning" }) {
  const color = tone === "success" ? "text-emerald-300" : tone === "danger" ? "text-rose-300" : tone === "warning" ? "text-amber-300" : "text-slate-100";
  return <div className="bg-[#0b0e12] px-3 py-3"><div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</div><div className={`metric-number mt-2 text-lg font-semibold ${color}`}>{value}</div></div>;
}

function PortfolioDetail({ item, onOpenFundDetail }: { item: PortfolioItem; onOpenFundDetail: (fundCode: string) => void }) {
  const rows = [
    ["当前市值", item.amountText],
    ["成本金额", item.costBasisText],
    ["持有盈亏", item.holdingPnlText],
    ["官方日盈亏", `${officialDailyPnlLabel(item)}${item.officialDailyPnlDate ? ` (${item.officialDailyPnlDate})` : ""}`],
    ["持有收益率", item.holdingReturnPctText],
    ["组合占比", item.weightText],
    ["持有份额", text(item.holdingUnits, "不可用")],
    ["最近净值", text(item.lastNav, "不可用")],
    ["净值日期", item.lastNavDate || "暂无"],
    ["角色", roleLabel(item.role || "未标注")],
    ["风格分组", styleLabel(item.styleGroup || "未分组")],
    ["交易状态", item.allowTrade ? "允许交易" : "固定持有/不可交易"],
    ["官方日盈亏状态", item.officialDailyPnlStatus || "暂无"],
    ["官方日盈亏说明", item.officialDailyPnlReason || "暂无"],
    ["定投金额", item.fixedDailyBuyAmount === null ? "不可用" : item.fixedDailyBuyAmount > 0 ? `${item.fixedDailyBuyAmount} 元/日` : "未开启"]
  ];
  return (
    <div className="space-y-4">
      <Button variant="primary" className="w-full" onClick={() => onOpenFundDetail(item.fundCode)}>
        查看完整详情
      </Button>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {rows.slice(0, 8).map(([label, value]) => (
          <div key={label} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="metric-number mt-1 text-sm font-bold text-slate-100">{value}</div>
          </div>
        ))}
      </div>
      <Card className="p-4">
        <SectionTitle title="组合定位" />
        <div className="space-y-2">
          {rows.slice(8).map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-3 border-b border-slate-800/70 pb-2 text-sm">
              <span className="text-slate-500">{label}</span>
              <span className="text-right text-slate-200">{value}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
