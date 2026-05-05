import type { CopilotRequest, FundDetailPayload, MemoryAction, Snapshot } from "./types";

const API_BASE = import.meta.env.VITE_OKRA_API_BASE ?? "http://127.0.0.1:8765";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getSnapshot(date?: string): Promise<Snapshot> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<Snapshot>(`/api/snapshot${query}`);
}

export function getFundDetail(fundCode: string, date?: string, range = "成立以来"): Promise<FundDetailPayload> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (range) params.set("range", range);
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<FundDetailPayload>(`/api/fund/${encodeURIComponent(fundCode)}${query}`);
}

export function runTask(kind: "daily" | "realtime", options: { force?: boolean } = {}): Promise<{ ok: boolean; pid: number; task: string; runDate: string; force?: boolean }> {
  return request(`/api/run/${kind}`, { method: "POST", body: JSON.stringify(options) });
}

export function runLongMemoryAction(
  memoryId: string,
  action: MemoryAction,
  note = ""
): Promise<{ ok: boolean; record: Record<string, unknown> }> {
  return request("/api/long-memory/action", {
    method: "POST",
    body: JSON.stringify({ memoryId, action, note })
  });
}

export function askCopilot(payload: CopilotRequest): Promise<{ answer: string; mode?: string; sourceDate?: string }> {
  return request("/api/copilot/explain", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
