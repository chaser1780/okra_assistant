export function text(value: unknown, fallback = "暂无"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["label", "summary", "status", "state", "message", "text", "name", "title"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    }
    return fallback;
  }
  return String(value);
}

export function lines(value: string | string[] | undefined, fallback = "暂无内容"): string[] {
  if (Array.isArray(value)) return value.filter(Boolean);
  const raw = value || "";
  const parsed = raw
    .split(/\r?\n/)
    .map((item) => item.replace(/^\s*[-*]\s*/, "").trim())
    .filter(Boolean);
  return parsed.length ? parsed : [fallback];
}

export function asNumber(value: unknown): number {
  return asNullableNumber(value) ?? 0;
}

export function asNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function compactMoney(value: unknown): string {
  const parsed = asNullableNumber(value);
  if (parsed === null) return "不可用";
  if (Math.abs(parsed) >= 10000) return `${(parsed / 10000).toFixed(2)}万`;
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function signedPct(value: unknown): string {
  const parsed = asNullableNumber(value);
  if (parsed === null) return "不可用";
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(2)}%`;
}

export function signedMoney(value: unknown): string {
  const parsed = asNullableNumber(value);
  if (parsed === null) return "不可用";
  return `${parsed > 0 ? "+" : ""}${parsed.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}
