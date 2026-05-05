import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { PortfolioItem, PortfolioPayload } from "../../lib/types";
import { asNumber, compactMoney, signedMoney, signedPct } from "../../lib/format";
import { actionLabel, roleLabel, styleLabel } from "../../lib/display";
import { Badge, Button, Card, DetailDrawer, EmptyState, MetricCard, SectionTitle } from "../../components/ui";

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

export function PortfolioPage({ portfolio, onOpenFundDetail }: { portfolio: PortfolioPayload; onOpenFundDetail: (fundCode: string) => void }) {
  const [selected, setSelected] = useState<PortfolioItem | null>(null);
  const returnBars = useMemo(
    () =>
      portfolio.items
        .map((item) => ({ code: item.fundCode, name: item.fundName || item.fundCode, value: asNumber(item.holdingReturnPct), pnl: asNumber(item.holdingPnl) }))
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
        .slice(0, 10),
    [portfolio.items]
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <MetricCard title="总资产" value={portfolio.totalValueText} body={`快照日期 ${portfolio.asOfDate || "暂无"}`} tone="accent" />
        <MetricCard title="持有盈亏" value={portfolio.holdingPnlText} body="基于当前持仓快照汇总" tone={pnlTone(portfolio.holdingPnl)} />
        <MetricCard title="持仓数量" value={String(portfolio.items.length)} body="当前组合覆盖的基金数量" tone="info" />
        <MetricCard title="现金" value={portfolio.cashText} body="用于下一次再平衡或补仓" tone="success" />
      </div>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-7 p-4">
          <SectionTitle title="组合资产走势" meta="来自 portfolio_state 历史快照" />
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={portfolio.history.totalValue} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="assetValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={compactMoney} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} formatter={(value) => [compactMoney(value), "总资产"]} />
                <Area type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2} fill="url(#assetValue)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="col-span-5 p-4">
          <SectionTitle title="持仓风格分布" meta="按当前市值汇总" />
          <div className="grid grid-cols-2 gap-3">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={portfolio.styleAllocation} dataKey="value" nameKey="name" innerRadius={48} outerRadius={82} paddingAngle={2}>
                    {portfolio.styleAllocation.map((entry, index) => (
                      <Cell key={entry.name} fill={palette[index % palette.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} formatter={(value, _name, item) => [compactMoney(value), styleLabel(item.payload.name)]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              {portfolio.styleAllocation.slice(0, 6).map((item, index) => (
                <div key={item.name} className="flex items-center justify-between gap-2 text-sm">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: palette[index % palette.length] }} />
                    <span className="truncate text-slate-300">{styleLabel(item.name)}</span>
                  </div>
                  <span className="metric-number text-slate-500">{item.weightText}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-4 p-4">
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

        <Card className="col-span-8 p-4">
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
                    <Cell key={entry.code} fill={entry.value >= 0 ? "#34d399" : "#fb7185"} />
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
          <div className="overflow-hidden rounded-md border border-slate-800">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-slate-900 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-3 text-left">基金</th>
                  <th className="px-3 py-3 text-right">市值</th>
                  <th className="px-3 py-3 text-right">占比</th>
                  <th className="px-3 py-3 text-right">持有盈亏</th>
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
                    <td className="metric-number px-3 py-3 text-right">{item.holdingReturnPctText}</td>
                    <td className="px-3 py-3">
                      <Badge tone="info">{roleLabel(item.role || "未标注")}</Badge>
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={item.fixedDailyBuyAmount > 0 ? "success" : actionTone(item.action)}>
                        {item.fixedDailyBuyAmount > 0 ? "每日定投" : actionLabel(item.action)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="暂无持仓数据" body="当前 API 没有读取到 portfolio_state 中的基金持仓，请检查组合快照或重新运行首启分析。" />
        )}
      </Card>

      <DetailDrawer open={Boolean(selected)} title={selected?.fundName || selected?.fundCode || "持仓详情"} subtitle={selected ? `${selected.fundCode} | ${styleLabel(selected.styleGroup || "未分组")}` : ""} onClose={() => setSelected(null)}>
        {selected ? <PortfolioDetail item={selected} onOpenFundDetail={onOpenFundDetail} /> : null}
      </DetailDrawer>
    </div>
  );
}

function PortfolioDetail({ item, onOpenFundDetail }: { item: PortfolioItem; onOpenFundDetail: (fundCode: string) => void }) {
  const rows = [
    ["当前市值", item.amountText],
    ["成本金额", item.costBasisText],
    ["持有盈亏", item.holdingPnlText],
    ["持有收益率", item.holdingReturnPctText],
    ["组合占比", item.weightText],
    ["持有份额", String(item.holdingUnits)],
    ["最近净值", String(item.lastNav || "暂无")],
    ["净值日期", item.lastNavDate || "暂无"],
    ["角色", roleLabel(item.role || "未标注")],
    ["风格分组", styleLabel(item.styleGroup || "未分组")],
    ["交易状态", item.allowTrade ? "允许交易" : "固定持有/不可交易"],
    ["定投金额", item.fixedDailyBuyAmount > 0 ? `${item.fixedDailyBuyAmount} 元/日` : "未开启"]
  ];
  return (
    <div className="space-y-4">
      <Button variant="primary" className="w-full" onClick={() => onOpenFundDetail(item.fundCode)}>
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
