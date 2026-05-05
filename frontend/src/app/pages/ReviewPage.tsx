import { Check, ExternalLink, RotateCcw, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { LongMemoryPayload, LongMemoryRecord, MemoryAction, ReviewPayload, Tone } from "../../lib/types";
import { lines } from "../../lib/format";
import { domainLabel, entityLabel, evidencePathLabel, memoryText, memoryTitle, statusLabel } from "../../lib/display";
import { Badge, Button, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";

type TabKey = "fund" | "market" | "execution" | "pending";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "fund", label: "基金画像" },
  { key: "market", label: "大盘规律" },
  { key: "execution", label: "执行纪律" },
  { key: "pending", label: "待确认策略" }
];

export function ReviewPage({
  review,
  longMemory,
  onMemoryAction
}: {
  review: ReviewPayload;
  longMemory: LongMemoryPayload;
  onMemoryAction: (memoryId: string, action: MemoryAction, note?: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<TabKey>("pending");
  const [noteById, setNoteById] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState("");
  const tabRecords = useMemo(() => {
    if (tab === "pending") return longMemory.pending;
    return longMemory[tab];
  }, [longMemory, tab]);

  async function act(memoryId: string, action: MemoryAction) {
    setBusyId(memoryId);
    try {
      await onMemoryAction(memoryId, action, noteById[memoryId] ?? "");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {review.metrics.map((metric) => (
          <MetricCard key={metric.title} {...metric} />
        ))}
      </div>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-3 p-4">
          <SectionTitle title="长期记忆总览" meta={longMemory.updatedAt} />
          <div className="space-y-2">
            <CountLine label="基金画像" value={longMemory.counts.fund ?? 0} />
            <CountLine label="大盘规律" value={longMemory.counts.market ?? 0} />
            <CountLine label="执行纪律" value={longMemory.counts.execution ?? 0} />
            <CountLine label="组合策略" value={longMemory.counts.portfolio ?? 0} />
            <CountLine label="待确认策略" value={longMemory.counts.pending ?? 0} tone="warning" />
          </div>
        </Card>

        <Card className="col-span-9 p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <SectionTitle title="长期记忆中心" meta="本地 SQLite/JSON 为真实源；全文检索和向量仅作为索引层" />
            <div className="flex rounded-md border border-slate-800 bg-slate-950 p-1">
              {tabs.map((item) => (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  className={`h-8 rounded px-3 text-xs font-bold transition ${
                    tab === item.key ? "bg-cyan-500/20 text-cyan-100" : "text-slate-500 hover:text-slate-200"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {tabRecords.length ? (
            <div className="space-y-3">
              {tabRecords.map((record) => (
                <MemoryCard
                  key={record.memory_id}
                  record={record}
                  pending={tab === "pending"}
                  busy={busyId === record.memory_id}
                  note={noteById[record.memory_id] ?? ""}
                  onNote={(value) => setNoteById((current) => ({ ...current, [record.memory_id]: value }))}
                  onAction={(action) => void act(record.memory_id, action)}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title="暂无长期记忆"
              body="运行每日首启分析或长期记忆更新后，这里会展示基金画像、大盘规律、执行纪律和待确认策略。"
            />
          )}
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-4 p-4">
          <SectionTitle title="旧复盘摘要" meta={review.meta} />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {lines(review.summary_text).slice(0, 10).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
        <Card className="col-span-4 p-4">
          <SectionTitle title="兼容永久规则" />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {(review.core_lines.length ? review.core_lines : ["暂无兼容规则"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
        <Card className="col-span-4 p-4">
          <SectionTitle title="重放学习" />
          <ul className="space-y-2 text-sm leading-6 text-slate-400">
            {(review.replay_lines.length ? review.replay_lines : ["暂无重放实验"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Card>
      </section>

      <Card className="p-4">
        <SectionTitle title="复盘报告" meta="迁移期保留旧报告；新的永久规则以审批区为准" />
        <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap text-sm leading-7 text-slate-400">{review.detail_text}</pre>
      </Card>
    </div>
  );
}

function CountLine({ label, value, tone = "neutral" }: { label: string; value: number; tone?: Tone }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
      <span className="text-slate-500">{label}</span>
      <Badge tone={tone}>{value}</Badge>
    </div>
  );
}

function MemoryCard({
  record,
  pending,
  busy,
  note,
  onNote,
  onAction
}: {
  record: LongMemoryRecord;
  pending: boolean;
  busy: boolean;
  note: string;
  onNote: (value: string) => void;
  onAction: (action: MemoryAction) => void;
}) {
  const evidence = record.evidence_refs ?? [];
  const canApprove = canApprovePermanent(record);
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-slate-100">{memoryTitle(record.title)}</h3>
            <Badge tone={statusTone(record.status)}>{statusLabel(record.status)}</Badge>
            <Badge tone="info">{domainLabel(record.domain)}</Badge>
            <Badge tone="neutral">{entityLabel(record.entity_key)}</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">{memoryText(record.text)}</p>
          {!canApprove && record.domain === "fund" ? (
            <p className="mt-2 text-xs leading-5 text-slate-500">
              基金画像用于长期学习单只基金的行为规律，不会直接设为永久规则；可复用结论会沉淀为组合、执行或大盘策略。
            </p>
          ) : null}
        </div>
        <div className="metric-number shrink-0 text-right text-xs text-slate-500">
          <div>置信度 {(Number(record.confidence || 0) * 100).toFixed(0)}%</div>
          <div>
            支持 {record.support_count} / 反例 {record.contradiction_count}
          </div>
        </div>
      </div>

      {evidence.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {evidence.slice(0, 4).map((item, index) => {
            const path = evidencePathLabel(item.path ?? item.file ?? item.source);
            return (
              <Badge key={`${path}-${index}`} tone="purple" className="max-w-full truncate">
                <ExternalLink className="mr-1 h-3 w-3" />
                {path || `证据 ${index + 1}`}
              </Badge>
            );
          })}
        </div>
      ) : null}

      {pending ? (
        <div className="mt-4 space-y-3">
          <textarea
            value={note}
            onChange={(event) => onNote(event.target.value)}
            placeholder="可选：写下确认、驳回、归档或降级原因"
            className="min-h-20 w-full resize-y rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-700"
          />
          <div className="flex flex-wrap gap-2">
            {canApprove ? (
              <Button variant="primary" className="gap-2" disabled={busy} onClick={() => onAction("approve")}>
                <Check className="h-4 w-4" />
                确认为永久策略
              </Button>
            ) : (
              <Badge tone="neutral">不作为永久规则</Badge>
            )}
            <Button variant="danger" className="gap-2" disabled={busy} onClick={() => onAction("reject")}>
              <X className="h-4 w-4" />
              驳回
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => onAction("archive")}>
              归档
            </Button>
            <Button variant="ghost" className="gap-2" disabled={busy} onClick={() => onAction("demote")}>
              <RotateCcw className="h-4 w-4" />
              降为候选
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function canApprovePermanent(record: LongMemoryRecord) {
  if (record.can_promote_permanent === false) return false;
  return record.domain !== "fund" && record.memory_type !== "fund_profile_memory";
}

function statusTone(status: string): Tone {
  if (status === "permanent") return "success";
  if (status === "strategic") return "warning";
  if (status === "rejected") return "danger";
  if (status === "archived") return "neutral";
  return "info";
}
