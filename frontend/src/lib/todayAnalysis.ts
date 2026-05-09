import type { Snapshot, SystemPayload, TodayAnalysisPayload, TodayAnalysisRuntimePayload, TodayAnalysisSystemPayload } from "./types";

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

export function pickAnalysisValue(...values: unknown[]): unknown {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && !value.trim()) continue;
    return value;
  }
  return undefined;
}
