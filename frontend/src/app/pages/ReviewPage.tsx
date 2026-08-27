import { Check, ExternalLink, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { LongMemoryPayload, LongMemoryRecord, MemoryAction, ReviewPayload, Tone } from "../../lib/types";
import { compactMoney, lines } from "../../lib/format";
import { actionLabel, domainLabel, entityLabel, evidencePathLabel, memoryText, memoryTitle, statusLabel, valueLabel } from "../../lib/display";
import { Badge, Button, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { TerminalPanel } from "../../components/okra/TerminalChrome";

type TabKey = "fund" | "market" | "execution" | "pending";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "fund", label: "基金画像" },
  { key: "market", label: "大盘规律" },
  { key: "execution", label: "执行纪律" },
  { key: "pending", label: "待确认策略" }
];

export function ReviewPage({
  review,
  longMemory,
  onMemoryAction
}: {
  review: ReviewPayload;
  longMemory: LongMemoryPayload;
  onMemoryAction: (memoryId: string, action: MemoryAction, note?: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<TabKey>("pending");
  const [noteById, setNoteById] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState("");
  const trust = review.trust;
  const tabRecords = useMemo(() => {
    if (tab === "pending") return longMemory.pending;
    return longMemory[tab];
  }, [longMemory, tab]);

  async function act(memoryId: string, action: MemoryAction) {
    setBusyId(memoryId);
    try {
      await onMemoryAction(memoryId, action, noteById[memoryId] ?? "");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="space-y-4">
      <section className="flex flex-wrap items-center justify-between gap-3 border-y border-slate-800 bg-slate-950/40 px-4 py-3">
        <div>
          <div className="text-sm font-bold text-slate-100">学习可信状态</div>
          <div className="mt-1 text-xs text-slate-500">
            {trust?.latestReplayAuditPath || trust?.manifestPath ? "已加载审计依据" : "尚无历史回放信任清单"}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={trust?.mode === "trusted" ? "success" : trust?.mode === "structural_only" ? "warning" : "danger"}>
            {valueLabel(trust?.mode || "blocked")}
          </Badge>
          <Badge tone={trust?.learningEligible ? "info" : "neutral"}>
            {trust?.learningEligible ? "可进入学习候选" : "不可学习"}
          </Badge>
          <Badge tone={trust?.trustedForLearning ? "success" : "warning"}>
            {trust?.trustedForLearning ? "审计通过" : "尚未通过审计"}
          </Badge>
        </div>
      </section>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {review.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} />
        ))}
      </div>
      <TerminalPanel title="记忆生命周期" meta="候选 → 实验中 → 验证策略 → 永久；永久影响必须显式确认" className="p-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <LifecycleNode label="候选" value={longMemory.counts.pending ?? 0} tone="warning" />
          <LifecycleNode label="实验中" value={longMemory.lifecycle?.statusCounts?.experimental_active ?? 0} tone="info" />
          <LifecycleNode label="验证策略" value={longMemory.lifecycle?.statusCounts?.validated_strategy ?? 0} tone="accent" />
          <LifecycleNode label="兼容策略" value={longMemory.lifecycle?.statusCounts?.strategic ?? review.metrics.find((item) => item.title === "战略规则")?.value ?? "0"} tone="accent" />
          <LifecycleNode label="永久" value={review.metrics.find((item) => item.title === "永久规则")?.value ?? "0"} tone="success" />
          <LifecycleNode label="审计状态" value={trust?.trustedForLearning ? "通过" : "阻断"} tone={trust?.trustedForLearning ? "success" : "danger"} />
        </div>
      </TerminalPanel>

      <MemoryEventTimeline events={longMemory.recentEvents ?? []} />

      <DecisionTracePanel trace={review.decisionTrace} />

      <ReviewQualityPanels quality={review.quality} />

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 xl:col-span-3">
          <SectionTitle title="长期记忆总览" meta={longMemory.updatedAt} />
          <div className="space-y-2">
            <CountLine label="基金画像" value={longMemory.counts.fund ?? 0} />
            <CountLine label="大盘规律" value={longMemory.counts.market ?? 0} />
            <CountLine label="执行纪律" value={longMemory.counts.execution ?? 0} />
            <CountLine label="组合策略" value={longMemory.counts.portfolio ?? 0} />
            <CountLine label="待确认策略" value={longMemory.counts.pending ?? 0} tone="warning" />
          </div>
        </Card>

        <Card className="col-span-12 p-4 xl:col-span-9">
          <div className="mb-4 flex flex-col items-stretch justify-between gap-4 sm:flex-row sm:items-center">
            <SectionTitle title="长期记忆中心" meta="本地 SQLite/JSON 为真实源；全文检索和向量仅作为索引层" />
            <div className="grid w-full grid-cols-2 rounded-md border border-slate-800 bg-slate-950 p-1 sm:w-auto sm:grid-cols-4">
              {tabs.map((item) => (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  className={`h-8 min-w-0 rounded px-2 text-xs font-bold transition sm:px-3 ${
                    tab === item.key ? "bg-cyan-500/20 text-cyan-100" : "text-slate-500 hover:text-slate-200"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {tabRecords.length ? (
            <div className="space-y-3">
              {tabRecords.map((record) => (
                <MemoryCard
                  key={record.memory_id}
                  record={record}
                  pending={tab === "pending"}
                  busy={busyId === record.memory_id}
                  note={noteById[record.memory_id] ?? ""}
                  onNote={(value) => setNoteById((current) => ({ ...current, [record.memory_id]: value }))}
                  onAction={(action) => void act(record.memory_id, action)}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title="暂无长期记忆"
              body="运行今日分析或长期记忆更新后，这里会展示基金画像、大盘规律、执行纪律和待确认策略。"
            />
          )}
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 md:col-span-4">
          <SectionTitle title="旧复盘摘要" meta={review.meta} />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {lines(review.summary_text).slice(0, 10).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
        <Card className="col-span-12 p-4 md:col-span-4">
          <SectionTitle title="兼容永久规则" />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {(review.core_lines.length ? review.core_lines : ["暂无兼容规则"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
        <Card className="col-span-12 p-4 md:col-span-4">
          <SectionTitle title="重放学习" />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {(review.replay_lines.length ? review.replay_lines : ["暂无重放实验"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
      </section>

      <Card className="p-4">
        <SectionTitle title="复盘报告" meta="迁移期保留旧报告；新的永久规则以审批区为准" />
        <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap text-sm leading-7 text-slate-400">{review.detail_text}</pre>
      </Card>
    </div>
  );
}

function LifecycleNode({ label, value, tone }: { label: string; value: string | number; tone: Tone }) {
  return <div className="border border-slate-800 bg-[#0b0e12] px-3 py-3"><div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</div><div className={`metric-number mt-2 text-xl font-semibold ${tone === "success" ? "text-emerald-300" : tone === "danger" ? "text-rose-300" : tone === "warning" ? "text-amber-300" : "text-cyan-200"}`}>{value}</div></div>;
}

function MemoryEventTimeline({ events }: { events: NonNullable<LongMemoryPayload["recentEvents"]> }) {
  return (
    <TerminalPanel title="记忆迁移账本" meta="创建、状态迁移、审批和替代均以本地事件记录为准" className="p-4">
      {events.length ? (
        <div className="max-h-64 overflow-auto divide-y divide-slate-800/80 border border-slate-800">
          {events.slice(0, 16).map((event) => (
            <div key={event.eventId} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2 text-sm">
              <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><Badge tone={event.sourceTrack === "strategy_simulation" ? "warning" : "info"}>{memoryEventLabel(event.eventType)}</Badge><span className="metric-number truncate text-xs text-slate-400">{event.memoryId}</span>{event.experimentId ? <Badge tone="warning">实验来源</Badge> : null}</div><div className="mt-1 truncate text-xs text-slate-500">{memoryStatusLabel(event.fromStatus)} → {memoryStatusLabel(event.toStatus)}{event.note ? ` · ${event.note}` : ""}</div></div>
              <div className="shrink-0 text-right text-xs text-slate-500"><div>{event.actor || "system"}</div><div className="mt-1">{event.createdAt ? event.createdAt.slice(0, 16).replace("T", " ") : "暂无时间"}</div></div>
            </div>
          ))}
        </div>
      ) : <EmptyState title="暂无记忆迁移事件" body="新建记忆、进入实验策略、用户确认、归档或替代后，这里会留下本地审计记录。" />}
    </TerminalPanel>
  );
}

function memoryEventLabel(value: string) {
  const labels: Record<string, string> = { created: "创建", updated: "更新", transition: "状态迁移", approval: "用户确认", superseded: "被替代" };
  return labels[value] ?? "记忆事件";
}

function memoryStatusLabel(value: string) {
  return value ? statusLabel(value) : "初始";
}

function DecisionTracePanel({ trace }: { trace?: ReviewPayload["decisionTrace"] }) {
  if (!trace?.available) {
    return <TerminalPanel title="当日决策追溯" meta="仅展示已生成的只读决策链" className="p-4"><EmptyState title="当前日期没有决策追溯" body="运行完成后，这里会显示建议来源、证据规模、模型调用数量和模拟执行边界。" /></TerminalPanel>;
  }
  const decisions = Array.isArray(trace.decisions) ? trace.decisions : [];
  return (
    <TerminalPanel title="当日决策追溯" meta="只读 · 用户模拟轨道 · 不产生交易指令" className="p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <TraceMetric label="建议数量" value={String(trace.decisionCount ?? 0)} />
        <TraceMetric label="证据快照" value={`${String(trace.evidenceCount ?? 0)} 条`} />
        <TraceMetric label="模型运行" value={`${String(trace.modelRunCount ?? 0)} 次`} />
        <TraceMetric label="链路产物" value={`${String(trace.availableArtifactCount ?? 0)} 项`} />
        <TraceMetric label="执行边界" value={trace.executionEligible ? "模拟可应用" : "仅供审查"} tone={trace.executionEligible ? "info" : "warning"} />
      </div>
      <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/45">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-3 py-2 text-xs">
          <span className="font-semibold text-slate-300">来源：{valueLabel(trace.source)}</span>
          <span className="text-slate-500">报告日期 {trace.reportDate}</span>
        </div>
        {decisions.length ? decisions.map((item, index) => {
          const fund = `${String(item.fundName || "")} ${String(item.fundCode || "")}`.trim() || "未标注基金";
          const confidence = Number(item.confidence);
          return <div key={`${String(item.fundCode)}-${index}`} className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 border-b border-slate-800/70 px-3 py-2 text-sm last:border-b-0"><div className="min-w-0"><div className="truncate font-semibold text-slate-200">{fund}</div><div className="mt-1 text-xs text-slate-500">{String(item.section || "建议")}</div></div><div className="text-right text-slate-400">{item.amount == null ? "金额未设" : compactMoney(item.amount)}</div><div className="text-right"><Badge tone={item.executionEligible ? "info" : "neutral"}>{actionLabel(item.action)} {Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : ""}</Badge></div></div>;
        }) : <div className="p-3 text-sm text-slate-500">决策追溯已生成，但没有可展示的建议记录。</div>}
      </div>
    </TerminalPanel>
  );
}

function TraceMetric({ label, value, tone = "accent" }: { label: string; value: string; tone?: Tone }) {
  return <div className="border border-slate-800 bg-slate-950/50 px-3 py-3"><div className="text-xs text-slate-500">{label}</div><div className="mt-2 flex items-center justify-between gap-2"><span className="metric-number text-sm font-semibold text-slate-200">{value}</span><Badge tone={tone}>{tone === "warning" ? "受限" : "追溯"}</Badge></div></div>;
}

function ReviewQualityPanels({ quality }: { quality?: ReviewPayload["quality"] }) {
  const advice = quality?.adviceQuality;
  const simulation = quality?.simulationQuality;
  const memory = quality?.memoryQuality;
  const twr = simulation?.twr ?? {};
  const mwr = simulation?.mwr ?? {};
  const drawdown = simulation?.cashflowAdjustedDrawdown ?? {};
  const benchmark = simulation?.benchmark ?? {};
  const trackCounts = memory?.sourceTrackCounts ?? {};
  return (
    <TerminalPanel title="复盘质量" meta="只使用已落库的复盘、用户模拟账本与记忆记录；数据不足时不估算" className="p-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <QualityBlock title="建议质量" tone="accent">
          <QualityLine label="已评估事件" value={`${advice?.scoredEventCount ?? 0} 条`} />
          <QualityLine label="方向一致率" value={qualityPercent(advice?.directionalAccuracyPct)} tone={advice?.directionalAccuracyPct == null ? "neutral" : advice.directionalAccuracyPct >= 50 ? "success" : "danger"} />
          <QualityLine label="支持 / 反向 / 中性" value={`${advice?.supportedCount ?? 0} / ${advice?.adverseCount ?? 0} / ${advice?.neutralCount ?? 0}`} />
          <QualityLine label="明确弃答" value={qualityRate(advice?.abstention?.count, advice?.abstention?.decisionCount)} />
          <p className="mt-3 text-xs leading-5 text-slate-500">{advice?.confidenceCalibration?.reason || "暂无置信度校准数据。"}</p>
        </QualityBlock>
        <QualityBlock title="用户模拟质量" tone="info">
          <QualityLine label="模拟操作" value={`${simulation?.operationCount ?? 0} 笔`} />
          <QualityLine label="换手金额 / 占比" value={`${compactMoney(simulation?.turnoverAmount)} / ${qualityPercent(simulation?.turnoverPct)}`} />
          <QualityLine label="明确费用" value={compactMoney(simulation?.costAmount)} />
          <QualityLine label="TWR / MWR" value={`${performanceValue(twr)} / ${performanceValue(mwr)}`} />
          <QualityLine label="现金流调整回撤" value={performanceValue(drawdown, "currentPct")} />
          <p className="mt-3 text-xs leading-5 text-slate-500">{benchmark.status === "available" ? "组合基准已配置，可在绩效图表中查看相对表现。" : "组合基准未配置，不展示伪造的超额收益。"}</p>
        </QualityBlock>
        <QualityBlock title="记忆质量" tone="warning">
          <QualityLine label="有效记录" value={`${memory?.recordCount ?? 0} 条`} />
          <QualityLine label="反例 / 已过期" value={`${memory?.contradictionCount ?? 0} / ${memory?.expiredCount ?? 0}`} />
          <QualityLine label="重复候选" value={`${memory?.duplicateCount ?? 0} 条`} />
          <QualityLine label="用户 / 实验来源" value={`${trackCounts.user_simulation ?? 0} / ${trackCounts.strategy_simulation ?? 0}`} />
          <p className="mt-3 text-xs leading-5 text-slate-500">实验来源保留在策略验证域，不能静默影响用户模拟组合。</p>
        </QualityBlock>
      </div>
    </TerminalPanel>
  );
}

function QualityBlock({ title, tone, children }: { title: string; tone: Tone; children: React.ReactNode }) {
  const color = tone === "warning" ? "text-amber-200" : tone === "info" ? "text-cyan-200" : "text-cyan-100";
  return <section className="border border-slate-800 bg-slate-950/45 p-3"><h3 className={`text-sm font-bold ${color}`}>{title}</h3><div className="mt-3 space-y-2">{children}</div></section>;
}

function QualityLine({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  const color = tone === "success" ? "text-emerald-300" : tone === "danger" ? "text-rose-300" : "text-slate-200";
  return <div className="flex items-center justify-between gap-3 text-sm"><span className="text-slate-500">{label}</span><span className={`metric-number text-right ${color}`}>{value}</span></div>;
}

function qualityPercent(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "不可用";
}

function qualityRate(count: number | undefined, total: number | undefined) {
  if (!total) return "不可用";
  return `${count ?? 0} / ${total} (${((count ?? 0) / total * 100).toFixed(1)}%)`;
}

function performanceValue(value: Record<string, unknown>, key = "returnPct") {
  if (value.available !== true) return "不可用";
  const numeric = Number(value[key]);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)}%` : "不可用";
}

function CountLine({ label, value, tone = "neutral" }: { label: string; value: number; tone?: Tone }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <Badge tone={tone}>{value}</Badge>
    </div>
  );
}

function MemoryCard({
  record,
  pending,
  busy,
  note,
  onNote,
  onAction
}: {
  record: LongMemoryRecord;
  pending: boolean;
  busy: boolean;
  note: string;
  onNote: (value: string) => void;
  onAction: (action: MemoryAction) => void;
}) {
  const evidence = record.evidence_refs ?? [];
  const canApprove = canApprovePermanent(record);
  const metadata = record.metadata ?? {};
  const strategyExperiment = metadata.sourceTrack === "strategy_simulation" || metadata.simulationSource === "strategy_simulation";
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-slate-100">{memoryTitle(record.title)}</h3>
            <Badge tone={record.isExpired ? "warning" : statusTone(record.status)}>{record.isExpired ? "已过期" : statusLabel(record.effectiveStatus ?? record.status)}</Badge>
            <Badge tone="info">{domainLabel(record.domain)}</Badge>
            <Badge tone="neutral">{entityLabel(record.entity_key)}</Badge>
            {strategyExperiment ? <Badge tone="warning">实验来源</Badge> : <Badge tone="success">用户轨道</Badge>}
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">{memoryText(record.text)}</p>
          {!canApprove && record.domain === "fund" ? (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              基金画像用于长期学习单只基金的行为规律，不会直接设为永久规则；可复用结论会沉淀为组合、执行或大盘策略。
            </p>
          ) : null}
        </div>
        <div className="metric-number shrink-0 text-left text-xs text-slate-500 sm:text-right">
          <div>置信度 {(Number(record.confidence || 0) * 100).toFixed(0)}%</div>
          <div>
            支持 {record.support_count} / 反例 {record.contradiction_count}
          </div>
          {strategyExperiment ? <div>仅用于策略验证</div> : null}
          {record.isExpired ? <div>有效期至 {record.valid_until || "未知"}</div> : null}
        </div>
      </div>

      {evidence.length ? (
        <details className="mt-3 rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
          <summary className="cursor-pointer text-xs font-semibold text-slate-400">证据 {evidence.length} 条</summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {evidence.slice(0, 4).map((item, index) => {
              const path = evidencePathLabel(item.path ?? item.file ?? item.source);
              return (
                <Badge key={`${path}-${index}`} tone="purple" className="max-w-full truncate">
                  <ExternalLink className="mr-1 h-3 w-3" />
                  {path || `证据 ${index + 1}`}
                </Badge>
              );
            })}
          </div>
        </details>
      ) : null}

      {pending ? (
        <div className="mt-4 space-y-3">
          <textarea
            value={note}
            onChange={(event) => onNote(event.target.value)}
            placeholder="可选：写下确认、驳回、归档或降级原因"
            className="min-h-20 w-full resize-y rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-700"
          />
          <div className="flex flex-wrap gap-2">
            {canApprove ? (
              <Button variant="primary" className="gap-2" disabled={busy} onClick={() => onAction("approve")}>
                <Check className="h-4 w-4" />
                确认为永久策略
              </Button>
            ) : (
              <Badge tone="neutral">不作为永久规则</Badge>
            )}
            <Button variant="danger" className="gap-2" disabled={busy} onClick={() => onAction("reject")}>
              <X className="h-4 w-4" />
              驳回
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => onAction("archive")}>
              归档
            </Button>
            <Button variant="ghost" className="gap-2" disabled={busy} onClick={() => onAction("demote")}>
              <RotateCcw className="h-4 w-4" />
              降为候选
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function canApprovePermanent(record: LongMemoryRecord) {
  if (record.can_promote_permanent === false) return false;
  return record.domain !== "fund" && record.memory_type !== "fund_profile_memory";
}

function statusTone(status: string): Tone {
  if (status === "permanent") return "success";
  if (status === "experimental_active") return "info";
  if (status === "validated_strategy") return "accent";
  if (status === "strategic") return "warning";
  if (status === "rejected") return "danger";
  if (status === "archived") return "neutral";
  return "info";
}
