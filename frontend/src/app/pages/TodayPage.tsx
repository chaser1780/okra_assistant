import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { FundResearchCard, LongMemoryRecord, TodayPagePayload, Tone } from "../../lib/types";
import { compactMoney, lines, text } from "../../lib/format";
import { Badge, Button, Card, MetricCard, SectionTitle } from "../../components/ui";
import { actionLabel, memoryText, memoryTitle, statusLabel, valueLabel } from "../../lib/display";
import { getTodayAnalysis, getTodayAnalysisSystem, pickAnalysisValue } from "../../lib/todayAnalysis";
import { routeForPage } from "../routeMeta";

const toneLabels: Record<string, string> = {
  neutral: "观察",
  accent: "重点",
  success: "正常",
  warning: "谨慎",
  danger: "风险",
  info: "信息",
  purple: "规则",
  magenta: "研究",
  amber: "提醒"
};

export function TodayPage({ snapshot }: { snapshot: TodayPagePayload }) {
  const navigate = useNavigate();
  const metrics = snapshot.dashboard.metrics;
  const main = metrics[0];
  const fundTickets = snapshot.research?.fund_cards ?? [];
  const todayAnalysis = getTodayAnalysis(snapshot);
  const todayAnalysisSystem = getTodayAnalysisSystem(snapshot.system);
  const keyMemories = [
    ...snapshot.longMemory.fund.slice(0, 2),
    ...snapshot.longMemory.market.slice(0, 2),
    ...snapshot.longMemory.execution.slice(0, 2),
    ...snapshot.longMemory.portfolio.slice(0, 2)
  ].slice(0, 6);
  const decision = (todayAnalysis?.decision ?? {}) as Record<string, unknown>;
  const analysis = (todayAnalysis?.analysis ?? {}) as Record<string, unknown>;
  const meta = (todayAnalysis?.meta ?? todayAnalysis?.updates ?? {}) as Record<string, unknown>;
  const prohibited = extractStringList(decision, ["prohibited_actions", "forbidden_actions", "avoid_actions"]);
  const allowed = extractStringList(decision, ["allowed_actions", "allowed_conditions", "watchlist"]);
  const briefLines = lines(todayAnalysis?.brief || snapshot.dashboard.summary_text, "今日分析尚未生成，可点击左侧“今日分析”运行。");
  const runStatus = pickAnalysisValue(todayAnalysis?.runStatus, analysis?.run_status, analysis?.status, meta?.run_status, todayAnalysisSystem?.runStatus);
  const analysisQuality = pickAnalysisValue(
    todayAnalysis?.analysisQuality,
    analysis?.analysis_quality,
    meta?.analysis_quality,
    todayAnalysisSystem?.analysisQuality
  );
  const memoryEligible = pickAnalysisValue(
    todayAnalysis?.memoryEligible,
    analysis?.memory_eligible,
    meta?.memory_eligible,
    todayAnalysisSystem?.memoryEligible
  );
  const syncState = pickAnalysisValue(analysis?.sync_state, meta?.sync_state, analysis?.context_available);
  const memoryUpdateState = pickAnalysisValue(
    meta?.status,
    meta?.summary,
    (analysis?.memory_cycle as Record<string, unknown> | undefined)?.status,
    (analysis?.memory_cycle as Record<string, unknown> | undefined)?.summary,
    todayAnalysisSystem?.memoryCycleSummary
  );
  const portfolioTrend = snapshot.portfolio.history.totalValue;
  const hasPortfolioTrend = portfolioTrend.some((point) => point.value !== null);

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-1 gap-4">
        <Card className="min-h-[246px] p-5">
          <div className="flex items-center justify-between">
            <div className="text-xs font-black text-cyan-300">今日分析决策</div>
            <Badge tone={main?.tone ?? "accent"}>{toneLabels[main?.tone ?? "accent"] ?? "就绪"}</Badge>
          </div>
          <div className="mt-8 text-4xl font-black text-slate-50">{main?.value ?? "暂无主动作"}</div>
          <div className="mt-3 text-sm font-semibold text-slate-300">{main?.title ?? "今日判断"}</div>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400">{main?.body ?? "暂无需要立刻执行的动作。"}</p>
        </Card>
        <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-3">
          {metrics.slice(1, 4).map((metric) => (
            <MetricCard key={metric.title} {...metric} />
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <SectionTitle title="今日分析链路" meta={snapshot.selectedDate} />
          <div className="grid grid-cols-2 gap-3">
            <MiniStat label="记忆总数" value={String(snapshot.longMemory.counts.total ?? 0)} />
            <MiniStat label="待确认" value={String(snapshot.longMemory.counts.pending ?? 0)} tone="warning" />
            <MiniStat label="基金画像" value={String(snapshot.longMemory.counts.fund ?? 0)} tone="info" />
            <MiniStat label="执行纪律" value={String(snapshot.longMemory.counts.execution ?? 0)} tone="success" />
          </div>
          <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-xs leading-6 text-slate-400">
            <div>运行状态：{text(runStatus !== undefined ? valueLabel(runStatus) : undefined, "暂无")}</div>
            <div>分析质量：{text(analysisQuality !== undefined ? valueLabel(analysisQuality) : undefined, "暂无")}</div>
            <div>可入记忆：{text(memoryEligible !== undefined ? valueLabel(memoryEligible) : undefined, "暂无")}</div>
            <div>数据同步：{text(syncState, "未记录")}</div>
            <div>记忆更新：{text(memoryUpdateState, "已接入本地长期记忆")}</div>
          </div>
        </Card>

        <Card className="p-4">
          <SectionTitle title="今日禁止动作" />
          <ActionList items={prohibited.length ? prohibited : lines(snapshot.dashboard.market_text).slice(0, 4)} tone="danger" />
        </Card>

        <Card className="p-4">
          <SectionTitle title="允许动作与条件" />
          <ActionList items={allowed.length ? allowed : lines(snapshot.dashboard.focus_text).slice(0, 4)} tone="success" />
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <SectionTitle title="组合状态" meta={snapshot.portfolio.asOfDate} />
          <div className="metric-number text-3xl font-black text-slate-50">{snapshot.portfolio.totalValueText}</div>
          <div className="mt-2 text-sm text-slate-500">
            现金 {snapshot.portfolio.cashText} | 持仓 {snapshot.portfolio.items.length} 只
          </div>
          {hasPortfolioTrend ? (
            <div className="mt-5 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={portfolioTrend}>
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={["dataMin", "dataMax"]} />
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid #263345", borderRadius: 8 }}
                    formatter={(value) => [compactMoney(value), "总资产"]}
                  />
                  <Area type="monotone" dataKey="value" stroke="#22d3ee" fill="#164e63" fillOpacity={0.35} connectNulls={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-5 flex h-32 items-center justify-center rounded-md border border-dashed border-slate-800 bg-slate-950/40 px-4 text-center text-sm text-slate-500">
              暂无真实资产历史，当前不展示趋势图。
            </div>
          )}
        </Card>

        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <SectionTitle title="基金 Ticket" meta={`${fundTickets.length} 张`} />
            <Button variant="ghost" className="h-8 shrink-0 gap-1 px-2" onClick={() => navigate(routeForPage("research", snapshot.selectedDate))}>
              完整研究页
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
          <div className="space-y-2">
            {fundTickets.length ? (
              fundTickets.slice(0, 6).map((card) => <TicketPreview key={card.ticketId} card={card} />)
            ) : (
              <p className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-500">
                暂无基金 Ticket。运行今日分析或切换到已有数据日期后会显示每日建议卡。
              </p>
            )}
          </div>
        </Card>

        <Card className="p-4">
          <SectionTitle title="关键长期记忆" meta={`${keyMemories.length} 条候选`} />
          <div className="space-y-2">
            {keyMemories.length ? keyMemories.map((item) => <MemoryLine key={item.memory_id} item={item} />) : <p className="text-sm text-slate-500">暂无可展示的长期记忆。</p>}
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <SectionTitle title="今日摘要" meta="today_analysis_brief" />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {briefLines.slice(0, 10).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
        <Card className="p-4">
          <SectionTitle title="投委会结论" />
          <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-400">{snapshot.dashboard.committee_text || "暂无投委会结论。"}</pre>
        </Card>
      </section>
    </div>
  );
}

function TicketPreview({ card }: { card: FundResearchCard }) {
  const pnlTone = numericTone(card.portfolio.holdingPnl);
  const newsRisk = Number(card.news.riskCount ?? 0);
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">{card.fundName}</div>
          <div className="mt-1 text-xs text-slate-500">
            <span className="metric-number">{card.fundCode}</span>
            <span className="mx-1.5">|</span>
            <span>{card.selectedDate}</span>
          </div>
        </div>
        <Badge tone={actionTone(card.action)}>{card.actionLabel || actionLabel(card.action)}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <TicketMini label="金额" value={card.amountText || "不可用"} />
        <TicketMini label="收益" value={text(card.portfolio.holdingPnlText, "0.00")} tone={pnlTone} />
        <TicketMini label="新闻" value={String(card.news.count ?? 0)} tone={newsRisk ? "warning" : "neutral"} />
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">{card.thesis}</p>
    </div>
  );
}

function TicketMini({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const color = tone === "success" ? "text-emerald-200" : tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-200" : "text-slate-200";
  return (
    <div className="min-w-0 rounded border border-slate-800 bg-slate-950/70 px-2 py-1.5">
      <div className="text-[11px] text-slate-600">{label}</div>
      <div className={`metric-number mt-1 truncate font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function actionTone(action: string): Tone {
  if (["buy", "add", "scheduled_dca", "planned_dca"].includes(action)) return "accent";
  if (["sell", "reduce", "switch"].includes(action)) return "danger";
  if (["locked", "not_applicable"].includes(action)) return "warning";
  return "neutral";
}

function numericTone(value: unknown): Tone {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return "neutral";
  return numeric > 0 ? "success" : "danger";
}

function extractStringList(source: Record<string, unknown>, keys: string[]): string[] {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) return value.map(actionConstraintText).filter(Boolean);
    if (typeof value === "string" && value.trim()) return lines(value);
  }
  return [];
}

function actionConstraintText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const record = value as Record<string, unknown>;
  const title = firstString(record, ["title", "label", "name"]);
  const detail = firstString(record, ["text", "description", "reason", "entity_key"]);
  if (title && detail && title !== detail) return `${title}：${detail}`;
  return title || detail;
}

function firstString(source: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function MiniStat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "success" | "warning" | "info" }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`metric-number mt-1 text-xl font-bold ${tone === "warning" ? "text-amber-200" : tone === "success" ? "text-emerald-200" : tone === "info" ? "text-cyan-200" : "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

function ActionList({ items, tone }: { items: string[]; tone: "danger" | "success" }) {
  return (
    <ul className="space-y-2">
      {items.slice(0, 5).map((item, index) => (
        <li key={`${item}-${index}`} className="flex gap-2 text-sm leading-6 text-slate-400">
          <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${tone === "danger" ? "bg-rose-300" : "bg-emerald-300"}`} />
          {item}
        </li>
      ))}
    </ul>
  );
}

function MemoryLine({ item }: { item: LongMemoryRecord }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="truncate text-sm font-semibold text-slate-200">{memoryTitle(item.title)}</div>
        <Badge tone={item.status === "permanent" ? "success" : item.status === "strategic" ? "warning" : "info"}>{statusLabel(item.status)}</Badge>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{memoryText(item.text)}</p>
    </div>
  );
}
