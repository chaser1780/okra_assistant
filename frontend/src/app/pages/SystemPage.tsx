import { fieldLabel, valueLabel } from "../../lib/display";
import { Badge, Card, SectionTitle } from "../../components/ui";

export function SystemPage({ system, summary }: { system: Record<string, unknown>; summary: Record<string, unknown> }) {
  const llmRuntime = (system.llmRuntime ?? {}) as Record<string, unknown>;
  const todayRuntime = (system.todayAnalysisRuntime ?? {}) as Record<string, unknown>;
  const longMemoryRuntime = (system.longMemoryRuntime ?? {}) as Record<string, unknown>;
  const agentRuntime = (system.agentRuntime ?? {}) as Record<string, unknown>;
  const failedAgents = Array.isArray(agentRuntime.failedAgents) ? agentRuntime.failedAgents : [];
  const degradedAgents = Array.isArray(agentRuntime.degradedAgents) ? agentRuntime.degradedAgents : [];

  return (
    <div className="grid grid-cols-2 gap-4">
      <Card className="col-span-2 p-4">
        <SectionTitle title="模型与主链路状态" />
        <div className="grid grid-cols-5 gap-3">
          <StatusTile label="主模型" value={String(llmRuntime.model ?? "暂无")} tone="accent" />
          <StatusTile label="评审模型" value={String(llmRuntime.reviewModel ?? "暂无")} tone="info" />
          <StatusTile label="今日分析状态" value={String(todayRuntime.status ?? "暂无")} tone={tileTone(todayRuntime.status)} />
          <StatusTile label="当前 Agent" value={String(todayRuntime.currentAgent ?? "暂无")} tone="success" />
          <StatusTile label="长期记忆状态" value={String(longMemoryRuntime.status ?? "暂无")} tone={tileTone(longMemoryRuntime.status)} />
        </div>
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
                <div className="font-semibold">{String((item as Record<string, unknown>).agent_name ?? "unknown")}</div>
                <div className="mt-1 text-xs text-slate-500">{String((item as Record<string, unknown>).error ?? "")}</div>
              </div>
            ))}
            {degradedAgents.map((item, index) => (
              <div key={`degraded-${index}`} className="rounded-md border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                <div className="font-semibold">{String(item)}</div>
                <div className="mt-1 text-xs text-slate-500">degraded</div>
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
          <div>provider: {String(llmRuntime.modelProvider ?? "暂无")}</div>
          <div>model: {String(llmRuntime.model ?? "暂无")}</div>
          <div>review: {String(llmRuntime.reviewModel ?? "暂无")}</div>
          <div>reasoning: {String(llmRuntime.reasoningEffort ?? "暂无")}</div>
          <div>wire_api: {String(llmRuntime.wireApi ?? "暂无")}</div>
          <div>base_url: {String(llmRuntime.baseUrl ?? "暂无")}</div>
        </div>
      </Card>

      <Card className="p-4">
        <SectionTitle title="系统摘要" />
        <KeyValueTree value={summary} />
      </Card>

      <Card className="p-4">
        <SectionTitle title="原始系统信息" />
        <KeyValueTree value={system} />
      </Card>
    </div>
  );
}

function StatusTile({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger" | "info";
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="break-all text-sm font-semibold text-slate-200">{value}</div>
        <Badge tone={tone}>{tone === "danger" ? "异常" : tone === "success" ? "运行中/正常" : "信息"}</Badge>
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
      <div>status: {String(payload.status ?? "暂无")}</div>
      <div>phase: {String(payload.phase ?? "暂无")}</div>
      <div>run_id: {String(payload.runId ?? "暂无")}</div>
      <div>report_date: {String(payload.reportDate ?? "暂无")}</div>
      <div>started_at: {String(payload.startedAt ?? "暂无")}</div>
      <div>elapsed_seconds: {String(payload.elapsedSeconds ?? 0)}</div>
      <div>current_step: {String(payload.currentStep ?? "暂无")}</div>
      <div>current_agent: {String(payload.currentAgent ?? "暂无")}</div>
      <div>current_agent_stage: {String(payload.currentAgentStage ?? "暂无")}</div>
      <div>running_agents: {runningAgents.length ? runningAgents.map((item) => String(item)).join(" / ") : "暂无"}</div>
      <div>failed_agents: {failedAgents.length}</div>
      <div>degraded_agents: {degradedAgents.length}</div>
      <div>last_error: {String(payload.lastError ?? "暂无")}</div>
      {"analysisQuality" in payload ? <div>analysis_quality: {String(payload.analysisQuality ?? "暂无")}</div> : null}
      {"memoryEligible" in payload ? <div>memory_eligible: {String(payload.memoryEligible ?? "暂无")}</div> : null}
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

function tileTone(status: unknown) {
  const text = String(status ?? "").toLowerCase();
  if (text === "failed") return "danger" as const;
  if (text === "running" || text === "ok") return "success" as const;
  return "info" as const;
}
