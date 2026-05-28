import { Activity, BarChart3, BrainCircuit, Gauge, Newspaper, PlayCircle, ReceiptText, SearchCheck, Settings, WalletCards } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { SystemPayload } from "../../lib/types";
import { getTodayAnalysisSystem } from "../../lib/todayAnalysis";
import { Button } from "../ui";
import { CopilotPanel } from "./CopilotPanel";

export type PageKey = "today" | "portfolio" | "execution" | "research" | "intelligence" | "realtime" | "review" | "shadowReview" | "system" | "fundDetail";

const nav = [
  { key: "today", label: "今日", icon: Gauge },
  { key: "portfolio", label: "持仓", icon: WalletCards },
  { key: "execution", label: "执行", icon: ReceiptText },
  { key: "research", label: "研究", icon: BarChart3 },
  { key: "intelligence", label: "资讯", icon: Newspaper },
  { key: "realtime", label: "实时", icon: Activity },
  { key: "review", label: "记忆", icon: BrainCircuit },
  { key: "shadowReview", label: "Shadow", icon: SearchCheck },
  { key: "system", label: "系统", icon: Settings }
] as const;

export function WorkbenchLayout({
  page,
  selectedDate,
  dates,
  onDateChange,
  onRunDaily,
  onRunRealtime,
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
  system?: SystemPayload;
  systemRunning?: boolean;
  dailyRunning?: boolean;
  fundCode?: string;
  children: ReactNode;
}) {
  const label = nav.find((item) => item.key === page)?.label ?? "基金详情";
  const context = `当前页面：${label}。查看日期：${selectedDate || "暂无"}`;
  const todayAnalysis = getTodayAnalysisSystem(system);
  const hasRunToday = Boolean(todayAnalysis?.hasRunToday ?? todayAnalysis?.todayDecisionExists);
  const todayRunLabel = dailyRunning ? "运行中" : hasRunToday ? `已运行${todayAnalysis?.runTime ? ` · ${todayAnalysis.runTime}` : ""}` : "今日未跑";
  const selectedDateQuery = selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : "";

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden xl:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-slate-800 bg-slate-950/80 p-3 xl:h-full xl:w-[236px] xl:border-b-0 xl:border-r xl:p-4">
        <div className="mb-3 xl:mb-7">
          <div className="text-2xl font-black text-slate-50">OKRA</div>
          <div className="mt-1 text-xs font-bold text-cyan-300">长期记忆投资工作台</div>
        </div>
        <nav className="grid grid-cols-3 gap-2 sm:grid-cols-4 xl:block xl:space-y-1">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.key}
                to={`${item.key === "shadowReview" ? "/shadow-review" : `/${item.key}`}${selectedDateQuery}`}
                className={({ isActive }) =>
                  `flex h-10 min-w-0 items-center justify-center gap-2 rounded-md px-2 text-sm font-semibold transition xl:justify-start xl:gap-3 xl:px-3 ${
                    isActive ? "border border-cyan-500/40 bg-cyan-950/40 text-cyan-100" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100"
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto] xl:mt-auto xl:block xl:space-y-3">
          <div className="hidden rounded-md border border-slate-800 bg-slate-950/60 p-3 xl:block">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-slate-400">系统状态</span>
              <span className={`text-xs font-bold ${systemRunning ? "text-cyan-300" : "text-emerald-300"}`}>{systemRunning ? "正在运行" : "空闲"}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-slate-400">今日分析</span>
              <span className={`text-right text-xs font-bold ${dailyRunning ? "text-cyan-300" : hasRunToday ? "text-emerald-300" : "text-amber-300"}`}>
                {todayRunLabel}
              </span>
            </div>
          </div>
          <select
            value={selectedDate}
            onChange={(event) => onDateChange(event.target.value)}
            className="h-9 w-full rounded-md border border-slate-800 bg-slate-950 px-2 text-sm text-slate-200"
          >
            {dates.map((date) => (
              <option key={date} value={date}>
                {date}
              </option>
            ))}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" className="gap-2" onClick={onRunDaily}>
              <PlayCircle className="h-4 w-4" />
              今日分析
            </Button>
            <Button variant="primary" onClick={onRunRealtime}>
              实时刷新
            </Button>
          </div>
        </div>
      </aside>
      <main className="w-full min-w-0 flex-1 overflow-auto overflow-x-hidden p-3 xl:p-5">{children}</main>
      <CopilotPanel context={context} page={page} selectedDate={selectedDate} fundCode={fundCode} />
    </div>
  );
}
