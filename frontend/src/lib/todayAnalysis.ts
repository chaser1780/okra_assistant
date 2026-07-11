import type { Snapshot, SystemPayload, TodayAnalysisPayload, TodayAnalysisRuntimePayload, TodayAnalysisSystemPayload, Tone } from "./types";

export type RuntimeStatusKind = "idle" | "running" | "success" | "degraded" | "failed" | "stale" | "unknown";

export type RuntimeStatusMeta = {
  kind: RuntimeStatusKind;
  label: string;
  tone: Tone;
};

export function getTodayAnalysis(snapshot: Pick<Snapshot, "todayAnalysis" | "dailyFirstOpen">): TodayAnalysisPayload {
  return snapshot.todayAnalysis ?? snapshot.dailyFirstOpen;
}

export function getTodayAnalysisSystem(system?: SystemPayload): TodayAnalysisSystemPayload | undefined {
  return system?.todayAnalysis ?? system?.dailyFirstOpen;
}

export function hasTodayAnalysisResult(snapshot: Pick<Snapshot, "todayAnalysis" | "dailyFirstOpen">): boolean {
  const todayAnalysis = getTodayAnalysis(snapshot);
  const decision = todayAnalysis?.decision ?? {};
  const brief = String(todayAnalysis?.brief ?? "");
  return Object.keys(decision).length > 0 || brief.trim().length > 0;
}

export function getTodayAnalysisRuntime(system?: SystemPayload): TodayAnalysisRuntimePayload | undefined {
  return system?.todayAnalysisRuntime;
}

export function isTodayAnalysisRunComplete(runtime: TodayAnalysisRuntimePayload | undefined, runId: string): boolean {
  if (!runtime || !runId) return false;
  if (String(runtime.runId ?? "") !== runId) return false;
  const status = String(runtime.status ?? "").toLowerCase();
  if (!["ok", "degraded", "retryable_failure", "blocking_failure"].includes(status)) {
    return false;
  }
  if (status === "ok" || status === "degraded") {
    return Boolean(runtime.resultReady) && String(runtime.resultRunId ?? "") === runId;
  }
  return true;
}

export function runtimeStatusMeta(value: unknown): RuntimeStatusMeta {
  const status = String(value ?? "").trim().toLowerCase();
  if (["running", "in_progress", "started"].includes(status)) return { kind: "running", label: "运行中", tone: "accent" };
  if (["ok", "success", "completed", "complete", "ready"].includes(status)) return { kind: "success", label: "成功", tone: "success" };
  if (["degraded", "partial", "retryable_failure", "warning"].includes(status)) return { kind: "degraded", label: "降级", tone: "warning" };
  if (["failed", "failure", "error", "blocking_failure"].includes(status)) return { kind: "failed", label: "失败", tone: "danger" };
  if (["stale", "expired"].includes(status)) return { kind: "stale", label: "已过期", tone: "warning" };
  if (["idle", "pending", "not_run", "not_started"].includes(status)) return { kind: "idle", label: "未运行", tone: "neutral" };
  return { kind: "unknown", label: status || "未知", tone: "neutral" };
}

export function pickAnalysisValue(...values: unknown[]): unknown {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && !value.trim()) continue;
    return value;
  }
  return undefined;
}
