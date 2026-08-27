import { text } from "./format";
import type { ScreenshotPreview, ScreenshotPreviewRow } from "./types";

const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export function cleanPayload(source: Record<string, string>) {
  return Object.fromEntries(Object.entries(source).filter(([, value]) => value !== ""));
}

export function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function extractPreviewRows(preview: ScreenshotPreview | null): ScreenshotPreviewRow[] {
  if (!preview) return [];
  const rows = preview.matched_items.concat(preview.new_items);
  if (rows.length) return rows;
  return preview.detected_holdings.filter((row) => row.fund_code || row.matched_fund_code);
}

export function hasValidPreviewIntegrity(preview: ScreenshotPreview) {
  return SHA256_PATTERN.test(preview.preview_sha256) && SHA256_PATTERN.test(preview.portfolio_state_sha256);
}

export function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

export function tradeTitle(item: Record<string, unknown>) {
  if (item.operation_type === "convert") {
    return `${text(item.out_fund_name ?? item.out_fund_code)} -> ${text(item.in_fund_name ?? item.in_fund_code)}`;
  }
  return text(item.fund_name ?? item.fund_code ?? item.trade_id, "模拟操作");
}

export function operationText(value: unknown) {
  const map: Record<string, string> = {
    buy: "买入",
    sell: "卖出",
    convert: "转换",
    dca: "定投",
    dividend: "分红",
    fee: "费用",
    cancel: "撤单"
  };
  return map[String(value ?? "")] ?? "操作";
}

export function statusText(value: unknown) {
  const map: Record<string, string> = {
    planned: "计划中",
    simulated: "已记录模拟",
    submitted: "待确认",
    confirmed: "已确认待到账",
    settled: "已完成",
    cancelled: "已取消",
    canceled: "已取消",
    failed: "失败"
  };
  return map[String(value ?? "")] ?? "待确认";
}
