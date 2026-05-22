import { copilotResponseSchema } from "./schemas";
import type { ApiEnvelope, CopilotRequest, CopilotResponse, FundDetailPayload, MemoryAction, Snapshot } from "./types";

const API_BASE = import.meta.env.VITE_OKRA_API_BASE ?? "http://127.0.0.1:8765";

// Keep this module as the low-level HTTP boundary plus command-style mutations.
// Page queries should prefer workbenchApi/workbenchQuery so payload validation stays centralized.
type ErrorEnvelope = {
  error_code?: string;
  error_message?: string;
  error?: {
    error_code?: string;
    error_message?: string;
    details?: Record<string, unknown>;
  } | null;
  details?: Record<string, unknown>;
};

export class ApiError extends Error {
  status: number;
  details?: Record<string, unknown>;
  code?: string;

  constructor(status: number, message: string, details?: Record<string, unknown>, code?: string) {
    super(message);
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    try {
      const parsed = JSON.parse(text || "{}") as ErrorEnvelope;
      const nestedError = parsed.error ?? undefined;
      throw new ApiError(
        response.status,
        nestedError?.error_message || parsed.error_message || nestedError?.error_code || parsed.error_code || `request failed: ${response.status}`,
        nestedError?.details || parsed.details,
        nestedError?.error_code || parsed.error_code
      );
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(response.status, text || `request failed: ${response.status}`);
    }
  }
  const payload = (await response.json()) as T | ApiEnvelope<T>;
  if (isApiEnvelope(payload)) {
    if (!payload.ok) {
      const error = payload.error;
      throw new ApiError(
        response.status,
        error?.error_message || error?.error_code || `request failed: ${response.status}`,
        error?.details,
        error?.error_code
      );
    }
    return payload.data as T;
  }
  return payload as T;
}

function isApiEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  if (!value || typeof value !== "object") return false;
  return "ok" in value && "data" in value;
}

export function getSnapshot(date?: string): Promise<Snapshot> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<Snapshot>(`/api/snapshot${query}`);
}

export function getFundDetail(fundCode: string, date?: string, range = "since_inception"): Promise<FundDetailPayload> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (range) params.set("range", range);
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<FundDetailPayload>(`/api/fund/${encodeURIComponent(fundCode)}${query}`);
}

export function runTask(
  kind: "daily" | "realtime",
  options: { force?: boolean } = {}
): Promise<{ ok: boolean; pid: number; runId?: string; task: string; runDate: string; force?: boolean; logPath?: string }> {
  return request(`/api/run/${kind}`, { method: "POST", body: JSON.stringify(options) });
}

export function recordExecutionTrade(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/execution-sync/trade", { method: "POST", body: JSON.stringify(payload) });
}

export function recordExecutionConversion(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/execution-sync/conversion", { method: "POST", body: JSON.stringify(payload) });
}

export function parseAlipayScreenshots(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/execution-sync/alipay-screenshot/parse", { method: "POST", body: JSON.stringify(payload) });
}

export function applyExecutionReconcile(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/api/execution-sync/reconcile/apply", { method: "POST", body: JSON.stringify(payload) });
}

export function updateExecutionConfirmations(payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  return request("/api/execution-sync/confirmation/update", { method: "POST", body: JSON.stringify(payload) });
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

export async function askCopilot(payload: CopilotRequest, signal?: AbortSignal): Promise<CopilotResponse> {
  const result = await request<unknown>("/api/copilot/explain", {
    method: "POST",
    signal,
    body: JSON.stringify(payload)
  });
  return copilotResponseSchema.parse(result) as CopilotResponse;
}

export function openExternalUrl(url: string): Promise<{ ok: boolean; url: string; opened?: boolean }> {
  return request("/api/open-url", {
    method: "POST",
    body: JSON.stringify({ url })
  });
}
