import { text } from "./format";

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

export function extractPreviewRows(preview: Record<string, unknown> | null) {
  if (!preview) return [];
  const rows = asList(preview.matched_items).concat(asList(preview.new_items));
  if (rows.length) return rows;
  return asList(preview.detected_holdings).filter((row) => row.fund_code || row.matched_fund_code);
}

export function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

export function tradeTitle(item: Record<string, unknown>) {
  if (item.operation_type === "convert") {
    return `${text(item.out_fund_name ?? item.out_fund_code)} -> ${text(item.in_fund_name ?? item.in_fund_code)}`;
  }
  return text(item.fund_name ?? item.fund_code ?? item.trade_id, "真实操作");
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
    submitted: "待确认",
    confirmed: "已确认待到账",
    settled: "已完成",
    canceled: "已撤单",
    failed: "失败"
  };
  return map[String(value ?? "")] ?? "待确认";
}
