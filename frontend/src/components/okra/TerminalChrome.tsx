import { Activity, Clock3, Crosshair, Radio, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Button } from "../ui";

export function TerminalPanel({ children, className = "", title, meta, action }: { children: ReactNode; className?: string; title?: string; meta?: string; action?: ReactNode }) {
  return (
    <section className={`terminal-panel ${className}`}>
      {title ? (
        <div className="terminal-panel-header">
          <div className="flex min-w-0 items-center gap-2">
            <span className="terminal-marker" />
            <h2 className="truncate text-sm font-semibold text-slate-100">{title}</h2>
            {meta ? <span className="truncate text-[10px] uppercase tracking-[0.12em] text-slate-600">{meta}</span> : null}
          </div>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function ChartFrame({ children, title, meta, height = "h-64", className = "" }: { children: ReactNode; title: string; meta?: string; height?: string; className?: string }) {
  return (
    <TerminalPanel title={title} meta={meta} className={className}>
      <div className={`terminal-chart ${height}`}>{children}</div>
    </TerminalPanel>
  );
}

export function TerminalRail({ selectedDate, status = "LOCAL", freshness = "研究模式", onRefresh }: { selectedDate?: string; status?: string; freshness?: string; onRefresh?: () => void }) {
  return (
    <div className="terminal-rail">
      <div className="flex min-w-0 items-center gap-3">
        <span className="terminal-brand-mark">OKRA</span>
        <span className="hidden text-xs text-slate-500 sm:inline">RESEARCH TERMINAL</span>
        <span className="terminal-rail-divider" />
        <span className="hidden items-center gap-1.5 text-xs text-slate-400 md:flex"><Clock3 className="h-3.5 w-3.5" /> {selectedDate || "暂无日期"}</span>
      </div>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]">
        <span className={`terminal-live ${status === "RUNNING" ? "terminal-live-active" : ""}`}><Radio className="h-3 w-3" /> {status}</span>
        <span className="terminal-freshness"><Activity className="h-3 w-3" /> {freshness}</span>
        {onRefresh ? <Button variant="ghost" className="h-7 px-2" onClick={onRefresh} aria-label="刷新终端数据" title="刷新终端数据"><RefreshCw className="h-3.5 w-3.5" /></Button> : null}
      </div>
    </div>
  );
}

export function TerminalFooter({ status = "NORMAL", code = "OKRA-TRM-7A2C" }: { status?: string; code?: string }) {
  return (
    <div className="terminal-footer">
      <span className="terminal-footer-code">{code}</span>
      <span className="terminal-footer-line" />
      <span className="flex items-center gap-1.5"><span className="terminal-heartbeat" /> 本地研究链路 {status}</span>
      <span className="hidden sm:inline">/</span>
      <span className="hidden sm:inline">模拟模式</span>
    </div>
  );
}

export function CrosshairHint({ label = "悬停查看详细数据" }: { label?: string }) {
  return <div className="terminal-crosshair-hint"><Crosshair className="h-3.5 w-3.5" /> {label}</div>;
}

export function TerminalState({ label, tone = "neutral" }: { label: string; tone?: "neutral" | "success" | "warning" | "danger" | "accent" | "info" }) {
  return <Badge tone={tone}>{label}</Badge>;
}

export function useTerminalClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now.toLocaleTimeString("zh-CN", { hour12: false });
}
