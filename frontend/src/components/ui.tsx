import { clsx } from "clsx";
import type { ReactNode } from "react";
import type { Tone } from "../lib/types";

const toneClass: Record<Tone, string> = {
  neutral: "border-slate-700/80 bg-slate-900/70 text-slate-200",
  accent: "border-cyan-500/40 bg-cyan-950/40 text-cyan-200",
  success: "border-emerald-500/40 bg-emerald-950/35 text-emerald-200",
  warning: "border-amber-500/40 bg-amber-950/35 text-amber-200",
  danger: "border-rose-500/40 bg-rose-950/35 text-rose-200",
  info: "border-indigo-500/40 bg-indigo-950/35 text-indigo-200",
  purple: "border-violet-500/40 bg-violet-950/35 text-violet-200",
  magenta: "border-pink-500/40 bg-pink-950/35 text-pink-200",
  amber: "border-amber-500/40 bg-amber-950/35 text-amber-200"
};

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return <span className={clsx("inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold", toneClass[tone], className)}>{children}</span>;
}

export function Button({
  children,
  variant = "secondary",
  className,
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(
        "inline-flex h-9 items-center justify-center rounded-md border px-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-cyan-400/60 bg-cyan-500/20 text-cyan-100 hover:bg-cyan-500/30",
        variant === "secondary" && "border-slate-700 bg-slate-900 text-slate-100 hover:border-cyan-700",
        variant === "ghost" && "border-transparent bg-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-100",
        variant === "danger" && "border-rose-500/50 bg-rose-950/30 text-rose-200 hover:bg-rose-900/30",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("okra-card", className)}>{children}</section>;
}

export function SectionTitle({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <h2 className="text-sm font-bold text-slate-100">{title}</h2>
      {meta ? <span className="text-xs text-slate-500">{meta}</span> : null}
    </div>
  );
}

export function MetricCard({ title, value, body, tone = "neutral" }: { title: string; value: string; body: string; tone?: Tone }) {
  const toneLabel: Record<Tone, string> = {
    neutral: "常规",
    accent: "重点",
    success: "良好",
    warning: "注意",
    danger: "风险",
    info: "信息",
    purple: "规则",
    magenta: "观察",
    amber: "提醒"
  };
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-slate-400">{title}</span>
        <Badge tone={tone}>{toneLabel[tone]}</Badge>
      </div>
      <div className="metric-number text-2xl font-bold text-slate-50">{value}</div>
      <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-400">{body}</p>
    </Card>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="okra-panel flex min-h-40 flex-col items-center justify-center p-6 text-center">
      <div className="text-sm font-semibold text-slate-200">{title}</div>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{body}</p>
    </div>
  );
}

export function DetailDrawer({
  open,
  title,
  subtitle,
  children,
  onClose
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/50 backdrop-blur-sm">
      <button className="absolute inset-0 cursor-default" aria-label="关闭详情" onClick={onClose} />
      <aside className="relative h-full w-[460px] border-l border-slate-800 bg-[#080d16] shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-5 py-4">
          <div>
            <div className="text-base font-bold text-slate-50">{title}</div>
            {subtitle ? <div className="mt-1 text-xs text-slate-500">{subtitle}</div> : null}
          </div>
          <Button variant="ghost" className="h-8 px-2" onClick={onClose}>
            关闭
          </Button>
        </div>
        <div className="h-[calc(100%-65px)] overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  );
}
