import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Plus, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { createStrategyExperiment, getStrategySimulation, recordStrategySimulationAction } from "../../lib/api";
import { compactMoney } from "../../lib/format";
import { valueLabel } from "../../lib/display";
import { Badge, Button, EmptyState } from "../ui";
import { TerminalPanel } from "./TerminalChrome";

const actionLabels = {
  buy: "假设买入",
  sell: "假设卖出",
  switch_in: "假设换入",
  switch_out: "假设换出"
} as const;

export function StrategySimulationPanel({ selectedDate }: { selectedDate: string }) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("策略实验");
  const [experimentId, setExperimentId] = useState("");
  const [action, setAction] = useState<keyof typeof actionLabels>("buy");
  const [fundCode, setFundCode] = useState("");
  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const overview = useQuery({ queryKey: ["strategy-simulation"], queryFn: getStrategySimulation, staleTime: 10_000 });
  const experiments = overview.data?.experiments ?? [];
  const selectedId = experimentId || experiments[0]?.experimentId || "";
  const create = useMutation({
    mutationFn: () => createStrategyExperiment({ label: label.trim() || "策略实验", asOfDate: selectedDate }),
    onSuccess: async (result) => {
      const experiment = result.experiment as Record<string, unknown> | undefined;
      setExperimentId(String(experiment?.experimentId ?? ""));
      setMessage("策略实验已创建，当前仍与用户模拟组合隔离。");
      await queryClient.invalidateQueries({ queryKey: ["strategy-simulation"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "创建策略实验失败")
  });
  const simulate = useMutation({
    mutationFn: () => recordStrategySimulationAction({
      experimentId: selectedId,
      action,
      fundCode: fundCode.trim(),
      amount: Number(amount),
      asOfDate: selectedDate
    }),
    onSuccess: async () => {
      setMessage("假设交易已应用到策略实验组合，用户模拟组合未改变。");
      setAmount("");
      await queryClient.invalidateQueries({ queryKey: ["strategy-simulation"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "策略实验操作失败")
  });
  const validAction = Boolean(selectedId && fundCode.trim() && Number.isFinite(Number(amount)) && Number(amount) > 0);
  const active = useMemo(() => experiments.find((item) => item.experimentId === selectedId), [experiments, selectedId]);

  return (
    <TerminalPanel title="策略实验 / SANDBOX" meta="与用户模拟组合永久隔离" className="p-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-slate-300"><FlaskConical className="h-4 w-4 text-amber-300" /> 自由验证规则、回放和假设仓位，不会改变当前组合。</div>
          <div className="flex gap-2">
            <input value={label} onChange={(event) => setLabel(event.target.value)} className="min-w-0 flex-1 rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100 outline-none focus:border-cyan-600" aria-label="策略实验名称" />
            <Button variant="secondary" className="gap-2" disabled={create.isPending} onClick={() => create.mutate()}><Plus className="h-4 w-4" />创建</Button>
          </div>
          {experiments.length ? <div className="space-y-2">{experiments.slice(0, 5).map((item) => <button key={item.experimentId} type="button" onClick={() => setExperimentId(item.experimentId)} className={`flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left ${item.experimentId === selectedId ? "border-amber-400/50 bg-amber-950/20" : "border-slate-800 bg-slate-950/50 hover:border-slate-700"}`}><span className="min-w-0 truncate text-sm font-semibold text-slate-200">{item.label}</span><span className="flex shrink-0 items-center gap-2"><Badge tone="warning">{item.actionCount} 笔</Badge><span className="text-xs text-slate-500">{valueLabel(item.status)}</span></span></button>)}</div> : <EmptyState title="暂无策略实验" body="创建一个实验后，可在隔离组合中执行假设买卖并观察策略路径。" />}
        </section>
        <section className="space-y-3 border-t border-slate-800 pt-4 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
          <div className="flex items-center justify-between gap-3"><div><div className="text-sm font-semibold text-slate-100">假设交易</div><div className="mt-1 text-xs text-slate-500">{active ? `${active.label} · 当前市值 ${compactMoney(active.totalValue)}` : "先选择或创建策略实验"}</div></div><Badge tone="info">实验轨道</Badge></div>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_120px]">
            <select value={action} onChange={(event) => setAction(event.target.value as keyof typeof actionLabels)} className="rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100"><option value="buy">假设买入</option><option value="sell">假设卖出</option><option value="switch_in">假设换入</option><option value="switch_out">假设换出</option></select>
            <input value={fundCode} onChange={(event) => setFundCode(event.target.value)} placeholder="基金代码" className="rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100 outline-none focus:border-cyan-600" />
            <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" placeholder="金额" className="rounded-md border border-slate-800 bg-slate-950 px-3 text-sm text-slate-100 outline-none focus:border-cyan-600" />
          </div>
          <Button variant="primary" className="w-full gap-2" disabled={!validAction || simulate.isPending} onClick={() => simulate.mutate()}><Play className="h-4 w-4" />{actionLabels[action]}</Button>
          {message ? <p className="text-xs leading-5 text-slate-400">{message}</p> : null}
        </section>
      </div>
    </TerminalPanel>
  );
}
