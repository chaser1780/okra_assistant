import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { AlertTriangle, Check, ExternalLink, Loader2, RefreshCw, Search } from "lucide-react";
import {
  applyExecutionReconcile,
  lookupExecutionFund,
  parseAlipayScreenshots,
  recordExecutionConversion,
  recordExecutionTrade,
  registerExecutionFund,
  updateExecutionConfirmations
} from "../../lib/api";
import type {
  ExecutionSyncPayload,
  FundLookupCandidate,
  PortfolioItem,
  PortfolioPayload,
  ScreenshotPreview,
  ScreenshotPreviewRow,
  UnmatchedHolding
} from "../../lib/types";
import { signedMoney, text } from "../../lib/format";
import { cleanPayload, extractPreviewRows, fileToDataUrl, hasValidPreviewIntegrity, operationText, statusText, tradeTitle } from "../../lib/executionSync";
import { Badge, Button, Card, SectionTitle } from "../../components/ui";
import { TerminalPanel, TerminalState } from "../../components/okra/TerminalChrome";
import { SimulationTrackRail } from "../../components/okra/ResearchContext";

type Props = {
  executionSync: ExecutionSyncPayload;
  portfolio: PortfolioPayload;
  onRefresh: () => void;
};

type TradeKind = "buy" | "sell" | "convert";
type ScreenshotMode = "update" | "replace";
type FundLookupState = {
  status: "loading" | "ready" | "error";
  candidates: FundLookupCandidate[];
  warnings: string[];
  error: string;
};
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
  convert: "换基"
};

function positiveInput(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error || "Request failed");
}

function unmatchedHoldingKey(item: UnmatchedHolding) {
  return `${item.display_name}::${item.page_index ?? "page"}::${item.row_index ?? "row"}`;
}

function previewBlockers(preview: ScreenshotPreview, rows: ScreenshotPreviewRow[]) {
  const blockers: string[] = [];
  if (preview.unmatched_detected.length) blockers.push(`还有 ${preview.unmatched_detected.length} 只截图持仓未匹配基金。`);
  if (!rows.length) blockers.push("没有可写入的已识别持仓。");
  if (!/^[0-9a-f]{64}$/.test(preview.preview_sha256)) blockers.push("预览完整性哈希缺失或格式无效，请重新解析截图。");
  if (!/^[0-9a-f]{64}$/.test(preview.portfolio_state_sha256)) blockers.push("组合状态哈希缺失或格式无效，请重新解析截图。");
  if (preview.apply_ready !== true) blockers.push("后端尚未将本次预览标记为可应用。");
  return blockers;
}

export function ExecutionPage({ executionSync, portfolio, onRefresh }: Props) {
  const today = new Date().toLocaleDateString("sv-SE");
  const firstFund = portfolio.items[0];
  const secondFund = portfolio.items[1] ?? firstFund;
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tradeKind, setTradeKind] = useState<TradeKind>("buy");
  const [screenshotPreview, setScreenshotPreview] = useState<ScreenshotPreview | null>(null);
  const [replaceConfirm, setReplaceConfirm] = useState("");
  const [fundLookups, setFundLookups] = useState<Record<string, FundLookupState>>({});
  const [registeringKey, setRegisteringKey] = useState("");
  const lookupInFlight = useRef(new Set<string>());
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
  const screenshotBlockers = useMemo(
    () => (screenshotPreview ? previewBlockers(screenshotPreview, recognizedRows) : []),
    [recognizedRows, screenshotPreview]
  );
  const screenshotApplyReady = screenshotPreview
    ? screenshotPreview.apply_ready === true
      && recognizedRows.length > 0
      && screenshotPreview.unmatched_detected.length === 0
      && hasValidPreviewIntegrity(screenshotPreview)
    : false;

  const loadFundCandidates = useCallback(async (holding: UnmatchedHolding, key: string) => {
    if (lookupInFlight.current.has(key)) return;
    lookupInFlight.current.add(key);
    setFundLookups((current) => ({
      ...current,
      [key]: { status: "loading", candidates: current[key]?.candidates ?? [], warnings: [], error: "" }
    }));
    try {
      const result = await lookupExecutionFund(holding.display_name);
      setFundLookups((current) => ({
        ...current,
        [key]: { status: "ready", candidates: result.candidates, warnings: result.warnings, error: "" }
      }));
    } catch (error) {
      setFundLookups((current) => ({
        ...current,
        [key]: { status: "error", candidates: [], warnings: [], error: errorMessage(error) }
      }));
    } finally {
      lookupInFlight.current.delete(key);
    }
  }, []);

  useEffect(() => {
    if (!screenshotPreview) return;
    screenshotPreview.unmatched_detected.forEach((holding) => {
      const key = unmatchedHoldingKey(holding);
      if (!fundLookups[key]) void loadFundCandidates(holding, key);
    });
  }, [fundLookups, loadFundCandidates, screenshotPreview]);

  async function submitTrade() {
    if (tradeKind === "convert") {
      if (!conversion.out_fund_code || !conversion.in_fund_code) {
        setMessage("请选择转出和转入基金。");
        return;
      }
      if (conversion.out_fund_code === conversion.in_fund_code) {
        setMessage("转出基金和转入基金不能相同。");
        return;
      }
      if (!positiveInput(conversion.out_amount) && !positiveInput(conversion.out_units)) {
        setMessage("转换需要填写大于 0 的转出金额或转出份额。");
        return;
      }
    } else {
      if (!trade.fund_code) {
        setMessage("请选择基金后再记录交易。");
        return;
      }
      if (!positiveInput(trade.amount) && !positiveInput(trade.units)) {
        setMessage("交易需要填写大于 0 的金额或份额。");
        return;
      }
    }
    setBusy(true);
    setMessage(`正在记录${tradeLabels[tradeKind]}模拟操作...`);
    try {
      if (tradeKind === "convert") {
        await recordExecutionConversion(cleanPayload({ ...conversion, source: "user_simulation", platform: "local_simulation", simulation_track: "user_simulation", simulation_status: "simulated" }));
        setMessage("转换已记录到用户模拟轨道。组合仓位仍以你确认同步的组合快照为准。");
      } else {
        await recordExecutionTrade(cleanPayload({ ...trade, operation_type: tradeKind, source: "user_simulation", platform: "local_simulation", simulation_track: "user_simulation", simulation_status: "simulated" }));
        setMessage(`${tradeLabels[tradeKind]}已记录到用户模拟轨道；不会自动改写当前组合仓位。`);
      }
      onRefresh();
    } catch (error) {
      setMessage(`操作失败：${errorMessage(error)}`);
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
      setReplaceConfirm("");
      setFundLookups({});
      const rows = extractPreviewRows(result);
      if (result.auto_parse_attempted && !result.auto_parse_ok) {
        setMessage(`截图已保存，但自动识别失败：${result.auto_parse_error || "LLM 视觉接口未返回可用结果"}`);
      } else if (result.unmatched_detected.length) {
        setMessage(`截图已识别到 ${rows.length} 只基金，另有 ${result.unmatched_detected.length} 只未匹配持仓，正在查询官方基金候选。`);
      } else if (rows.length) {
        setMessage(hasValidPreviewIntegrity(result) && result.apply_ready === true
          ? "截图已识别并通过完整性检查，请核对后选择“更新”或“全部替换”。"
          : "截图已识别，但缺少应用所需的完整性信息，请查看阻断原因并重新解析。"
        );
      } else {
        setMessage("截图已保存，但没有识别到可同步的持仓。");
      }
    } catch (error) {
      setMessage(`截图识别失败：${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function confirmFundRegistration(holding: UnmatchedHolding, candidate: FundLookupCandidate, key: string) {
    if (!screenshotPreview) return;
    if (!screenshotPreview.reconcile_id || !/^[0-9a-f]{64}$/.test(screenshotPreview.preview_sha256)) {
      setMessage("当前预览缺少有效的预览哈希，不能安全添加基金；请重新解析截图。");
      return;
    }
    if (!hasValidPreviewIntegrity(screenshotPreview)) {
      setMessage("当前预览缺少有效的完整性哈希，不能安全添加基金；请重新解析截图。");
      return;
    }
    if (!/^\d{6}$/.test(candidate.fund_code)) {
      setMessage("候选基金代码格式无效，不能添加。");
      return;
    }
    setRegisteringKey(key);
    setMessage(`正在确认并添加 ${candidate.fund_name}...`);
    try {
      const refreshedPreview = await registerExecutionFund({
        reconcileId: screenshotPreview.reconcile_id,
        expectedPreviewSha256: screenshotPreview.preview_sha256,
        displayName: holding.display_name,
        fundCode: candidate.fund_code,
        userConfirmed: true
      });
      setScreenshotPreview(refreshedPreview);
      setReplaceConfirm("");
      setFundLookups({});
      const remaining = refreshedPreview.unmatched_detected.length;
      setMessage(remaining
        ? `${candidate.fund_name} 已添加并重新生成预览；还有 ${remaining} 只未匹配持仓，正在继续查询。`
        : `${candidate.fund_name} 已添加，新的预览已生成，请核对后再应用。`
      );
    } catch (error) {
      setMessage(`添加基金失败：${errorMessage(error)}`);
    } finally {
      setRegisteringKey("");
    }
  }

  async function applyScreenshot(mode: ScreenshotMode) {
    if (!screenshotPreview) return;
    if (!screenshotApplyReady) {
      setMessage(`当前预览不能应用：${screenshotBlockers.join(" ") || "完整性检查未通过。"}`);
      return;
    }
    if (mode === "replace" && replaceConfirm.trim().toUpperCase() !== "REPLACE") {
      setMessage("全部替换会把截图未出现的持仓归零；请输入 REPLACE 后再执行。");
      return;
    }
    setBusy(true);
    setMessage(mode === "replace" ? "正在按截图全部替换用户模拟组合..." : "正在按截图更新用户模拟组合...");
    try {
      await applyExecutionReconcile({
        reconcileId: screenshotPreview.reconcile_id,
        previewSha256: screenshotPreview.preview_sha256,
        expectedPortfolioStateSha256: screenshotPreview.portfolio_state_sha256,
        dropMissing: mode === "replace",
        confirmReplace: mode === "replace" ? replaceConfirm.trim().toUpperCase() : undefined
      });
      setScreenshotPreview(null);
      setReplaceConfirm("");
      setFundLookups({});
      setMessage(mode === "replace" ? "用户模拟组合已完全按截图替换。" : "用户模拟组合已按截图更新，未出现在截图中的持仓已保留。");
      onRefresh();
    } catch (error) {
      setMessage(`仓位同步失败：${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function refreshConfirmations() {
    setBusy(true);
    try {
      const result = await updateExecutionConfirmations({ date: today });
      setMessage(`模拟记录状态已刷新；当前组合不会因状态刷新自动改写。`);
      onRefresh();
    } catch (error) {
      setMessage(`确认状态刷新失败：${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <SimulationTrackRail simulation={executionSync.simulation ?? portfolio.simulation} />
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric title="模拟记录" value={executionSync.counts.pending ?? 0} body="计划中或已记录的用户模拟操作" />
        <Metric title="用户操作" value={executionSync.counts.trades ?? 0} body="已写入用户模拟账本" />
        <Metric title="执行偏差" value={executionSync.counts.deviations ?? 0} body="只用于执行纪律，不影响策略胜率" />
        <Metric title="组合同步" value={executionSync.counts.reports ?? 0} body="截图或快照更新用户模拟组合的记录" />
      </section>

      <TerminalPanel title="模拟状态" meta={`UPDATED ${executionSync.updatedAt || "暂无"}`} className="grid grid-cols-2 gap-px bg-slate-800/60 md:grid-cols-4">
        <ExecutionState label="建议生成" value="已读取" tone="success" />
        <ExecutionState label="用户记录" value={`${executionSync.counts.trades ?? 0} 笔`} tone="info" />
        <ExecutionState label="模拟待办" value={`${executionSync.counts.pending ?? 0} 笔`} tone={executionSync.counts.pending ? "warning" : "success"} />
        <ExecutionState label="组合同步" value={`${executionSync.counts.reports ?? 0} 份`} tone="accent" />
      </TerminalPanel>

      {message ? <div className="rounded-md border border-cyan-500/30 bg-cyan-950/25 px-4 py-3 text-sm text-cyan-100">{message}</div> : null}

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 xl:col-span-7">
          <SectionTitle title="记录用户模拟操作" meta="只写入用户模拟账本，不自动改写组合" />
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

        <Card className="col-span-12 p-4 xl:col-span-5">
          <SectionTitle title="同步用户组合快照" meta="识别后确认更新用户模拟组合" />
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
              <PreviewSummary
                preview={screenshotPreview}
                rows={recognizedRows}
                applyReady={screenshotApplyReady}
                blockers={screenshotBlockers}
                lookups={fundLookups}
                registeringKey={registeringKey}
                onRetry={(holding) => void loadFundCandidates(holding, unmatchedHoldingKey(holding))}
                onRegister={(holding, candidate) => void confirmFundRegistration(holding, candidate, unmatchedHoldingKey(holding))}
              />
              <div className="rounded-md border border-rose-500/30 bg-rose-950/20 p-3">
                <div className="text-xs font-semibold text-rose-100">全部替换确认</div>
                <p className="mt-1 text-xs leading-5 text-rose-100/80">只有选择“全部替换”时需要输入 REPLACE。该操作会把截图未出现的当前持仓归零。</p>
                <input
                  className={`${inputClass} mt-2 border-rose-500/40`}
                  value={replaceConfirm}
                  placeholder="REPLACE"
                  onChange={(event) => setReplaceConfirm(event.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" disabled={busy || !screenshotApplyReady} onClick={() => void applyScreenshot("update")}>
                  更新
                </Button>
                <Button variant="danger" disabled={busy || !screenshotApplyReady || replaceConfirm.trim().toUpperCase() !== "REPLACE"} onClick={() => void applyScreenshot("replace")}>
                  全部替换
                </Button>
                <Button variant="ghost" disabled={busy || Boolean(registeringKey)} onClick={() => { setScreenshotPreview(null); setReplaceConfirm(""); setFundLookups({}); }}>
                  取消
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 p-4 lg:col-span-6">
          <SectionTitle title="待确认交易" meta="到确认日/到账日后可刷新落仓" />
          <Button className="mb-3" variant="secondary" disabled={busy} onClick={() => void refreshConfirmations()}>
            刷新确认状态
          </Button>
          <TradeList items={executionSync.pending} empty="暂无待确认交易" />
        </Card>
        <Card className="col-span-12 p-4 lg:col-span-6">
          <SectionTitle title="最近用户模拟操作" meta="本地账本记录" />
          <TradeList items={executionSync.trades} empty="暂无用户模拟操作记录" />
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
    <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
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
    <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
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

function PreviewSummary({
  preview,
  rows,
  applyReady,
  blockers,
  lookups,
  registeringKey,
  onRetry,
  onRegister
}: {
  preview: ScreenshotPreview;
  rows: ScreenshotPreviewRow[];
  applyReady: boolean;
  blockers: string[];
  lookups: Record<string, FundLookupState>;
  registeringKey: string;
  onRetry: (holding: UnmatchedHolding) => void;
  onRegister: (holding: UnmatchedHolding, candidate: FundLookupCandidate) => void;
}) {
  const warnings = [...preview.warnings, ...preview.vision_warnings];
  const missing = preview.missing_items.length || preview.missing_portfolio_funds.length;
  return (
    <div className="space-y-3 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-100">识别到 {rows.length} 只基金</span>
        <Badge tone={applyReady ? "success" : "warning"}>{applyReady ? "可以应用" : "暂不可应用"}</Badge>
      </div>
      <div className="max-h-64 space-y-2 overflow-auto">
        {rows.map((row, index) => (
          <div key={`${text(row.fund_code ?? row.matched_fund_code, String(index))}-${index}`} className="rounded border border-slate-800 bg-slate-900/50 px-3 py-2">
            <div className="font-semibold text-slate-200">{text(row.fund_code ?? row.matched_fund_code)} {text(row.fund_name ?? row.matched_fund_name ?? row.display_name)}</div>
            <div className="mt-1 text-xs text-slate-500">
              当前市值 {signedMoney(row.current_value)} | 持仓收益 {signedMoney(row.holding_pnl)}
            </div>
          </div>
        ))}
      </div>
      {missing ? <div className="mt-3 text-xs text-amber-200">有 {missing} 只当前持仓未出现在截图中；选择“全部替换”时会归零。</div> : null}
      {blockers.length ? (
        <div className="rounded border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-xs leading-5 text-amber-100">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            应用前需要解决
          </div>
          {blockers.map((blocker) => (
            <div key={blocker} className="mt-1 pl-6">{blocker}</div>
          ))}
        </div>
      ) : null}
      {preview.unmatched_detected.map((holding) => {
        const key = unmatchedHoldingKey(holding);
        const lookup = lookups[key];
        return (
          <div key={key} className="border-t border-slate-800 pt-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-semibold text-slate-100">{holding.display_name}</div>
                <div className="mt-1 text-xs text-slate-500">
                  截图市值 {signedMoney(holding.current_value)} | 持仓收益 {signedMoney(holding.holding_pnl)}
                </div>
              </div>
              <Badge tone="warning">未匹配</Badge>
            </div>

            {!lookup || lookup.status === "loading" ? (
              <div className="mt-3 flex items-center gap-2 text-xs text-cyan-200">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在查询官方基金候选
              </div>
            ) : null}

            {lookup?.status === "error" ? (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded border border-rose-500/30 bg-rose-950/20 px-3 py-2 text-xs text-rose-100">
                <span>候选查询失败：{lookup.error}</span>
                <Button variant="secondary" className="h-8 gap-2" onClick={() => onRetry(holding)}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  重试
                </Button>
              </div>
            ) : null}

            {lookup?.status === "ready" && !lookup.candidates.length ? (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                <span>{lookup.warnings.join(" ") || "没有找到可核验的基金候选。"}</span>
                <Button variant="secondary" className="h-8 gap-2" onClick={() => onRetry(holding)}>
                  <Search className="h-3.5 w-3.5" />
                  重新查询
                </Button>
              </div>
            ) : null}

            {lookup?.candidates.map((candidate) => (
              <FundCandidate
                key={`${key}-${candidate.fund_code}`}
                candidate={candidate}
                disabled={Boolean(registeringKey) || !preview.reconcile_id || !/^\d{6}$/.test(candidate.fund_code) || !hasValidPreviewIntegrity(preview)}
                registering={registeringKey === key}
                onConfirm={() => onRegister(holding, candidate)}
              />
            ))}
          </div>
        );
      })}
      {warnings.map((item, index) => (
        <div key={index} className="mt-2 text-xs leading-5 text-slate-500">
          {item}
        </div>
      ))}
    </div>
  );
}

function ExecutionState({ label, value, tone }: { label: string; value: string; tone: "success" | "warning" | "info" | "accent" }) {
  return <div className="bg-[#0b0e12] px-3 py-3"><div className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</div><div className="mt-2 flex items-center justify-between gap-2 text-sm font-semibold text-slate-200"><span>{value}</span><TerminalState label={tone === "warning" ? "待确认" : "正常"} tone={tone} /></div></div>;
}

function FundCandidate({
  candidate,
  disabled,
  registering,
  onConfirm
}: {
  candidate: FundLookupCandidate;
  disabled: boolean;
  registering: boolean;
  onConfirm: () => void;
}) {
  return (
    <div className="mt-3 rounded border border-slate-700 bg-slate-900/50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words font-semibold text-slate-100">{candidate.fund_name || "官方名称暂无"}</div>
          <div className="mt-1 text-xs text-cyan-200">基金代码 {candidate.fund_code || "暂无"}</div>
        </div>
        {candidate.match_score !== null ? <Badge tone="accent">匹配度 {Math.round(candidate.match_score * 100)}%</Badge> : null}
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-xs sm:grid-cols-2">
        <CandidateField label="基金类型" value={candidate.fund_type} />
        <CandidateField label="基金公司" value={candidate.company_name} />
        <CandidateField label="基金经理" value={candidate.manager_name} />
        <CandidateField
          label="最新净值"
          value={candidate.latest_nav === null ? "" : `${candidate.latest_nav}${candidate.nav_date ? ` (${candidate.nav_date})` : ""}`}
        />
      </dl>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-3">
        <div className="flex flex-wrap gap-3 text-xs">
          {candidate.source_links.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-cyan-300 hover:text-cyan-100"
            >
              {link.label}
              <ExternalLink className="h-3 w-3" />
            </a>
          ))}
          {!candidate.source_links.length ? <span className="text-slate-500">暂无可核验来源链接</span> : null}
        </div>
        <Button variant="primary" className="gap-2" disabled={disabled} onClick={onConfirm}>
          {registering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {registering ? "正在添加" : "确认添加"}
        </Button>
      </div>
    </div>
  );
}

function CandidateField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-slate-200">{value || "暂无"}</dd>
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
            {operationText(item.operation_type)} | {text(item.trade_date)} | {signedMoney(item.amount ?? item.out_amount)}
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
