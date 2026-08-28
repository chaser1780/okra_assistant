import { useEffect, useState } from "react";
import { fieldLabel, valueLabel } from "../../lib/display";
import { buildDesktopRuntimeConfig, getDesktopRuntimeConfig } from "../../lib/desktopRuntime";
import { ragRuntimeSchema } from "../../lib/schemas";
import { runtimeStatusMeta } from "../../lib/todayAnalysis";
import type { RagRuntimePayload, SimulationPayload, Tone } from "../../lib/types";
import { Badge, Card, SectionTitle } from "../../components/ui";
import { SimulationTrackRail } from "../../components/okra/ResearchContext";

export function SystemPage({ system, summary }: { system: Record<string, unknown>; summary: Record<string, unknown> }) {
  const llmRuntime = (system.llmRuntime ?? {}) as Record<string, unknown>;
  const todayRuntime = (system.todayAnalysisRuntime ?? {}) as Record<string, unknown>;
  const longMemoryRuntime = (system.longMemoryRuntime ?? {}) as Record<string, unknown>;
  const agentRuntime = (system.agentRuntime ?? {}) as Record<string, unknown>;
  const ragRuntime = ragRuntimeSchema.parse(system.ragRuntime ?? system.rag ?? {}) as RagRuntimePayload;
  const latestTraces = Array.isArray(ragRuntime.latestTraces) ? ragRuntime.latestTraces : [];
  const latestTrace = latestTraces[0] ?? {};
  const hybridSettings = ragRuntime.hybrid ?? {};
  const failedAgents = Array.isArray(agentRuntime.failedAgents) ? agentRuntime.failedAgents : [];
  const degradedAgents = Array.isArray(agentRuntime.degradedAgents) ? agentRuntime.degradedAgents : [];
  const modelRuns = Array.isArray(system.modelRuns) ? system.modelRuns as Array<Record<string, unknown>> : [];
  const decisionTrace = (system.decisionTrace ?? {}) as Record<string, unknown>;
  const sourceHealth = (system.sourceHealth ?? {}) as Record<string, unknown>;
  const simulation = system.simulation as SimulationPayload | undefined;
  const sourceHealthItems = Array.isArray(sourceHealth.items) ? sourceHealth.items as Array<Record<string, unknown>> : [];
  const [desktopRuntime, setDesktopRuntime] = useState(buildDesktopRuntimeConfig);

  useEffect(() => {
    void getDesktopRuntimeConfig().then(setDesktopRuntime);
  }, []);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card className="lg:col-span-2 p-4">
        <SectionTitle title="桌面连接状态" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatusTile label="模式" value={desktopRuntime.mode === "remote" ? "远程" : "本地"} tone={desktopRuntime.mode === "remote" ? "accent" : "success"} />
          <StatusTile label="API 目标" value={desktopRuntime.diagnosticApiBase} tone={desktopRuntime.configured ? "info" : "danger"} />
          <StatusTile label="配置来源" value={runtimeSourceLabel(desktopRuntime.source)} tone={desktopRuntime.configured ? "success" : "warning"} />
        </div>
      </Card>

      <Card className="p-4 lg:col-span-2">
        <SectionTitle title="模型与主链路状态" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <StatusTile label="主模型" value={String(llmRuntime.model ?? "暂无")} tone="accent" stackAtXl />
          <StatusTile label="评审模型" value={String(llmRuntime.reviewModel ?? "暂无")} tone="info" stackAtXl />
          <StatusTile label="今日分析状态" value={runtimeStatusLabel(todayRuntime.status)} tone={runtimeStatusMeta(todayRuntime.status).tone} />
          <StatusTile label="当前 Agent" value={agentLabel(todayRuntime.currentAgent)} tone={todayRuntime.currentAgent ? "success" : "neutral"} />
          <StatusTile label="长期记忆状态" value={runtimeStatusLabel(longMemoryRuntime.status)} tone={runtimeStatusMeta(longMemoryRuntime.status).tone} />
        </div>
      </Card>

      <SimulationTrackRail simulation={simulation} />

      <Card className="p-4 lg:col-span-2">
        <SectionTitle title="数据采集运行轨道" meta="按来源展示本地采集健康与降级状态" />
        {sourceHealthItems.length ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sourceHealthItems.slice(0, 9).map((item, index) => <SourceHealthTile key={`${String(item.source_key ?? item.provider ?? "source")}-${index}`} item={item} />)}
          </div>
        ) : <div className="text-sm text-slate-500">当前日期没有来源运行记录；运行采集后会显示各来源的状态、延迟与降级信息。</div>}
      </Card>

      <Card className="p-4 lg:col-span-2">
        <SectionTitle title="模型运行与决策追溯" meta="只记录哈希、耗时和状态，不保存密钥或完整 Prompt" />
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-sm leading-6 text-slate-400">
            <div>决策来源：{valueLabel(decisionTrace.decisionSource)}</div>
            <div>建议轨道：{valueLabel(decisionTrace.formalTrack)}</div>
            <div>建议数量：{Array.isArray(decisionTrace.decisions) ? decisionTrace.decisions.length : 0}</div>
            <div>证据快照：{String((decisionTrace.evidenceSnapshot as Record<string, unknown> | undefined)?.itemCount ?? 0)} 条</div>
          </div>
          <div className="max-h-44 overflow-auto rounded-md border border-slate-800">
            {modelRuns.length ? modelRuns.map((run) => <div key={String(run.modelRunId)} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-slate-800/70 px-3 py-2 last:border-b-0"><div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-200">{modelRunLabel(run.requestName)}</div><div className="mt-1 truncate text-xs text-slate-500">{String(run.model ?? "")}</div></div><div className="text-right text-xs text-slate-500"><div>{String(run.latencyMs ?? "-")} ms</div><Badge tone={run.status === "ok" ? "success" : "danger"}>{run.status === "ok" ? "完成" : "失败"}</Badge></div></div>) : <div className="p-4 text-sm text-slate-500">当前日期没有模型运行记录。</div>}
          </div>
        </div>
      </Card>

      <Card className="p-4 lg:col-span-2">
        <SectionTitle title="RAG 检索状态" meta={ragModeDescription(latestTrace, hybridSettings)} />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <StatusTile label="最近检索模式" value={ragModeLabel(latestTrace.mode)} tone={latestTrace.mode === "hybrid_lexical_semantic" ? "accent" : "info"} />
          <StatusTile label="语义灰度" value={enabledLabel(hybridSettings.enabled)} tone={hybridSettings.enabled ? "warning" : "neutral"} />
          <StatusTile label="默认接入" value={enabledLabel(ragRuntime.enabled)} tone={ragRuntime.enabled ? "success" : "info"} />
          <StatusTile label="默认 Agent 接入" value={enabledLabel((ragRuntime.agentDefault ?? {}).enabled)} tone={(ragRuntime.agentDefault ?? {}).enabled ? "success" : "info"} />
          <StatusTile label="影子 Agent" value={enabledLabel((ragRuntime.agentShadow ?? {}).enabled)} tone={(ragRuntime.agentShadow ?? {}).enabled ? "success" : "info"} />
          <StatusTile label="旧链路备用" value={enabledLabel(ragRuntime.fallbackToLegacy)} tone={ragRuntime.fallbackToLegacy ? "success" : "warning"} />
          <StatusTile label="文档 / 分块" value={`${countValue(ragRuntime.counts, "documents")} / ${countValue(ragRuntime.counts, "chunks")}`} tone="accent" />
          <StatusTile label="向量待处理 / 错误" value={`${countValue(ragRuntime.embeddingStatus, "pending")} / ${countValue(ragRuntime.embeddingStatus, "error")}`} tone={countValue(ragRuntime.embeddingStatus, "error") ? "warning" : "info"} />
        </div>
        {ragRuntime.statusError ? <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-950/25 p-3 text-sm text-amber-100">RAG 状态存在异常，详细原因已收录在高级诊断中。</div> : null}
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <MiniPanel title="来源计数" value={ragRuntime.sourceCounts ?? {}} />
          <RagEvaluationPanel evaluation={ragRuntime.latestEval ?? {}} />
        </div>
        <RagTraceList traces={latestTraces.slice(0, 5)} />
      </Card>

      <Card className="p-4">
        <SectionTitle title="今日分析运行态" />
        <RuntimeBlock payload={todayRuntime} />
      </Card>

      <Card className="p-4">
        <SectionTitle title="长期记忆运行态" />
        <RuntimeBlock payload={longMemoryRuntime} />
      </Card>

      <Card className="p-4">
        <SectionTitle title="失败与降级 Agent" />
        {failedAgents.length || degradedAgents.length ? (
          <div className="space-y-2">
            {failedAgents.map((item, index) => (
              <div key={index} className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                <div className="font-semibold">{agentLabel((item as Record<string, unknown>).agent_name)}</div>
                <div className="mt-1 text-xs text-slate-500">执行失败，详细错误已收录在高级诊断中。</div>
              </div>
            ))}
            {degradedAgents.map((item, index) => (
              <div key={`degraded-${index}`} className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                <div className="font-semibold">{agentLabel(item)}</div>
                <div className="mt-1 text-xs text-slate-500">已降级，部分结果可能不可用。</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-500">暂无失败或降级 Agent</div>
        )}
      </Card>

      <Card className="p-4">
        <SectionTitle title="模型接线" />
        <div className="space-y-1 text-sm text-slate-400">
          <div>模型提供方：{modelProviderLabel(llmRuntime.modelProvider)}</div>
          <div>主模型：{String(llmRuntime.model ?? "暂无")}</div>
          <div>评审模型：{String(llmRuntime.reviewModel ?? "暂无")}</div>
          <div>推理强度：{reasoningLabel(llmRuntime.reasoningEffort)}</div>
          <div>调用协议：{wireApiLabel(llmRuntime.wireApi)}</div>
          <div>服务地址：{llmRuntime.baseUrlConfigured ? "已配置（已隐藏）" : "未配置"}</div>
        </div>
      </Card>

      <Card className="p-4">
        <details>
          <summary className="cursor-pointer text-sm font-bold text-slate-100">系统摘要 / 高级诊断</summary>
          <div className="mt-4"><KeyValueTree value={summary} /></div>
        </details>
      </Card>

      <Card className="p-4">
        <details>
          <summary className="cursor-pointer text-sm font-bold text-slate-100">原始系统信息 / 高级诊断</summary>
          <div className="mt-4"><KeyValueTree value={system} /></div>
        </details>
      </Card>
    </div>
  );
}

function MiniPanel({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="min-h-[160px] rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="mb-2 text-xs font-bold text-slate-400">{title}</div>
      <KeyValueTree value={value} />
    </div>
  );
}

function StatusTile({
  label,
  value,
  tone = "neutral",
  stackAtXl = false
}: {
  label: string;
  value: string;
  tone?: Tone;
  stackAtXl?: boolean;
}) {
  const badgeLabel = tone === "danger" ? "异常" : tone === "warning" ? "注意" : tone === "success" ? "正常" : tone === "accent" ? "运行中" : "信息";
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 flex gap-3 ${stackAtXl ? "flex-col items-start xl:flex-col 2xl:flex-row 2xl:items-center 2xl:justify-between" : "items-center justify-between"}`}>
        <div className="break-all text-sm font-semibold text-slate-200">{value}</div>
        <Badge tone={tone}>{badgeLabel}</Badge>
      </div>
    </div>
  );
}

function RuntimeBlock({ payload }: { payload: Record<string, unknown> }) {
  const runningAgents = Array.isArray(payload.runningAgents) ? payload.runningAgents : [];
  const failedAgents = Array.isArray(payload.failedAgents) ? payload.failedAgents : [];
  const degradedAgents = Array.isArray(payload.degradedAgents) ? payload.degradedAgents : [];
  return (
    <div className="space-y-1 text-sm text-slate-400">
      <div>状态：{valueLabel(payload.status)}</div>
      <div>阶段：{valueLabel(payload.phase)}</div>
      <div>运行日期：{valueLabel(payload.reportDate)}</div>
      <div>启动时间：{valueLabel(payload.startedAt)}</div>
      <div>已运行：{String(payload.elapsedSeconds ?? 0)} 秒</div>
      <div>当前步骤：{runtimeStepLabel(payload.currentStep)}</div>
      <div>当前 Agent：{agentLabel(payload.currentAgent)}</div>
      <div>当前阶段：{agentStageLabel(payload.currentAgentStage)}</div>
      <div>运行中 Agent：{runningAgents.length ? runningAgents.map(agentLabel).join(" / ") : "暂无"}</div>
      <div>失败 Agent：{failedAgents.length}</div>
      <div>降级 Agent：{degradedAgents.length}</div>
      <div>最近错误：{valueLabel(payload.lastError)}</div>
      {"analysisQuality" in payload ? <div>分析质量：{valueLabel(payload.analysisQuality)}</div> : null}
      {"memoryEligible" in payload ? <div>允许进入记忆：{valueLabel(payload.memoryEligible)}</div> : null}
    </div>
  );
}

function KeyValueTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (!value.length) return <div className="text-sm text-slate-500">暂无</div>;
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={index} className="rounded-md border border-slate-800 bg-slate-950/40 p-2">
            <KeyValueTree value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return <div className="text-sm text-slate-500">暂无</div>;
    return (
      <div className="space-y-2">
        {entries.map(([key, item]) => (
          <div key={key} className={depth ? "border-b border-slate-800/70 pb-2" : "rounded-md border border-slate-800 bg-slate-950/40 p-3"}>
            <div className="mb-1 flex items-center justify-between gap-3 text-sm">
              <span className="font-semibold text-slate-300">{fieldLabel(key)}</span>
              {!isNested(item) ? <ValueBadge value={item} /> : null}
            </div>
            {isNested(item) ? <KeyValueTree value={item} depth={depth + 1} /> : null}
          </div>
        ))}
      </div>
    );
  }
  return <ValueBadge value={value} />;
}

function ValueBadge({ value }: { value: unknown }) {
  const label = valueLabel(value);
  if (label === "正常" || label === "是" || label === "成功" || label === "新鲜") return <Badge tone="success">{label}</Badge>;
  if (label === "注意" || label === "已过期" || label === "兜底") return <Badge tone="warning">{label}</Badge>;
  if (label === "错误" || label === "失败") return <Badge tone="danger">{label}</Badge>;
  return <span className="break-all text-right text-sm text-slate-400">{label}</span>;
}

function isNested(value: unknown) {
  return Boolean(value && typeof value === "object");
}

function enabledLabel(value: unknown) {
  return value === true ? "开启" : value === false ? "关闭" : "暂无";
}

function SourceHealthTile({ item }: { item: Record<string, unknown> }) {
  const runtime = item.runtime && typeof item.runtime === "object" ? item.runtime as Record<string, unknown> : {};
  const metrics = item.metrics && typeof item.metrics === "object" ? item.metrics as Record<string, unknown> : {};
  const status = valueLabel(item.status);
  const tone: Tone = item.status === "ok" ? "success" : item.status === "disabled" ? "neutral" : "warning";
  const source = sourceHealthLabel(item.provider ?? item.source_key);
  const requests = Number(metrics.request_skipped ?? 0);
  const failures = Number(runtime.consecutive_failures ?? 0);
  return <div className="border border-slate-800 bg-slate-950/40 p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-200">{source}</div><div className="mt-1 text-xs text-slate-500">{valueLabel(item.source_role)}</div></div><Badge tone={tone}>{status}</Badge></div><div className="mt-3 text-xs leading-5 text-slate-500">{requests ? "本轮已跳过" : failures ? `连续失败 ${failures} 次` : "本轮已完成健康检查"}</div></div>;
}

function ragModeLabel(value: unknown) {
  if (value === "hybrid_lexical_semantic") return "词法 + 语义重排";
  return "词法检索 + 重排";
}

function ragModeDescription(trace: Record<string, unknown>, hybrid: Record<string, unknown>) {
  const semantic = trace.semantic as Record<string, unknown> | undefined;
  if (trace.mode === "hybrid_lexical_semantic") {
    const coverage = typeof semantic?.coverage === "number" ? `${Math.round(semantic.coverage * 100)}% 向量覆盖` : "语义灰度已生效";
    return `最近一次检索采用词法与语义重排；${coverage}`;
  }
  if (hybrid.enabled === true && semantic?.reason === "insufficient_vector_coverage") return "语义灰度已开启，但最近检索因向量覆盖不足回退至词法重排";
  if (hybrid.enabled === true && semantic?.reason === "embedding_not_live") return "语义灰度已开启，但 embedding 未启用，最近检索回退至词法重排";
  return "默认使用词法检索与重排；语义检索仅在显式灰度且数据满足条件时启用";
}

function RagTraceList({ traces }: { traces: Array<Record<string, unknown>> }) {
  if (!traces.length) return <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-500">暂无检索轨迹。检索发生后会在这里显示实际模式与回退原因。</div>;
  return (
    <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/40">
      <div className="border-b border-slate-800 px-3 py-2 text-xs font-bold text-slate-400">最近检索轨迹</div>
      {traces.map((trace) => {
        const semantic = trace.semantic as Record<string, unknown> | undefined;
        const mode = trace.mode === "hybrid_lexical_semantic" ? "词法 + 语义" : "词法重排";
        const reason = ragTraceReason(semantic);
        return (
          <div key={String(trace.traceId)} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-slate-800/70 px-3 py-2 last:border-b-0">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-200">{ragIntentLabel(trace.intent)} · {String(trace.queryDate || "暂无日期")}</div>
              <div className="mt-1 truncate text-xs text-slate-500">{reason || ragProfileLabel(trace.profile)}</div>
            </div>
            <div className="text-right text-xs text-slate-500">
              <Badge tone={trace.mode === "hybrid_lexical_semantic" ? "accent" : "info"}>{mode}</Badge>
              <div className="mt-1">缺失 {String(trace.missingDataCount ?? 0)} 项</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RagEvaluationPanel({ evaluation }: { evaluation: Record<string, unknown> }) {
  const metrics = evaluation.metrics as Record<string, unknown> | undefined;
  const labeledQueries = numberOrNull(metrics?.gold_labeled_query_count);
  if (labeledQueries === null || labeledQueries === 0) {
    return <div className="min-h-[160px] rounded-md border border-slate-800 bg-slate-950/40 p-3"><div className="mb-2 text-xs font-bold text-slate-400">离线检索评估</div><div className="text-sm leading-6 text-slate-500">暂无人工标注评估集。系统仍会记录命中、引用完整性和未来数据拒绝，但不会伪造 Recall 或 nDCG。</div></div>;
  }
  const rows: Array<[string, unknown, Tone]> = [
    ["Recall@K", metrics?.recall_at_k, "accent"],
    ["nDCG@K", metrics?.nDCG_at_k, "accent"],
    ["证据覆盖", metrics?.evidence_coverage_rate, "success"],
    ["错误召回", metrics?.erroneous_recall_rate, "warning"],
    ["引用正确", metrics?.citation_correctness_rate, "success"],
    ["弃答质量", metrics?.abstention_quality, "info"],
    ["未来数据拒绝", metrics?.future_data_rejection_rate, "success"],
  ];
  return (
    <div className="min-h-[160px] rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-2"><div className="text-xs font-bold text-slate-400">离线检索评估</div><Badge tone="info">标注 {labeledQueries} 条</Badge></div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {rows.map(([label, value, tone]) => <div key={label} className="flex items-center justify-between gap-2"><span className="text-slate-500">{label}</span><Badge tone={tone}>{rateLabel(value)}</Badge></div>)}
      </div>
    </div>
  );
}

function numberOrNull(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function rateLabel(value: unknown) {
  const numeric = numberOrNull(value);
  return numeric === null ? "不可用" : `${(numeric * 100).toFixed(0)}%`;
}

function ragTraceReason(semantic: Record<string, unknown> | undefined) {
  if (!semantic) return "";
  if (semantic.reason === "hybrid_disabled") return "语义灰度未开启";
  if (semantic.reason === "embedding_not_live") return "向量模型未启用";
  if (semantic.reason === "insufficient_vector_coverage") {
    const coverage = typeof semantic.coverage === "number" ? `向量覆盖 ${Math.round(semantic.coverage * 100)}%，未达到灰度门槛` : "向量覆盖不足";
    return coverage;
  }
  if (semantic.reason === "query_embedding_failed") return "查询向量生成失败，已回退至词法重排";
  return "";
}

function countValue(source: Record<string, number> | undefined, key: string) {
  const value = source?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function agentLabel(value: unknown) {
  const labels: Record<string, string> = {
    market_analyst: "市场分析师",
    bull_researcher: "多头研究员",
    bear_researcher: "空头研究员",
    researcher: "研究员",
    research_manager: "研究经理",
    risk_manager: "风险管理",
    portfolio_trader: "组合策略",
    committee: "投委会"
  };
  const raw = String(value ?? "").trim();
  return labels[raw] ?? (raw ? fieldLabel(raw) : "暂无");
}

function agentStageLabel(value: unknown) {
  const labels: Record<string, string> = {
    analyst: "市场分析",
    researcher: "研究验证",
    manager: "投委会汇总",
    guardrail: "约束校验"
  };
  const raw = String(value ?? "").trim();
  return labels[raw] ?? (raw ? fieldLabel(raw) : "暂无");
}

function runtimeStepLabel(value: unknown) {
  const labels: Record<string, string> = {
    run_daily_pipeline: "执行今日分析",
    run_promoted_advice_chain: "生成建议与审查",
    run_long_memory_analysis: "复盘长期记忆",
    sync_state: "同步组合状态",
    execution_sync_check: "检查模拟组合"
  };
  const raw = String(value ?? "").trim();
  return labels[raw] ?? (raw ? fieldLabel(raw) : "暂无");
}

function modelRunLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  if (["news_batch_classifier", "newsbatchclassifier"].includes(raw)) return "资讯批量分类";
  if (["rag_admin_search", "ragadminsearch"].includes(raw)) return "RAG 管理检索";
  return runtimeStepLabel(raw === "" ? "模型调用" : raw);
}

function modelProviderLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return "暂无";
  if (raw.toLowerCase() === "openai") return "OpenAI 兼容接口";
  return raw;
}

function reasoningLabel(value: unknown) {
  const labels: Record<string, string> = { none: "不启用", minimal: "极简", low: "低", medium: "中", high: "高", xhigh: "很高", max: "最高", ultra: "极高" };
  const raw = String(value ?? "").trim();
  return labels[raw] ?? (raw || "暂无");
}

function wireApiLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  if (raw === "responses") return "Responses API";
  if (raw === "chat_completions") return "Chat Completions API";
  return raw || "暂无";
}

function runtimeSourceLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  if (raw === "VITE_OKRA_API_BASE") return "桌面环境变量";
  if (raw === "default") return "本地默认配置";
  if (raw === "tauri-runtime") return "桌面运行时配置";
  return raw || "暂无";
}

function ragIntentLabel(value: unknown) {
  const labels: Record<string, string> = {
    general_chat: "通用问答",
    page_explain: "页面解读",
    fund_explain: "基金解读",
    decision_explain: "建议解读",
    risk_review: "风险复核",
    execution_review: "模拟执行复核",
    memory_review: "记忆复核",
    rag_admin_search: "RAG 管理检索",
    ragadminsearch: "RAG 管理检索"
  };
  const raw = String(value ?? "").trim();
  return labels[raw] ?? (raw ? fieldLabel(raw) : "通用问答");
}

function ragProfileLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return "默认检索配置";
  if (["rag_admin_search", "ragadminsearch"].includes(raw)) return "RAG 管理检索";
  return agentLabel(raw);
}

function runtimeStatusLabel(value: unknown) {
  return String(value ?? "").trim() ? runtimeStatusMeta(value).label : "暂无";
}

function sourceHealthLabel(value: unknown) {
  const raw = String(value ?? "").trim();
  const labels: Record<string, string> = {
    eastmoney_notice_and_articles: "东方财富公告与资讯",
    eastmoney_search_api: "东方财富检索",
    openai_web_search: "网页检索",
    xueqiu_web: "雪球资讯",
    douyin_web: "短视频资讯"
  };
  return labels[raw] || raw.replace(/^rss:/, "RSS / ").replace(/^reg:/, "监管 / ").replace(/_/g, " ") || "未知来源";
}
