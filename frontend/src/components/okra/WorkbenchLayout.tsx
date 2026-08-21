import { Activity, BarChart3, BrainCircuit, ChevronRight, Gauge, Newspaper, PlayCircle, ReceiptText, SearchCheck, Settings, WalletCards, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { SystemPayload } from "../../lib/types";
import { getTodayAnalysisRuntime, getTodayAnalysisSystem, runtimeStatusMeta } from "../../lib/todayAnalysis";
import { Button } from "../ui";
import { CopilotPanel } from "./CopilotPanel";

export type PageKey = "today" | "portfolio" | "execution" | "research" | "intelligence" | "realtime" | "review" | "shadowReview" | "system" | "fundDetail";

type NavItem = { key: PageKey; label: string; icon: LucideIcon };
type NavGroup = { label: string; items: NavItem[] };

const navGroups: NavGroup[] = [
  { label: "总览", items: [{ key: "today", label: "今日决策", icon: Gauge }] },
  {
    label: "资产",
    items: [
      { key: "portfolio", label: "组合与持仓", icon: WalletCards },
      { key: "execution", label: "交易执行台", icon: ReceiptText }
    ]
  },
  {
    label: "研究",
    items: [
      { key: "research", label: "研究建议", icon: BarChart3 },
      { key: "intelligence", label: "市场情报", icon: Newspaper },
      { key: "realtime", label: "实时估值", icon: Activity }
    ]
  },
  {
    label: "审计",
    items: [
      { key: "review", label: "策略记忆", icon: BrainCircuit },
      { key: "shadowReview", label: "影子审查", icon: SearchCheck },
      { key: "system", label: "运行中心", icon: Settings }
    ]
  }
];

export function WorkbenchLayout({
  page,
  selectedDate,
  dates,
  onDateChange,
  onRunDaily,
  onRunRealtime,
  autoRunToday,
  onAutoRunTodayChange,
  dailyRunLabel,
  dailyRunTarget,
  system,
  systemRunning,
  dailyRunning,
  fundCode,
  children
}: {
  page: PageKey;
  selectedDate: string;
  dates: string[];
  onDateChange: (date: string) => void;
  onRunDaily: () => void;
  onRunRealtime: () => void;
  autoRunToday: boolean;
  onAutoRunTodayChange: (enabled: boolean) => void;
  dailyRunLabel: string;
  dailyRunTarget: string;
  system?: SystemPayload;
  systemRunning?: boolean;
  dailyRunning?: boolean;
  fundCode?: string;
  children: ReactNode;
}) {
  const label = navGroups.flatMap((group) => group.items).find((item) => item.key === page)?.label ?? "基金详情";
  const context = `当前页面：${label}。查看日期：${selectedDate || "暂无"}`;
  const todayAnalysis = getTodayAnalysisSystem(system);
  const hasRunToday = Boolean(todayAnalysis?.hasRunToday ?? todayAnalysis?.todayDecisionExists);
  const runtime = getTodayAnalysisRuntime(system);
  const rawRuntimeMeta = runtimeStatusMeta(dailyRunning ? "running" : runtime?.status);
  const runtimeMeta = hasRunToday && ["idle", "unknown"].includes(rawRuntimeMeta.kind)
    ? runtimeStatusMeta("success")
    : !hasRunToday && rawRuntimeMeta.kind === "unknown"
      ? runtimeStatusMeta("idle")
      : rawRuntimeMeta;
  const todayRunLabel = `${hasRunToday && runtimeMeta.kind === "success" ? "已运行" : runtimeMeta.label}${todayAnalysis?.runTime ? ` · ${todayAnalysis.runTime}` : ""}`;
  const isHistoricalView = dailyRunTarget && dailyRunTarget !== new Date().toLocaleDateString("sv-SE");
  const sidebarRunLabel = isHistoricalView ? "历史数据" : todayRunLabel;
  const todayRunColor =
    runtimeMeta.tone === "danger"
      ? "text-rose-300"
      : runtimeMeta.tone === "warning"
        ? "text-amber-300"
        : runtimeMeta.tone === "success"
          ? "text-emerald-300"
          : runtimeMeta.tone === "accent"
            ? "text-cyan-300"
            : "text-slate-400";
  const sidebarRunColor = isHistoricalView ? "text-slate-400" : todayRunColor;
  const selectedDateQuery = selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : "";
  const contextualCopilot = page === "research" || page === "intelligence" || page === "fundDetail";
  const [copilotOpen, setCopilotOpen] = useState(contextualCopilot);

  useEffect(() => {
    setCopilotOpen(contextualCopilot);
  }, [contextualCopilot]);

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden bg-[hsl(var(--surface-0))] xl:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-slate-800 bg-[hsl(var(--surface-0))] p-3 xl:h-full xl:w-[220px] xl:border-b-0 xl:border-r xl:p-4">
        <div className="mb-4 xl:mb-7">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,0.7)]" />
            <div className="text-2xl font-black tracking-wide text-slate-50">OKRA</div>
          </div>
          <div className="mt-2 text-[11px] font-semibold tracking-wide text-slate-500">长期记忆投资工作台</div>
        </div>
        <nav className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:block">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-4 last:mb-0">
              <div className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">{group.label}</div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.key}
                      to={`${item.key === "shadowReview" ? "/shadow-review" : `/${item.key}`}${selectedDateQuery}`}
                      className={({ isActive }) =>
                        `group flex h-9 min-w-0 items-center justify-center gap-2 rounded-md border px-2 text-xs font-semibold transition xl:justify-start xl:gap-3 xl:px-3 ${
                          isActive
                            ? "border-cyan-400/40 bg-cyan-950/45 text-cyan-100 shadow-[inset_2px_0_0_rgba(103,232,249,0.9)]"
                            : "border-transparent text-slate-400 hover:border-slate-800 hover:bg-slate-900/80 hover:text-slate-100"
                        }`
                      }
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{item.label}</span>
                      <ChevronRight className="ml-auto hidden h-3.5 w-3.5 text-cyan-300/70 group-[.active]:block xl:block xl:opacity-0 xl:group-hover:opacity-100" />
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="mt-3 grid grid-cols-1 gap-2 xl:mt-auto xl:block">
          <div className="hidden rounded-md border border-slate-800 bg-slate-950/70 p-3 xl:block">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-bold text-slate-500">系统状态</span>
              <span className={`text-[11px] font-bold ${systemRunning ? "text-cyan-300" : "text-emerald-300"}`}>{systemRunning ? "运行中" : "空闲"}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-[11px] font-bold text-slate-500">今日分析</span>
              <span className={`text-right text-[11px] font-bold ${sidebarRunColor}`}>
                {sidebarRunLabel}
              </span>
            </div>
          </div>
        </div>
      </aside>
      <main className="w-full min-w-0 flex-1 overflow-auto overflow-x-hidden p-3 xl:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/90 pb-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
            <span className="font-bold uppercase tracking-[0.16em] text-slate-500">数据日期</span>
            <label className="sr-only" htmlFor="workbench-date">查看日期</label>
            <select
              id="workbench-date"
              value={selectedDate}
              onChange={(event) => onDateChange(event.target.value)}
              className="h-8 rounded-md border border-slate-700 bg-slate-950 px-2 text-xs font-semibold text-slate-100"
            >
              {dates.map((date) => (
                <option key={date} value={date}>{date}</option>
              ))}
            </select>
            <span className="hidden text-slate-600 sm:inline">/</span>
            <span className="text-slate-500">运行目标 <span className="font-semibold text-slate-300">{dailyRunTarget}</span></span>
            <span className={`rounded-sm border px-2 py-1 font-semibold ${systemRunning ? "border-cyan-500/40 bg-cyan-950/30 text-cyan-200" : "border-emerald-500/30 bg-emerald-950/20 text-emerald-200"}`}>
              {systemRunning ? "运行中" : "系统空闲"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex h-8 cursor-pointer items-center gap-2 rounded-md border border-slate-800 bg-slate-950/70 px-2 text-xs text-slate-400">
              <input type="checkbox" checked={autoRunToday} onChange={(event) => onAutoRunTodayChange(event.target.checked)} />
              自动分析
            </label>
            <Button variant="secondary" className="h-8 gap-2 px-2.5 text-xs" onClick={onRunDaily}>
              <PlayCircle className="h-3.5 w-3.5" />
              {dailyRunLabel}
            </Button>
            <Button variant="primary" className="h-8 px-2.5 text-xs" onClick={onRunRealtime}>
              刷新行情
            </Button>
          </div>
        </div>
        {children}
      </main>
      <CopilotPanel open={copilotOpen} onToggle={() => setCopilotOpen((current) => !current)} context={context} page={page} selectedDate={selectedDate} fundCode={fundCode} />
    </div>
  );
}
