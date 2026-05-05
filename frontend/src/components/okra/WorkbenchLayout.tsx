import { Activity, BarChart3, BrainCircuit, Gauge, Settings, WalletCards } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui";
import { CopilotPanel } from "./CopilotPanel";

export type PageKey = "today" | "portfolio" | "research" | "realtime" | "review" | "system" | "fundDetail";

const nav = [
  { key: "today", label: "今日", icon: Gauge },
  { key: "portfolio", label: "持仓", icon: WalletCards },
  { key: "research", label: "研究", icon: BarChart3 },
  { key: "realtime", label: "实时", icon: Activity },
  { key: "review", label: "记忆", icon: BrainCircuit },
  { key: "system", label: "系统", icon: Settings }
] as const;

export function WorkbenchLayout({
  page,
  onPageChange,
  selectedDate,
  dates,
  onDateChange,
  onRunDaily,
  onRunRealtime,
  fundCode,
  children
}: {
  page: PageKey;
  onPageChange: (page: PageKey) => void;
  selectedDate: string;
  dates: string[];
  onDateChange: (date: string) => void;
  onRunDaily: () => void;
  onRunRealtime: () => void;
  fundCode?: string;
  children: ReactNode;
}) {
  const label = nav.find((item) => item.key === page)?.label ?? "基金详情";
  const context = `当前页面：${label}。查看日期：${selectedDate || "暂无"}`;
  return (
    <div className="flex h-full overflow-hidden">
      <aside className="flex w-[236px] shrink-0 flex-col border-r border-slate-800 bg-slate-950/80 p-4">
        <div className="mb-7">
          <div className="text-2xl font-black text-slate-50">OKRA</div>
          <div className="mt-1 text-xs font-bold text-cyan-300">长期记忆投资工作台</div>
        </div>
        <nav className="space-y-1">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                onClick={() => onPageChange(item.key)}
                className={`flex h-10 w-full items-center gap-3 rounded-md px-3 text-sm font-semibold transition ${
                  page === item.key ? "border border-cyan-500/40 bg-cyan-950/40 text-cyan-100" : "text-slate-400 hover:bg-slate-900 hover:text-slate-100"
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3">
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
            <Button variant="secondary" onClick={onRunDaily}>
              首启分析
            </Button>
            <Button variant="primary" onClick={onRunRealtime}>
              实时刷新
            </Button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto p-5">{children}</main>
      <CopilotPanel context={context} page={page} selectedDate={selectedDate} fundCode={fundCode} />
    </div>
  );
}
