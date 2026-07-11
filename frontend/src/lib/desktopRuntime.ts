import { invoke } from "@tauri-apps/api/core";

export type DesktopMode = "local" | "remote";

export type DesktopRuntimeConfig = {
  mode: DesktopMode;
  apiBase: string;
  diagnosticApiBase: string;
  configured: boolean;
  source: string;
  error?: string;
};

const LOCAL_API_BASE = "http://127.0.0.1:8765";

function normalizedBase(value: unknown) {
  return String(value ?? "").trim().replace(/\/+$/, "");
}

function buildMode(): DesktopMode {
  const configured = String(import.meta.env.VITE_OKRA_DESKTOP_MODE ?? "").trim().toLowerCase();
  if (configured === "remote") return "remote";
  if (configured === "local") return "local";
  const apiBase = normalizedBase(import.meta.env.VITE_OKRA_API_BASE);
  return apiBase && !/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(apiBase) ? "remote" : "local";
}

export function sanitizeApiBase(value: unknown) {
  const raw = normalizedBase(value);
  if (!raw) return "未配置";
  try {
    const parsed = new URL(raw);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    return raw.split(/[?#]/, 1)[0] || "未配置";
  }
}

export function buildDesktopRuntimeConfig(): DesktopRuntimeConfig {
  const mode = buildMode();
  const configuredBase = normalizedBase(import.meta.env.VITE_OKRA_API_BASE);
  const apiBase = configuredBase || (mode === "local" ? LOCAL_API_BASE : "");
  return {
    mode,
    apiBase,
    diagnosticApiBase: sanitizeApiBase(apiBase),
    configured: mode === "local" || Boolean(apiBase),
    source: configuredBase ? "VITE_OKRA_API_BASE" : "default",
  };
}

let runtimeConfigPromise: Promise<DesktopRuntimeConfig> | null = null;

export function getDesktopRuntimeConfig(): Promise<DesktopRuntimeConfig> {
  if (!runtimeConfigPromise) {
    runtimeConfigPromise = invoke<DesktopRuntimeConfig>("desktop_runtime_config")
      .then((runtime) => {
        const mode: DesktopMode = runtime.mode === "remote" ? "remote" : "local";
        const apiBase = normalizedBase(runtime.apiBase);
        return {
          mode,
          apiBase,
          diagnosticApiBase: sanitizeApiBase(runtime.diagnosticApiBase || apiBase),
          configured: mode === "local" || Boolean(apiBase && runtime.configured),
          source: String(runtime.source || "tauri-runtime"),
        };
      })
      .catch((error) => ({
        ...buildDesktopRuntimeConfig(),
        error: error instanceof Error ? error.message : String(error || "Tauri runtime unavailable"),
      }));
  }
  return runtimeConfigPromise;
}
