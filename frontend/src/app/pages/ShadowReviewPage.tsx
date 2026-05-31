import { AlertTriangle, CheckCircle2, CircleDot, Eye, FileWarning, ShieldCheck } from "lucide-react";
import type { ShadowReviewItem, ShadowReviewPagePayload, Tone } from "../../lib/types";
import { Badge, Card, EmptyState, MetricCard, SectionTitle } from "../../components/ui";
import { asNumber, text } from "../../lib/format";

const statusCopy: Record<string, { label: string; body: string; tone: Tone }> = {
  missing: { label: "Missing", body: "No official or shadow review artifacts are available for this date.", tone: "neutral" },
  not_run: { label: "Not run", body: "Official advice exists, but shadow action tickets have not been generated.", tone: "warning" },
  running: { label: "Running", body: "Shadow review is running; this page only displays readable artifacts.", tone: "info" },
  ready: { label: "Ready", body: "Official advice, shadow tickets, retrieval packs, and debate traces are readable.", tone: "success" },
  partial: { label: "Partial", body: "Some shadow artifacts are missing; only recoverable read-only content is shown.", tone: "warning" },
  degraded: { label: "Degraded", body: "Some shadow artifacts are degraded or invalid, but recoverable content is shown.", tone: "danger" },
  failed: { label: "Failed", body: "Shadow review cannot recover comparable items. Check artifact status.", tone: "danger" }
};

const categoryTone: Record<string, Tone> = {
  same: "success",
  changed: "warning",
  new_shadow_only: "info",
  legacy_only: "neutral",
  missing: "neutral",
  error: "danger"
};

export function ShadowReviewPage({ shadowReview }: { shadowReview: ShadowReviewPagePayload }) {
  const copy = statusCopy[shadowReview.status] ?? statusCopy.missing;
  const summary = shadowReview.summary;
  const agreement = summary.agreementRate == null ? "N/A" : `${(asNumber(summary.agreementRate) * 100).toFixed(0)}%`;
  const missing = shadowReview.artifacts.missing ?? [];

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={copy.tone}>{copy.label}</Badge>
            <Badge tone="neutral" className="gap-1">
              <Eye className="h-3 w-3" />
              display-only
            </Badge>
            <Badge tone="neutral" className="gap-1">
              <ShieldCheck className="h-3 w-3" />
              non-executable
            </Badge>
          </div>
          <h2 className="mt-5 text-2xl font-black text-slate-50">{shadowReview.selectedDate}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-400">{copy.body}</p>
          <div className="mt-5 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-xs leading-6 text-slate-400">
            <div>generatedAt: {shadowReview.generatedAt || "N/A"}</div>
            <div>executionDisabled: {String(shadowReview.guardrails.executionDisabled)}</div>
            <div>affectsPortfolio: {String(shadowReview.guardrails.affectsPortfolio)}</div>
            <div>affectsLongMemoryPromotion: {String(shadowReview.guardrails.affectsLongMemoryPromotion)}</div>
          </div>
        </Card>

        <div className="col-span-7 grid grid-cols-3 gap-4">
          <MetricCard title="Official" value={String(summary.legacyCount)} body="legacy validated advice actions" tone="accent" />
          <MetricCard title="Shadow" value={String(summary.shadowCount)} body="shadow action tickets" tone="info" />
          <MetricCard title="Comparable" value={String(summary.comparableCount)} body={`agreement ${agreement}`} tone="success" />
          <MetricCard title="Changed" value={String(summary.changedCount)} body="official and shadow action labels differ" tone={summary.changedCount ? "warning" : "neutral"} />
          <MetricCard title="High Risk" value={String(summary.highRiskDiffCount ?? 0)} body="changed items with hard guardrail blocks" tone={summary.highRiskDiffCount ? "danger" : "neutral"} />
          <MetricCard title="Missing" value={String(missing.length)} body="missing, invalid, or not generated artifacts" tone={missing.length ? "warning" : "success"} />
        </div>
      </section>

      <section className="grid grid-cols-12 gap-4">
        <Card className="col-span-5 p-4">
          <SectionTitle title="Artifact Status" meta={shadowReview.artifacts.evalReportPath ?? ""} />
          <div className="space-y-2">
            {Object.entries(shadowReview.artifacts.states ?? {}).map(([kind, state]) => (
              <div key={kind} className="flex items-center justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
                <span className="truncate text-slate-400">{kind}</span>
                <Badge tone={state === "ready" ? "success" : state === "not_run" ? "neutral" : "warning"}>{state}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-7 p-4">
          <SectionTitle title="Missing Or Degraded Notes" />
          {missing.length ? (
            <div className="space-y-2">
              {missing.slice(0, 8).map((item) => (
                <div key={`${item.kind}-${item.path}-${item.reason}`} className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={item.reason === "invalid_json" ? "danger" : "warning"} className="gap-1">
                      <FileWarning className="h-3 w-3" />
                      {item.kind}
                    </Badge>
                    <span className="text-xs text-slate-500">{item.reason}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{item.message}</p>
                  {item.path ? <div className="mt-1 truncate text-xs text-slate-600">{item.path}</div> : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No missing artifact" body="The DTO did not report missing, invalid, or degraded review artifacts." />
          )}
        </Card>
      </section>

      <Card className="p-4">
        <SectionTitle title="Read-Only Ticket Comparison" meta={`${shadowReview.items.length} items`} />
        {shadowReview.items.length ? (
          <div className="space-y-3">
            {shadowReview.items.map((item) => (
              <ShadowReviewCard key={item.reviewId} item={item} />
            ))}
          </div>
        ) : (
          <EmptyState title="No comparable shadow ticket" body="This page does not synthesize review items from snapshots or unrelated artifacts." />
        )}
      </Card>
    </div>
  );
}

function ShadowReviewCard({ item }: { item: ShadowReviewItem }) {
  const notes = Array.isArray(item.diff?.notes) ? item.diff.notes : [];
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-bold text-slate-100">{item.displayLabel || item.fundCode}</h3>
            <Badge tone={categoryTone[item.category] ?? "neutral"}>{item.category}</Badge>
            <Badge tone={item.severity === "high" ? "danger" : item.severity === "medium" ? "warning" : "neutral"}>{item.severity}</Badge>
            <Badge tone="neutral">display-only</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">{text(item.display?.primaryText, "No display summary")}</p>
        </div>
        {item.diff?.actionChanged ? <AlertTriangle className="h-5 w-5 shrink-0 text-amber-300" /> : <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-300" />}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <CompareBlock title="Official" payload={item.legacy} />
        <CompareBlock title="Shadow" payload={item.shadow} />
      </div>

      <div className="mt-4 grid grid-cols-12 gap-3">
        <InfoBlock className="col-span-4" title="Guardrails" value={guardrailText(item.guardrails)} />
        <InfoBlock className="col-span-4" title="Retrieval" value={retrievalText(item.retrieval)} />
        <InfoBlock className="col-span-4" title="Debate" value={debateText(item.debate)} />
      </div>

      <div className="mt-3 grid grid-cols-12 gap-3">
        <InfoBlock className="col-span-4" title="Soft Policies" value={policyText(item.softPolicies)} />
        <InfoBlock className="col-span-4" title="Skills" value={skillText(item.skillRefs, item.skillOutputs)} />
        <InfoBlock className="col-span-4" title="Outcomes" value={outcomeText(item.outcomeEvents)} />
      </div>

      {notes.length ? (
        <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-400">
          {notes.slice(0, 4).map((note) => (
            <li key={note} className="flex gap-2">
              <CircleDot className="mt-1 h-4 w-4 shrink-0 text-cyan-300" />
              {note}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function CompareBlock({ title, payload }: { title: string; payload?: Record<string, unknown> | null }) {
  if (!payload) {
    return (
      <div className="rounded-md border border-slate-800 bg-slate-950 p-3">
        <div className="text-xs font-bold text-slate-500">{title}</div>
        <p className="mt-2 text-sm text-slate-500">No record</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950 p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-bold text-slate-500">{title}</div>
        <Badge tone="info">{text(payload.action, "none")}</Badge>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-slate-400">{text(payload.thesis, "No thesis")}</p>
      <div className="mt-2 text-xs text-slate-600">confidence: {String(payload.confidence ?? 0)}</div>
    </div>
  );
}

function InfoBlock({ title, value, className }: { title: string; value: string; className?: string }) {
  return (
    <div className={`rounded-md border border-slate-800 bg-slate-950 p-3 ${className ?? ""}`}>
      <div className="text-xs font-bold text-slate-500">{title}</div>
      <div className="mt-2 text-sm text-slate-300">{value}</div>
    </div>
  );
}

function guardrailText(value?: Record<string, unknown>) {
  if (!value) return "not_run";
  return `block=${value.block ?? 0}; adjust=${value.adjust ?? 0}; pass=${value.pass ?? 0}`;
}

function retrievalText(value?: Record<string, unknown> | null) {
  if (!value) return "not_run";
  return `trace=${value.traceCompletenessRate ?? "N/A"}; missing=${value.missingDataCount ?? 0}; rag=${value.ragTraceCount ?? 0}`;
}

function debateText(value?: Record<string, unknown> | null) {
  if (!value) return "not_run";
  return `verdict=${value.verdict || "N/A"}; writesTicketFile=${String(value.writesTicketFile ?? false)}`;
}

function policyText(value?: Array<Record<string, unknown>>) {
  if (!value?.length) return "none";
  const first = value[0];
  return `${value.length}; ${text(first.policy_id ?? first.policyId ?? first.effect_type, "policy note")}`;
}

function skillText(refs?: Array<Record<string, unknown>>, outputs?: Array<Record<string, unknown>>) {
  const refCount = refs?.length ?? 0;
  const outputCount = outputs?.length ?? 0;
  if (!refCount && !outputCount) return "none";
  const first = refs?.[0] ?? outputs?.[0] ?? {};
  return `refs=${refCount}; outputs=${outputCount}; ${text(first.skill_id ?? first.skillId ?? first.output_type, "skill trace")}`;
}

function outcomeText(value?: Array<Record<string, unknown>>) {
  if (!value?.length) return "none";
  const scored = value.filter((item) => item.scoring_status === "scored").length;
  const pending = value.filter((item) => item.scoring_status === "pending").length;
  const first = value[0];
  return `${value.length}; scored=${scored}; pending=${pending}; ${text(first.outcome_label, "outcome")}`;
}
