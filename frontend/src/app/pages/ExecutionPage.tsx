import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  applyExecutionReconcile,
  parseAlipayScreenshots,
  recordExecutionConversion,
  recordExecutionTrade,
  updateExecutionConfirmations
} from "../../lib/api";
import type { ExecutionSyncPayload, PortfolioItem, PortfolioPayload } from "../../lib/types";
import { asNumber, signedMoney, text } from "../../lib/format";
import { Badge, Button, Card, SectionTitle } from "../../components/ui";

type Props = {
  executionSync: ExecutionSyncPayload;
  portfolio: PortfolioPayload;
  onRefresh: () => void;
};

type TradeKind = "buy" | "sell" | "convert";
type ScreenshotMode = "update" | "replace";
type TradeFormValue = {
  trade_date: string;
  trade_time: string;
  fund_code: string;
  fund_name: string;
  amount: string;
  units: string;
  nav: string;
  fee: string;
  confirm_date: string;
  settlement_date: string;
  linked_suggestion_id: string;
  user_note: string;
};
type ConversionFormValue = {
  trade_date: string;
  trade_time: string;
  out_fund_code: string;
  out_fund_name: string;
  in_fund_code: string;
  in_fund_name: string;
  out_amount: string;
  out_units: string;
  out_nav: string;
  in_amount: string;
  in_units: string;
  in_nav: string;
  fee: string;
  out_confirm_date: string;
  in_confirm_date: string;
  user_note: string;
};

const tradeLabels: Record<TradeKind, string> = {
  buy: "买入",
  sell: "卖出",
  convert: "转换"
};

export function ExecutionPage({ executionSync, portfolio, onRefresh }: Props) {
  const today = new Date().toLocaleDateString("sv-SE");
  const firstFund = portfolio.items[0];
  const secondFund = portfolio.items[1] ?? firstFund;
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tradeKind, setTradeKind] = useState<TradeKind>("buy");
  const [screenshotPreview, setScreenshotPreview] = useState<Record<string, unknown> | null>(null);
  const [trade, setTrade] = useState<TradeFormValue>({
    trade_date: today,
    trade_time: "14:50",
    fund_code: firstFund?.fundCode ?? "",
    fund_name: firstFund?.fundName ?? "",
    amount: "",
    units: "",
    nav: "",
    fee: "",
    confirm_date: "",
    settlement_date: "",
    linked_suggestion_id: "",
    user_note: ""
  });
  const [conversion, setConversion] = useState<ConversionFormValue>({
    trade_date: today,
    trade_time: "14:50",
    out_fund_code: firstFund?.fundCode ?? "",
    out_fund_name: firstFund?.fundName ?? "",
    in_fund_code: secondFund?.fundCode ?? "",
    in_fund_name: secondFund?.fundName ?? "",
    out_amount: "",
    out_units: "",
    out_nav: "",
    in_amount: "",
    in_units: "",
    in_nav: "",
    fee: "",
    out_confirm_date: "",
    in_confirm_date: "",
    user_note: ""
  });
  const recognizedRows = useMemo(() => extractPreviewRows(screenshotPreview), [screenshotPreview]);

  async function submitTrade() {
    setBusy(true);
    setMessage(`正在记录${tradeLabels[tradeKind]}...`);
    try {
      if (tradeKind === "convert") {
        await recordExecutionConversion(cleanPayload({ ...conversion, source: "manual", platform: "alipay" }));
        setMessage("转换已记录为一组真实转换单；确认日到期后会自动落入真实仓位。");
      } else {
        await recordExecutionTrade(cleanPayload({ ...trade, operation_type: tradeKind, source: "manual", platform: "alipay" }));
        setMessage(`${tradeLabels[tradeKind]}已记录；未确认前进入待确认列表，到期后自动更新真实仓位。`);
      }
      onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setMessage("正在识别支付宝持仓截图...");
    try {
      const encoded = await Promise.all(
        Array.from(files).map(async (file) => ({
          name: file.name,
          data: await fileToDataUrl(file)
        }))
      );
      const result = await parseAlipayScreenshots({ snapshot_date: today, files: encoded });
      setScreenshotPreview(result);
      setMessage("截图已识别，请核对识别结果，然后选择“更新”或“全部替换”。");
    } finally {
      setBusy(false);
    }
  }

  async function applyScreenshot(mode: ScreenshotMode) {
    if (!screenshotPreview) return;
    setBusy(true);
    setMessage(mode === "replace" ? "正在按截图全部替换真实仓位..." : "正在按截图更新真实仓位...");
    try {
      await applyExecutionReconcile({ preview: screenshotPreview, dropMissing: mode === "replace" });
      setScreenshotPreview(null);
      setMessage(mode === "replace" ? "真实仓位已完全按截图替换。" : "真实仓位已按截图更新，未出现在截图中的持仓已保留。");
      onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function refreshConfirmations() {
    setBusy(true);
    try {
      const result = await updateExecutionConfirmations({ date: today });
      setMessage(`待确认状态已刷新，落入真实仓位 ${text(result.portfolio_applied_count, "0")} 笔。`);
      onRefresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-4 gap-4">
        <Metric title="待确认" value={executionSync.counts.pending ?? 0} body="未确认份额、未到账赎回或转换未完成" />
        <Metric title="真实操作" value={executionSync.counts.trades ?? 0} body="已写入本地真实执行账本" />
        <Metric title="执行偏差" value={executionSync.counts.deviations ?? 0} body="只用于执行纪律，不影响策略胜率" />
        <Metric title="同步报告" value={executionSync.counts.reports ?? 0} body="截图或快照更新真实仓位后的记录" />
      </section>

      {message ? <div className="rounded-md border border-cyan-500/30 bg-cyan-950/25 px-4 py-3 text-sm text-cyan-100">{message}</div> : null}

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-7 p-4">
          <SectionTitle title="交易记录" meta="手动录入后直接写入真实执行账本" />
          <div className="mb-4 inline-flex rounded-md border border-slate-800 bg-slate-950 p-1">
            {(["buy", "sell", "convert"] as TradeKind[]).map((kind) => (
              <button
                key={kind}
                className={`h-9 rounded px-4 text-sm font-semibold transition ${
                  tradeKind === kind ? "bg-cyan-500/20 text-cyan-100" : "text-slate-400 hover:text-slate-100"
                }`}
                onClick={() => setTradeKind(kind)}
              >
                {tradeLabels[kind]}
              </button>
            ))}
          </div>
          {tradeKind === "convert" ? (
            <ConversionForm conversion={conversion} setConversion={setConversion} portfolio={portfolio} />
          ) : (
            <BuySellForm trade={trade} setTrade={setTrade} portfolio={portfolio} kind={tradeKind} />
          )}
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-xs leading-5 text-slate-500">
              15:00 后或非交易日会顺延；买入确认前不增加份额，卖出确认前只进入待确认，到账后更新现金仓。
            </p>
            <Button variant="primary" disabled={busy} onClick={() => void submitTrade()}>
              记录{tradeLabels[tradeKind]}
            </Button>
          </div>
        </Card>

        <Card className="col-span-5 p-4">
          <SectionTitle title="支付宝截图上传" meta="识别后确认更新真实仓位" />
          <input
            type="file"
            multiple
            accept="image/*"
            className="block w-full rounded-md border border-slate-800 bg-slate-950 p-3 text-sm text-slate-300"
            onChange={(event) => void handleFiles(event.target.files)}
          />
          <p className="mt-3 text-sm leading-6 text-slate-500">
            截图识别只生成待确认结果。确认后，“更新”会保留截图未提到的持仓，“全部替换”会把未出现在截图中的持仓归零。
          </p>
          {screenshotPreview ? (
            <div className="mt-4 space-y-3">
              <PreviewSummary preview={screenshotPreview} rows={recognizedRows} />
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" disabled={busy || !recognizedRows.length} onClick={() => void applyScreenshot("update")}>
                  更新
                </Button>
                <Button variant="danger" disabled={busy || !recognizedRows.length} onClick={() => void applyScreenshot("replace")}>
                  全部替换
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => setScreenshotPreview(null)}>
                  取消
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-6 p-4">
          <SectionTitle title="待确认交易" meta="到确认日/到账日后可刷新落仓" />
          <Button className="mb-3" variant="secondary" disabled={busy} onClick={() => void refreshConfirmations()}>
            刷新确认状态
          </Button>
          <TradeList items={executionSync.pending} empty="暂无待确认交易" />
        </Card>
        <Card className="col-span-6 p-4">
          <SectionTitle title="最近真实操作" meta="本地账本记录" />
          <TradeList items={executionSync.trades} empty="暂无真实操作记录" />
        </Card>
      </section>
    </div>
  );
}

function BuySellForm({
  trade,
  setTrade,
  portfolio,
  kind
}: {
  trade: TradeFormValue;
  setTrade: Dispatch<SetStateAction<TradeFormValue>>;
  portfolio: PortfolioPayload;
  kind: "buy" | "sell";
}) {
  return (
    <div className="grid grid-cols-2 gap-3 text-sm">
      <Field label="交易日期">
        <input className={inputClass} type="date" value={trade.trade_date} onChange={(e) => setTrade({ ...trade, trade_date: e.target.value })} />
      </Field>
      <Field label="交易时间">
        <input className={inputClass} type="time" value={trade.trade_time} onChange={(e) => setTrade({ ...trade, trade_time: e.target.value })} />
      </Field>
      <FundSelect label="基金" value={trade.fund_code} portfolio={portfolio} onChange={(fund) => setTrade({ ...trade, fund_code: fund.fundCode, fund_name: fund.fundName })} />
      <Field label={kind === "buy" ? "买入金额" : "卖出金额"}>
        <input className={inputClass} inputMode="decimal" value={trade.amount} onChange={(e) => setTrade({ ...trade, amount: e.target.value })} />
      </Field>
      <Field label="份额">
        <input className={inputClass} inputMode="decimal" value={trade.units} onChange={(e) => setTrade({ ...trade, units: e.target.value })} />
      </Field>
      <Field label="净值">
        <input className={inputClass} inputMode="decimal" value={trade.nav} onChange={(e) => setTrade({ ...trade, nav: e.target.value })} />
      </Field>
      <Field label="费用">
        <input className={inputClass} inputMode="decimal" value={trade.fee} onChange={(e) => setTrade({ ...trade, fee: e.target.value })} />
      </Field>
      <Field label="确认日">
        <input className={inputClass} type="date" value={trade.confirm_date} onChange={(e) => setTrade({ ...trade, confirm_date: e.target.value })} />
      </Field>
      {kind === "sell" ? (
        <Field label="到账日">
          <input className={inputClass} type="date" value={trade.settlement_date} onChange={(e) => setTrade({ ...trade, settlement_date: e.target.value })} />
        </Field>
      ) : null}
      <Field label="关联系统建议">
        <input className={inputClass} value={trade.linked_suggestion_id} onChange={(e) => setTrade({ ...trade, linked_suggestion_id: e.target.value })} />
      </Field>
      <Field label="备注">
        <input className={inputClass} value={trade.user_note} onChange={(e) => setTrade({ ...trade, user_note: e.target.value })} />
      </Field>
    </div>
  );
}

function ConversionForm({
  conversion,
  setConversion,
  portfolio
}: {
  conversion: ConversionFormValue;
  setConversion: Dispatch<SetStateAction<ConversionFormValue>>;
  portfolio: PortfolioPayload;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 text-sm">
      <Field label="交易日期">
        <input className={inputClass} type="date" value={conversion.trade_date} onChange={(e) => setConversion({ ...conversion, trade_date: e.target.value })} />
      </Field>
      <Field label="交易时间">
        <input className={inputClass} type="time" value={conversion.trade_time} onChange={(e) => setConversion({ ...conversion, trade_time: e.target.value })} />
      </Field>
      <FundSelect label="转出基金" value={conversion.out_fund_code} portfolio={portfolio} onChange={(fund) => setConversion({ ...conversion, out_fund_code: fund.fundCode, out_fund_name: fund.fundName })} />
      <FundSelect label="转入基金" value={conversion.in_fund_code} portfolio={portfolio} onChange={(fund) => setConversion({ ...conversion, in_fund_code: fund.fundCode, in_fund_name: fund.fundName })} />
      <Field label="转出金额">
        <input className={inputClass} inputMode="decimal" value={conversion.out_amount} onChange={(e) => setConversion({ ...conversion, out_amount: e.target.value })} />
      </Field>
      <Field label="转出份额">
        <input className={inputClass} inputMode="decimal" value={conversion.out_units} onChange={(e) => setConversion({ ...conversion, out_units: e.target.value })} />
      </Field>
      <Field label="转入金额">
        <input className={inputClass} inputMode="decimal" value={conversion.in_amount} onChange={(e) => setConversion({ ...conversion, in_amount: e.target.value })} />
      </Field>
      <Field label="转入份额">
        <input className={inputClass} inputMode="decimal" value={conversion.in_units} onChange={(e) => setConversion({ ...conversion, in_units: e.target.value })} />
      </Field>
      <Field label="转出确认日">
        <input className={inputClass} type="date" value={conversion.out_confirm_date} onChange={(e) => setConversion({ ...conversion, out_confirm_date: e.target.value })} />
      </Field>
      <Field label="转入确认日">
        <input className={inputClass} type="date" value={conversion.in_confirm_date} onChange={(e) => setConversion({ ...conversion, in_confirm_date: e.target.value })} />
      </Field>
      <Field label="费用">
        <input className={inputClass} inputMode="decimal" value={conversion.fee} onChange={(e) => setConversion({ ...conversion, fee: e.target.value })} />
      </Field>
      <Field label="备注">
        <input className={inputClass} value={conversion.user_note} onChange={(e) => setConversion({ ...conversion, user_note: e.target.value })} />
      </Field>
    </div>
  );
}

function PreviewSummary({ preview, rows }: { preview: Record<string, unknown>; rows: Record<string, unknown>[] }) {
  const warnings = [...asList(preview.warnings), ...asList(preview.vision_warnings)];
  const missing = asList(preview.missing_items).length || asList(preview.missing_portfolio_funds).length;
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-100">识别到 {rows.length} 只基金</span>
        <Badge tone={rows.length ? "success" : "warning"}>{rows.length ? "可确认" : "未识别"}</Badge>
      </div>
      <div className="max-h-64 space-y-2 overflow-auto">
        {rows.map((row, index) => (
          <div key={`${text(row.fund_code ?? row.matched_fund_code, String(index))}-${index}`} className="rounded border border-slate-800 bg-slate-900/50 px-3 py-2">
            <div className="font-semibold text-slate-200">{text(row.fund_code ?? row.matched_fund_code)} {text(row.fund_name ?? row.matched_fund_name ?? row.display_name)}</div>
            <div className="mt-1 text-xs text-slate-500">
              当前市值 {signedMoney(asNumber(row.current_value))} | 持仓收益 {signedMoney(asNumber(row.holding_pnl))}
            </div>
          </div>
        ))}
      </div>
      {missing ? <div className="mt-3 text-xs text-amber-200">有 {missing} 只当前持仓未出现在截图中；选择“全部替换”时会归零。</div> : null}
      {warnings.map((item, index) => (
        <div key={index} className="mt-2 text-xs leading-5 text-slate-500">
          {text(item)}
        </div>
      ))}
    </div>
  );
}

function TradeList({ items, empty }: { items: Record<string, unknown>[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <div className="space-y-2">
      {items.slice(0, 12).map((item, index) => (
        <div key={String(item.trade_id ?? item.conversion_id ?? index)} className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-400">
          <div className="flex items-center justify-between gap-3">
            <div className="font-semibold text-slate-200">{tradeTitle(item)}</div>
            <Badge tone={item.status === "settled" ? "success" : item.status === "confirmed" ? "accent" : "warning"}>{statusText(item.status)}</Badge>
          </div>
          <div>
            {operationText(item.operation_type)} | {text(item.trade_date)} | {signedMoney(asNumber(item.amount ?? item.out_amount))}
          </div>
          <div className="text-xs text-slate-500">
            确认日 {text(item.confirm_date ?? item.in_confirm_date ?? item.out_confirm_date)} | 到账日 {text(item.settlement_date ?? item.in_confirm_date)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({ title, value, body }: { title: string; value: number; body: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-bold text-slate-500">{title}</div>
      <div className="metric-number mt-2 text-2xl font-black text-slate-50">{value}</div>
      <p className="mt-2 text-sm leading-6 text-slate-400">{body}</p>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="space-y-1">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      {children}
    </label>
  );
}

function FundSelect({
  label,
  value,
  portfolio,
  onChange
}: {
  label: string;
  value: string;
  portfolio: PortfolioPayload;
  onChange: (fund: PortfolioItem) => void;
}) {
  return (
    <Field label={label}>
      <select className={inputClass} value={value} onChange={(e) => onChange(portfolio.items.find((item) => item.fundCode === e.target.value) ?? portfolio.items[0])}>
        {portfolio.items.map((item) => (
          <option key={item.fundCode} value={item.fundCode}>
            {item.fundCode} {item.fundName}
          </option>
        ))}
      </select>
    </Field>
  );
}

const inputClass = "h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100 outline-none transition focus:border-cyan-500/70";

function cleanPayload(source: Record<string, string>) {
  return Object.fromEntries(Object.entries(source).filter(([, value]) => value !== ""));
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function extractPreviewRows(preview: Record<string, unknown> | null) {
  if (!preview) return [];
  const rows = asList(preview.matched_items).concat(asList(preview.new_items));
  if (rows.length) return rows;
  return asList(preview.detected_holdings).filter((row) => row.fund_code || row.matched_fund_code);
}

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

function tradeTitle(item: Record<string, unknown>) {
  if (item.operation_type === "convert") {
    return `${text(item.out_fund_name ?? item.out_fund_code)} -> ${text(item.in_fund_name ?? item.in_fund_code)}`;
  }
  return text(item.fund_name ?? item.fund_code ?? item.trade_id, "真实操作");
}

function operationText(value: unknown) {
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

function statusText(value: unknown) {
  const map: Record<string, string> = {
    submitted: "待确认",
    confirmed: "已确认待到账",
    settled: "已完成",
    canceled: "已撤单",
    failed: "失败"
  };
  return map[String(value ?? "")] ?? "待确认";
}
