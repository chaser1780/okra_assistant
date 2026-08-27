import { AlertTriangle, CheckCircle2, CircleDot, Eye, FileWarning, ShieldCheck } from "lucide-react";
import type { ShadowReviewItem, ShadowReviewPagePayload, Tone } from "../../lib/types";
import { Badge, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { StrategySimulationPanel } from "../../components/okra/StrategySimulationPanel";
import { asNumber, compactMoney, signedMoney, text } from "../../lib/format";
import { actionLabel, fieldLabel, narrativeText, valueLabel } from "../../lib/display";

const statusCopy: Record<string, { label: string; body: string; tone: Tone }> = {
  missing: { label: "缺失", body: "当前日期没有可用的官方或影子审查产物。", tone: "neutral" },
  not_run: { label: "未运行", body: "官方建议存在，但影子动作票据尚未生成。", tone: "warning" },
  running: { label: "运行中", body: "影子审查正在运行；本页面只展示可读取的审计内容。", tone: "info" },
  ready: { label: "就绪", body: "官方建议、影子票据、检索包和辩论轨迹均可读取。", tone: "success" },
  partial: { label: "部分可用", body: "部分影子产物缺失；当前只展示可恢复的只读内容。", tone: "warning" },
  degraded: { label: "降级", body: "部分影子产物降级或无效，但仍展示可恢复内容。", tone: "danger" },
  failed: { label: "失败", body: "影子审查无法恢复可比较项目，请检查产物状态。", tone: "danger" }
};

const categoryTone: Record<string, Tone> = {
  same: "success",
  changed: "warning",
  new_shadow_only: "info",
  legacy_only: "neutral",
  missing: "neutral",
  error: "danger"
};

export function ShadowReviewPage({ shadowReview }: { shadowReview: ShadowReviewPagePayload }) {
  const copy = statusCopy[shadowReview.status] ?? statusCopy.missing;
  const summary = shadowReview.summary;
  const agreement = summary.agreementRate == null ? "N/A" : `${(asNumber(summary.agreementRate) * 100).toFixed(0)}%`;
  const missing = shadowReview.artifacts.missing ?? [];

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={copy.tone}>{copy.label}</Badge>
            <Badge tone="neutral" className="gap-1">
              <Eye className="h-3 w-3" />
              仅供审查
            </Badge>
            <Badge tone="neutral" className="gap-1">
              <ShieldCheck className="h-3 w-3" />
              不可执行
            </Badge>
          </div>
          <h2 className="mt-5 text-2xl font-black text-slate-50">{shadowReview.selectedDate}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-400">{copy.body}</p>
          <div className="mt-5 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-xs leading-6 text-slate-400">
            <div>生成时间：{shadowReview.generatedAt || "暂无"}</div>
            <div>执行权限：{shadowReview.guardrails.executionDisabled ? "已禁用" : "未禁用"}</div>
            <div>影响组合：{shadowReview.guardrails.affectsPortfolio ? "是" : "否"}</div>
            <div>影响长期记忆：{shadowReview.guardrails.affectsLongMemoryPromotion ? "是" : "否"}</div>
          </div>
        </Card>

        <div className="col-span-7 grid grid-cols-3 gap-4">
          <MetricCard title="官方动作" value={String(summary.legacyCount)} body="已验证的官方建议动作" tone="accent" />
          <MetricCard title="影子动作" value={String(summary.shadowCount)} body="影子动作票据" tone="info" />
          <MetricCard title="可比较" value={String(summary.comparableCount)} body={`一致率 ${agreement}`} tone="success" />
          <MetricCard title="发生变化" value={String(summary.changedCount)} body="官方和影子动作标签不同" tone={summary.changedCount ? "warning" : "neutral"} />
          <MetricCard title="高风险差异" value={String(summary.highRiskDiffCount ?? 0)} body="触发硬约束阻断的差异" tone={summary.highRiskDiffCount ? "danger" : "neutral"} />
          <MetricCard title="缺失产物" value={String(missing.length)} body="缺失、无效或未生成的产物" tone={missing.length ? "warning" : "success"} />
        </div>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-4">
          <SectionTitle title="产物状态" meta={shadowReview.artifacts.evalReportPath ? "高级诊断路径已记录" : ""} />
          <div className="space-y-2">
            {Object.entries(shadowReview.artifacts.states ?? {}).map(([kind, state]) => (
              <div key={kind} className="flex items-center justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
                <span className="truncate text-slate-400">{fieldLabel(kind)}</span>
                <Badge tone={state === "ready" ? "success" : state === "not_run" ? "neutral" : "warning"}>{valueLabel(state)}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-7 p-4">
          <SectionTitle title="缺失或降级说明" />
          {missing.length ? (
            <div className="space-y-2">
              {missing.slice(0, 8).map((item) => (
                <div key={`${item.kind}-${item.path}-${item.reason}`} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={item.reason === "invalid_json" ? "danger" : "warning"} className="gap-1">
                      <FileWarning className="h-3 w-3" />
                      {fieldLabel(item.kind)}
                    </Badge>
                    <span className="text-xs text-slate-500">{valueLabel(item.reason)}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{missingArtifactMessage(item.kind, item.reason)}</p>
                  {item.path ? <div className="mt-1 text-xs text-slate-600">原始路径已收录在高级诊断中</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="没有缺失产物" body="当前日期没有报告缺失、无效或降级的审查产物。" />
          )}
        </Card>
      </section>

      <StrategySimulationPanel selectedDate={shadowReview.selectedDate} />

      <ExperimentSnapshotPanel experiments={shadowReview.strategyExperiments ?? []} />

      <Card className="p-4">
        <SectionTitle title="实验与正式建议对照" meta={`${shadowReview.items.length} 项`} />
        {shadowReview.items.length ? (
          <div className="space-y-3">
            {shadowReview.items.map((item) => (
              <ShadowReviewCard key={item.reviewId} item={item} />
            ))}
          </div>
        ) : (
          <EmptyState title="暂无可比较建议" body="本页面不会从快照或无关产物中合成审查项目。" />
        )}
      </Card>
    </div>
  );
}

function ExperimentSnapshotPanel({ experiments }: { experiments: NonNullable<ShadowReviewPagePayload["strategyExperiments"]> }) {
  return (
    <Card className="p-4">
      <SectionTitle title="隔离实验快照" meta="实验组合与用户模拟组合永久隔离；金额变化不是收益结论" />
      {experiments.length ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {experiments.map((experiment) => {
            const actionCounts = experiment.actionCounts as Record<string, number> | undefined;
            const actionSummary = actionCounts ? Object.entries(actionCounts).map(([action, count]) => `${actionLabel(action)} ${count}`).join(" / ") : "暂无假设交易";
            return <div key={experiment.experimentId} className="border border-amber-500/20 bg-amber-950/10 p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-100">{experiment.label}</div><div className="mt-1 text-xs text-slate-500">{experiment.asOfDate || "暂无日期"}</div></div><Badge tone="warning">{valueLabel(experiment.status)}</Badge></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><div className="text-xs text-slate-500">当前组合值</div><div className="metric-number mt-1 text-slate-200">{compactMoney(experiment.totalValue)}</div></div><div><div className="text-xs text-slate-500">相对初始变化</div><div className={`metric-number mt-1 ${Number(experiment.valueDelta) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{experiment.valueDelta == null ? "不可用" : signedMoney(experiment.valueDelta)}</div></div></div><div className="mt-3 border-t border-amber-500/10 pt-2 text-xs text-slate-500">{experiment.actionCount} 笔假设交易 · {actionSummary}</div></div>;
          })}
        </div>
      ) : <EmptyState title="暂无隔离实验" body="创建策略实验后，这里只展示实验组合快照和假设交易数量，不会影响用户模拟组合。" />}
    </Card>
  );
}

function ShadowReviewCard({ item }: { item: ShadowReviewItem }) {
  const notes = Array.isArray(item.diff?.notes) ? item.diff.notes : [];
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-bold text-slate-100">{item.displayLabel || item.fundCode}</h3>
            <Badge tone={categoryTone[item.category] ?? "neutral"}>{valueLabel(item.category)}</Badge>
            <Badge tone={item.severity === "high" ? "danger" : item.severity === "medium" ? "warning" : "neutral"}>{valueLabel(item.severity)}</Badge>
            <Badge tone="neutral">仅供审查</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">{narrativeText(item.display?.primaryText, "暂无审查摘要")}</p>
        </div>
        {item.diff?.actionChanged ? <AlertTriangle className="h-5 w-5 shrink-0 text-amber-300" /> : <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-300" />}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <CompareBlock title="Official" payload={item.legacy} />
        <CompareBlock title="Shadow" payload={item.shadow} />
      </div>

      <div className="mt-4 grid grid-cols-12 gap-3">
        <InfoBlock className="col-span-4" title="硬约束" value={guardrailText(item.guardrails)} />
        <InfoBlock className="col-span-4" title="检索" value={retrievalText(item.retrieval)} />
        <InfoBlock className="col-span-4" title="辩论" value={debateText(item.debate)} />
      </div>

      <div className="mt-3 grid grid-cols-12 gap-3">
        <InfoBlock className="col-span-4" title="软策略" value={policyText(item.softPolicies)} />
        <InfoBlock className="col-span-4" title="策略技能" value={skillText(item.skillRefs, item.skillOutputs)} />
        <InfoBlock className="col-span-4" title="结果" value={outcomeText(item.outcomeEvents)} />
      </div>

      {notes.length ? (
        <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-400">
          {notes.slice(0, 4).map((note) => (
            <li key={note} className="flex gap-2">
              <CircleDot className="mt-1 h-4 w-4 shrink-0 text-cyan-300" />
              {note}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function CompareBlock({ title, payload }: { title: string; payload?: Record<string, unknown> | null }) {
  if (!payload) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-950 p-3">
        <div className="text-xs font-bold text-slate-500">{title === "Official" ? "官方" : title === "Shadow" ? "影子" : title}</div>
        <p className="mt-2 text-sm text-slate-500">暂无记录</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-bold text-slate-500">{title === "Official" ? "官方" : title === "Shadow" ? "影子" : title}</div>
        <Badge tone="info">{valueLabel(payload.action ?? "none")}</Badge>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-slate-400">{narrativeText(payload.thesis, "暂无判断依据")}</p>
      <div className="mt-2 text-xs text-slate-600">置信度：{String(payload.confidence ?? 0)}</div>
    </div>
  );
}

function InfoBlock({ title, value, className }: { title: string; value: string; className?: string }) {
  return (
    <div className={`rounded-md border border-slate-800 bg-slate-950 p-3 ${className ?? ""}`}>
      <div className="text-xs font-bold text-slate-500">{title}</div>
      <div className="mt-2 text-sm text-slate-300">{value}</div>
    </div>
  );
}

function guardrailText(value?: Record<string, unknown>) {
  if (!value) return "未运行";
  return `阻断 ${value.block ?? 0} 项，调整 ${value.adjust ?? 0} 项，通过 ${value.pass ?? 0} 项`;
}

function retrievalText(value?: Record<string, unknown> | null) {
  if (!value) return "未运行";
  const completeness = typeof value.traceCompletenessRate === "number" ? `${Math.round(value.traceCompletenessRate * 100)}%` : "未报告";
  return `追溯完整度 ${completeness}，缺失 ${value.missingDataCount ?? 0} 项，RAG 轨迹 ${value.ragTraceCount ?? 0} 条`;
}

function debateText(value?: Record<string, unknown> | null) {
  if (!value) return "未运行";
  return `结论 ${valueLabel(value.verdict)}；${value.writesTicketFile ? "已生成影子建议卡" : "未写入影子建议卡"}`;
}

function policyText(value?: Array<Record<string, unknown>>) {
  if (!value?.length) return "暂无软策略调整";
  const first = value[0];
  return `${value.length} 条；${text(first.policy_id ?? first.policyId ?? first.effect_type, "策略说明")}`;
}

function skillText(refs?: Array<Record<string, unknown>>, outputs?: Array<Record<string, unknown>>) {
  const refCount = refs?.length ?? 0;
  const outputCount = outputs?.length ?? 0;
  if (!refCount && !outputCount) return "暂无策略技能";
  const first = refs?.[0] ?? outputs?.[0] ?? {};
  return `引用 ${refCount} 条，输出 ${outputCount} 条；${text(first.skill_id ?? first.skillId ?? first.output_type, "技能轨迹")}`;
}

function outcomeText(value?: Array<Record<string, unknown>>) {
  if (!value?.length) return "暂无复盘结果";
  const scored = value.filter((item) => item.scoring_status === "scored").length;
  const pending = value.filter((item) => item.scoring_status === "pending").length;
  const first = value[0];
  return `${value.length} 条；已评估 ${scored} 条，待评估 ${pending} 条；${text(first.outcome_label, "暂无结论")}`;
}

function missingArtifactMessage(kind: unknown, reason: unknown) {
  if (reason === "invalid_json") return "该审查产物无法解析，请在高级诊断中检查数据格式。";
  if (reason === "missing_source") return "该审查产物依赖的上游来源尚未生成，当前无法提供可追溯内容。";

  const messages: Record<string, string> = {
    legacyAdvice: "官方建议产物尚未生成，暂时无法与实验建议进行对照。",
    actionTickets: "影子建议卡尚未生成，当前不展示假设动作。",
    retrievalPacks: "检索追溯包尚未生成，暂时无法核对证据链。",
    actionDebates: "影子辩论产物尚未生成，暂时无法核对观点差异。",
    adaptivePolicies: "策略记忆调整信息尚未生成。",
    strategySkills: "策略技能记录尚未生成。",
    outcomeEvents: "当前日期没有可用复盘结果。",
    evalReport: "审查报告尚未生成。"
  };
  return messages[String(kind)] ?? "该审查产物当前不可用，请在高级诊断中查看具体原因。";
}
