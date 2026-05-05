import { ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { getFundDetail } from "../../lib/api";
import type { FundDetailPayload, LongMemoryRecord } from "../../lib/types";
import { asNumber, compactMoney, lines, signedMoney, signedPct, text } from "../../lib/format";
import { actionLabel, evidencePathLabel, memoryText, memoryTitle, roleLabel, statusLabel, styleLabel } from "../../lib/display";
import { Badge, Button, Card, EmptyState, SectionTitle } from "../../components/ui";

const ranges = ["近1月", "近3月", "近6月", "近1年", "成立以来"];

export function FundDetailPage({
  fundCode,
  selectedDate,
  onBack
}: {
  fundCode: string;
  selectedDate: string;
  onBack: () => void;
}) {
  const [range, setRange] = useState("成立以来");
  const [detail, setDetail] = useState<FundDetailPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    getFundDetail(fundCode, selectedDate, range)
      .then((payload) => {
        if (alive) setDetail(payload);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : "基金详情加载失败。");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [fundCode, selectedDate, range]);

  const trendData = useMemo(() => {
    const proxyMap = new Map((detail?.history.proxyNormalized ?? []).map((point) => [point.date, point.value]));
    return (detail?.history.navNormalized ?? []).map((point) => ({
      date: point.date,
      nav: point.value,
      proxy: proxyMap.get(point.date)
    }));
  }, [detail]);

  const changeData = useMemo(() => {
    const estimateMap = new Map((detail?.history.estimateChangePct ?? []).map((point) => [point.date, point.value]));
    return (detail?.history.dayChangePct ?? []).map((point) => ({
      date: point.date,
      day: point.value,
      estimate: estimateMap.get(point.date)
    }));
  }, [detail]);

  if (loading) {
    return (
      <Card className="flex min-h-[520px] items-center justify-center p-8">
        <div className="flex items-center gap-3 text-slate-300">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
          正在加载基金详情
        </div>
      </Card>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" className="gap-2" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
          返回
        </Button>
        <EmptyState title="基金详情加载失败" body={error || "没有拿到基金详情数据。"} />
      </div>
    );
  }

  const portfolio = detail.portfolio ?? {};
  const realtime = detail.realtime ?? {};
  const research = detail.research ?? {};

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Button variant="ghost" className="mb-3 gap-2 px-0" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            返回上一页
          </Button>
          <div className="text-xs font-bold uppercase tracking-normal text-cyan-300">基金详情</div>
          <h1 className="mt-1 text-2xl font-black text-slate-50">{detail.fundName}</h1>
          <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
            <span>{detail.fundCode}</span>
            <span>|</span>
            <span>{styleLabel(portfolio.styleGroup || realtime.style_group || "未分组")}</span>
            <span>|</span>
            <span>{detail.selectedDate}</span>
          </div>
        </div>
        <div className="flex rounded-md border border-slate-800 bg-slate-950 p-1">
          {ranges.map((item) => (
            <button
              key={item}
              onClick={() => setRange(item)}
              className={`h-8 rounded px-3 text-xs font-bold transition ${
                range === item ? "bg-cyan-500/20 text-cyan-100" : "text-slate-500 hover:text-slate-200"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        <SummaryTile label="当前市值" value={text(portfolio.amountText, "暂无")} />
        <SummaryTile label="持有盈亏" value={text(portfolio.holdingPnlText, "暂无")} tone={pnlTone(portfolio.holdingPnl)} />
        <SummaryTile label="持有收益率" value={text(portfolio.holdingReturnPctText, "暂无")} tone={pnlTone(portfolio.holdingReturnPct)} />
        <SummaryTile label="今日估算" value={signedPct(realtime.effective_change_pct)} tone={pnlTone(realtime.effective_change_pct)} />
        <SummaryTile label="区间净值表现" value={detail.performance.stageReturn} />
      </div>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-8 p-4">
          <SectionTitle title="长期画像" meta="建议成败基于系统每日复盘，不基于真实交易" />
          <MemoryList records={detail.longMemory.fund} empty="这只基金还没有形成长期画像，运行首启分析后会逐步积累。" />
        </Card>
        <Card className="col-span-4 p-4">
          <SectionTitle title="适用规则与执行纪律" meta="下单前检查" />
          <MemoryList records={[...detail.longMemory.rules, ...detail.longMemory.execution].slice(0, 6)} empty="暂无触发的执行纪律。" compact />
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-8 p-4">
          <SectionTitle title="历史净值走势" meta={`净值源 ${detail.performance.navSource || "暂无"} | 代理 ${detail.performance.proxyName || "暂无"}`} />
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData} margin={{ left: 0, right: 10, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} />
                <Line type="monotone" dataKey="nav" name="基金净值" stroke="#22d3ee" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="proxy" name="代理/基准" stroke="#34d399" dot={false} strokeWidth={2} strokeDasharray="4 4" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="col-span-4 p-4">
          <SectionTitle title="实时估值" meta={text(realtime.mode, "暂无模式")} />
          <div className="space-y-3">
            <InfoRow label="采用涨跌" value={signedPct(realtime.effective_change_pct)} tone={pnlTone(realtime.effective_change_pct)} />
            <InfoRow label="估算涨跌" value={signedPct(realtime.estimate_change_pct)} />
            <InfoRow label="代理涨跌" value={signedPct(realtime.proxy_change_pct)} />
            <InfoRow label="今日估算收益" value={signedMoney(realtime.estimated_intraday_pnl_amount)} />
            <InfoRow label="异常分数" value={asNumber(realtime.anomaly_score).toFixed(2)} />
            <InfoRow label="置信度" value={asNumber(realtime.confidence).toFixed(2)} />
          </div>
          <p className="mt-4 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-400">{text(realtime.reason, "暂无估值说明。")}</p>
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-6 p-4">
          <SectionTitle title="日涨跌与估值变化" meta="对比官方日涨跌和实时估值序列" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={changeData} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={18} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(value) => `${value}%`} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} formatter={(value) => signedPct(value)} />
                <Bar dataKey="day" name="日涨跌" radius={[4, 4, 0, 0]} fill="#22d3ee" />
                <Bar dataKey="estimate" name="估值涨跌" radius={[4, 4, 0, 0]} fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="col-span-6 p-4">
          <SectionTitle title="我的持仓收益" meta="来自组合历史快照" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={detail.history.holdingPnl} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="holdingPnl" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.42} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={18} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={compactMoney} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8 }} formatter={(value) => [signedMoney(value), "持有盈亏"]} />
                <Area type="monotone" dataKey="value" stroke="#34d399" strokeWidth={2} fill="url(#holdingPnl)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-4">
          <SectionTitle title="交易记录" meta="买入/卖出/定投标记" />
          {detail.tradeMarkers.length ? (
            <div className="space-y-2">
              {detail.tradeMarkers.slice(-8).reverse().map((item) => (
                <div key={`${item.date}-${item.action}-${item.amount}`} className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm">
                  <div>
                    <div className="font-semibold text-slate-200">{item.date}</div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      <Badge tone={item.source === "planned_dca" ? "success" : "info"}>{actionLabel(item.action)}</Badge>
                      <span>{item.source === "planned_dca" ? "按定投日生成" : "真实交易"}</span>
                    </div>
                  </div>
                  <div className="metric-number text-slate-100">{item.amountText}</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="暂无交易标记" body="该基金在当前区间没有可展示的交易记录。" />
          )}
        </Card>

        <Card className="col-span-7 p-4">
          <SectionTitle title="AI 建议上下文" meta={text(research.validated_action, text(research._section, "暂无建议"))} />
          <div className="space-y-3">
            <p className="rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm leading-6 text-slate-300">{text(research.thesis || research.reason, "暂无建议理由")}</p>
            <div className="grid grid-cols-2 gap-3">
              <InfoRow label="建议动作" value={text(research.validated_action, "暂无")} />
              <InfoRow label="建议金额" value={text(research.validated_amount, "0")} />
              <InfoRow label="AI 共识" value={text(research._consensus_text, "暂无")} />
              <InfoRow label="冲突提示" value={research._has_conflict ? "存在分歧" : "无明显分歧"} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <EvidenceList title="证据" items={lines(research.evidence as string[] | string | undefined, "暂无证据")} />
              <EvidenceList title="风险" items={lines(research.risks as string[] | string | undefined, "暂无风险")} />
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}

function SummaryTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "success" | "danger" | "warning" }) {
  const toneClass =
    tone === "success" ? "text-emerald-200" : tone === "danger" ? "text-rose-200" : tone === "warning" ? "text-amber-200" : "text-slate-100";
  return (
    <Card className="p-4">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className={`metric-number mt-2 text-xl font-black ${toneClass}`}>{value}</div>
    </Card>
  );
}

function InfoRow({ label, value, tone }: { label: string; value: string; tone?: "neutral" | "success" | "danger" | "warning" }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm">
      <span className="text-slate-500">{label}</span>
      {tone ? <Badge tone={tone}>{value}</Badge> : <span className="metric-number text-right font-semibold text-slate-200">{value}</span>}
    </div>
  );
}

function EvidenceList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="mb-2 text-sm font-bold text-slate-200">{title}</div>
      <ul className="space-y-1 text-sm leading-6 text-slate-400">
        {items.slice(0, 5).map((item) => (
          <li key={item}>- {evidencePathLabel(item)}</li>
        ))}
      </ul>
    </div>
  );
}

function MemoryList({ records, empty, compact = false }: { records: LongMemoryRecord[]; empty: string; compact?: boolean }) {
  if (!records.length) return <p className="text-sm leading-6 text-slate-500">{empty}</p>;
  return (
    <div className={`grid gap-3 ${compact ? "grid-cols-1" : "grid-cols-2"}`}>
      {records.slice(0, compact ? 6 : 8).map((item) => (
        <div key={item.memory_id} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="truncate text-sm font-bold text-slate-100">{memoryTitle(item.title)}</div>
            <Badge tone={item.status === "permanent" ? "success" : item.status === "strategic" ? "warning" : "info"}>{statusLabel(item.status)}</Badge>
          </div>
          <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-500">{memoryText(item.text)}</p>
        </div>
      ))}
    </div>
  );
}

function pnlTone(value: unknown) {
  const parsed = asNumber(value);
  if (parsed > 0) return "success" as const;
  if (parsed < 0) return "danger" as const;
  return "neutral" as const;
}
