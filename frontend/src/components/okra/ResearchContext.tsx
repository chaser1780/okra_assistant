import { Database, FlaskConical, ShieldCheck, TimerReset } from "lucide-react";
import type { DataContext, SimulationPayload } from "../../lib/types";
import { Badge } from "../ui";

const freshnessCopy: Record<string, { label: string; tone: "success" | "warning" | "danger" | "info" | "neutral" }> = {
  latest: { label: "数据最新", tone: "success" },
  market_closed: { label: "收盘快照", tone: "info" },
  official_nav_pending: { label: "官方净值待确认", tone: "warning" },
  proxy_observation: { label: "代理观察", tone: "info" },
  delayed_1d: { label: "滞后 1 日", tone: "warning" },
  delayed_multi_day: { label: "滞后多日", tone: "danger" },
  unavailable: { label: "暂无可用数据", tone: "neutral" },
  conflict: { label: "数据存在冲突", tone: "danger" }
};

export function ResearchDataContext({ context, className = "" }: { context?: DataContext; className?: string }) {
  if (!context) return null;
  const freshness = freshnessCopy[context.freshnessStatus] ?? { label: "数据状态未知", tone: "neutral" as const };
  return (
    <section className={`terminal-context-grid ${className}`} aria-label="数据研究上下文">
      <div className="terminal-context-item">
        <Database className="h-3.5 w-3.5 text-cyan-300" />
        <div>
          <div className="terminal-context-label">数据基准</div>
          <div className="terminal-context-value">组合 {context.portfolioAsOfDate || "暂无"} / 观察 {context.realtimeAsOfDate || "暂无"}</div>
        </div>
      </div>
      <div className="terminal-context-item">
        <TimerReset className="h-3.5 w-3.5 text-slate-400" />
        <div>
          <div className="terminal-context-label">市场状态</div>
          <div className="terminal-context-value">{sessionLabel(context.sessionStatus)}{context.latestRetrievedAt ? ` · ${timeLabel(context.latestRetrievedAt)}` : ""}</div>
        </div>
      </div>
      <div className="terminal-context-item terminal-context-status">
        <Badge tone={freshness.tone}>{freshness.label}</Badge>
        <span className="line-clamp-1 text-[11px] text-slate-500" title={context.freshnessReason}>{context.freshnessReason || "暂无数据说明"}</span>
      </div>
    </section>
  );
}

export function SimulationTrackRail({ simulation, className = "" }: { simulation?: SimulationPayload; className?: string }) {
  if (!simulation) return null;
  const user = simulation.userSimulation;
  const strategy = simulation.strategySimulation;
  return (
    <section className={`simulation-track-rail ${className}`} aria-label="模拟轨道">
      <div className="flex min-w-0 items-center gap-2">
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
        <div className="min-w-0">
          <div className="terminal-context-label">当前组合</div>
          <div className="truncate text-xs font-semibold text-slate-200">{user?.label ?? "用户模拟组合"}</div>
        </div>
      </div>
      <div className="simulation-track-divider" />
      <div className="min-w-0 text-xs text-slate-500">
        用户操作 {operationCount(user)} 笔，仅影响当前模拟组合
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-2">
        <FlaskConical className="h-3.5 w-3.5 shrink-0 text-amber-300" />
        <span className="truncate text-xs text-slate-400">策略实验 {strategy?.experimentCount ?? 0} 项，不影响当前组合</span>
      </div>
    </section>
  );
}

function operationCount(track?: SimulationPayload["userSimulation"]) {
  return Object.values(track?.operationCounts ?? {}).reduce((sum, value) => sum + Number(value || 0), 0);
}

function sessionLabel(value: string) {
  const labels: Record<string, string> = {
    market_open: "市场开盘",
    market_closed: "市场已收盘",
    historical_snapshot: "历史快照",
    unknown: "时段未知"
  };
  return labels[value] ?? (value || "时段未知");
}

function timeLabel(value: string) {
  const match = String(value).match(/(?:T|\s)(\d{2}:\d{2})/);
  return match?.[1] ?? String(value).slice(0, 16);
}
