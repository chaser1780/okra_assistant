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
import type { PortfolioItem, PortfolioPayload, PortfolioRiskBreakdown } from "../../lib/types";
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
        {portfolio.simulationV2?.fundingMode === "virtual_external_flows" ? (
          <MetricCard title="虚拟本金净流入" value={portfolio.simulationV2.netExternalFlow == null ? "暂无" : signedMoney(portfolio.simulationV2.netExternalFlow)} body="买入自动入金、卖出自动出金、分红与费用内部结算，现金池余额无需手动维护" tone="success" />
        ) : (
          <MetricCard title="现金(旧版参考)" value={portfolio.cashText} body="旧版余额参考，不参与新规则下的再平衡" tone="success" />
        )}
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

      <TerminalPanel title="收益口径 / PERFORMANCE" meta={portfolio.performanceMetrics?.status === "available" ? "CASHFLOW ADJUSTED" : "NEEDS CASHFLOW"} className="p-4">
        {portfolio.performanceMetrics?.status === "available" ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><TerminalReadout label="TWR" value={`${portfolio.performanceMetrics.twr.returnPct?.toFixed(2) ?? "暂无"}%`} /><TerminalReadout label="MWR / XIRR" value={`${portfolio.performanceMetrics.mwr.returnPct?.toFixed(2) ?? "暂无"}%`} /><TerminalReadout label="调整回撤" value={portfolio.performanceMetrics.cashflowAdjustedDrawdown?.currentPct == null ? "暂无" : `${portfolio.performanceMetrics.cashflowAdjustedDrawdown.currentPct.toFixed(2)}%`} tone="danger" /><TerminalReadout label="外部现金流" value={`${portfolio.performanceMetrics.cashflowCount} 笔`} /></div>
        ) : (
          <p className="text-sm leading-6 text-slate-400">{portfolio.performanceMetrics?.reason ?? "缺少显式外部入金/出金数据，不把组合资产变化误作投资收益。"}</p>
        )}
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

      <RiskBreakdownPanel rows={portfolio.riskBreakdown ?? []} summary={portfolio.riskSummary} />

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 lg:col-span-4">
          <SectionTitle title="角色配置" meta="核心、战术、现金、固定持有" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={portfolio.roleAllocation} layout="vertical" margin={{ left: 18, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#718096", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={compactMoney} />
                <YAxis dataKey="name" type="category" width={98} tick={{ fill: "#718096", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={roleLabel} />
                <Tooltip contentStyle={{ background: "var(--chart-tooltip)", border: "1px solid var(--chart-tooltip-border)", borderRadius: 8 }} formatter={(value) => [compactMoney(value), "市值"]} />
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
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="code" tick={{ fill: "#718096", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#718096", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(value) => `${value}%`} />
                <Tooltip
                  contentStyle={{ background: "var(--chart-tooltip)", border: "1px solid var(--chart-tooltip-border)", borderRadius: 8 }}
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

function RiskBreakdownPanel({ rows, summary }: { rows: PortfolioRiskBreakdown[]; summary?: PortfolioPayload["riskSummary"] }) {
  const weighted = summary?.weightedTotalAnomalyScore;
  return (
    <Card className="p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <SectionTitle title="风险构成 / DIAGNOSTIC" meta="只读观察分解，不改变既有异常分数、约束或模拟动作" />
        <div className="flex flex-wrap gap-2">
          <Badge tone="info">组合观察 {weighted == null ? "不可用" : weighted.toFixed(1)}</Badge>
          <Badge tone={summary?.partialCoverageFundCount ? "warning" : "success"}>部分覆盖 {summary?.partialCoverageFundCount ?? 0}</Badge>
          <Badge tone="neutral">组合覆盖 {summary?.weightedComponentCoverage == null ? "不可用" : `${(summary.weightedComponentCoverage * 100).toFixed(0)}%`}</Badge>
          <Badge tone="neutral">历史百分位 {summary?.historicalPercentileAvailableCount ?? 0} 只</Badge>
        </div>
      </div>
      {rows.length ? (
        <div className="overflow-x-auto border border-slate-800">
          <table className="min-w-[1040px] w-full border-collapse text-sm">
            <thead className="bg-slate-950/80 text-xs text-slate-500">
              <tr>
                <th className="px-3 py-3 text-left">基金</th>
                <th className="px-3 py-3 text-right">综合观察</th>
                <th className="px-3 py-3 text-right">时效</th>
                <th className="px-3 py-3 text-right">冲突</th>
                <th className="px-3 py-3 text-right">波动</th>
                <th className="px-3 py-3 text-right">拥挤</th>
                <th className="px-3 py-3 text-right">新闻</th>
                <th className="px-3 py-3 text-right">摩擦</th>
                <th className="px-3 py-3 text-right">历史分位</th>
                <th className="px-3 py-3 text-left">覆盖</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.fundCode} className="border-t border-slate-800/80 hover:bg-cyan-950/15">
                  <td className="px-3 py-3"><div className="font-semibold text-slate-200">{row.fundName || row.fundCode}</div><div className="metric-number text-xs text-slate-500">{row.fundCode} · 权重 {row.weightPct?.toFixed(2) ?? "暂无"}%</div></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.totalAnomalyScore} strong /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.freshnessRisk} /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.dataConflictRisk} /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.volatilityRisk} /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.crowdingRisk} /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.newsRisk} /></td>
                  <td className="px-3 py-3 text-right"><RiskValue value={row.executionFrictionRisk} /></td>
                  <td className="metric-number px-3 py-3 text-right text-slate-300">{row.historicalPercentile == null ? "样本不足" : `${row.historicalPercentile.toFixed(0)}%`}</td>
                  <td className="px-3 py-3"><details><summary className="cursor-pointer text-xs text-cyan-300">{row.dataCoverage.availableComponentCount == null || row.dataCoverage.componentCount == null ? "覆盖不可用" : `${row.dataCoverage.availableComponentCount}/${row.dataCoverage.componentCount} 项`} · {row.dataCoverage.coverageRatio == null ? "不可用" : `${(row.dataCoverage.coverageRatio * 100).toFixed(0)}%`}</summary><div className="mt-2 max-w-72 space-y-1 text-xs leading-5 text-slate-500">{Object.entries(row.reasons).map(([key, reason]) => <div key={key}><span className="text-slate-300">{riskLabel(key)}：</span>{reason}</div>)}</div></details></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <EmptyState title="暂无风险分解" body="缺少组合或实时观察数据时，不会生成虚假的风险构成。" />}
    </Card>
  );
}

function RiskValue({ value, strong = false }: { value: number | null; strong?: boolean }) {
  if (value == null) return <span className="metric-number text-xs text-slate-600">不可用</span>;
  const tone = value >= 70 ? "text-rose-300" : value >= 40 ? "text-amber-300" : "text-emerald-300";
  return <span className={`metric-number ${strong ? "font-semibold" : ""} ${tone}`}>{value.toFixed(1)}</span>;
}

function riskLabel(value: string) {
  const labels: Record<string, string> = {
    freshnessRisk: "数据时效",
    dataConflictRisk: "数据冲突",
    volatilityRisk: "观察波动",
    crowdingRisk: "拥挤信号",
    newsRisk: "新闻事件",
    executionFrictionRisk: "模拟摩擦"
  };
  return labels[value] ?? value;
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
    ["持有份额", text(item.holdingUnits, "待确认")],
    ["最近净值", text(item.lastNav, "待确认")],
    ["净值日期", item.lastNavDate || "暂无"],
    ["角色", roleLabel(item.role || "未标注")],
    ["风格分组", styleLabel(item.styleGroup || "未分组")],
    ["交易状态", item.allowTrade ? "允许交易" : "固定持有/不可交易"],
    ["官方日盈亏状态", item.officialDailyPnlStatus || "暂无"],
    ["官方日盈亏说明", item.officialDailyPnlReason || "暂无"],
    ["固定模拟定投配置", item.fixedDailyBuyAmount === null ? "未配置" : item.fixedDailyBuyAmount > 0 ? `${item.fixedDailyBuyAmount} 元/日` : "未开启"]
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
