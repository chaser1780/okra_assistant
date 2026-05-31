# Shadow Review API Contract

Status: implemented partial. The read-only API and Workbench page are live for
shadow review; this contract is now the current implementation reference.

This document defines the proposed read-only Workbench API surface for
old-versus-new shadow review. It is intentionally display-only. Shadow review
artifacts must never create executable trade actions, update portfolio state,
approve long-memory records, or label advice accuracy.

## Goals

- Give the Workbench a stable DTO instead of binding directly to raw shadow
  artifacts.
- Compare legacy advice and shadow candidate outputs in one read-only review
  surface.
- Make missing shadow artifacts explicit and non-fatal.
- Preserve current page contracts and `/api/snapshot` compatibility.
- Keep execution-only evidence out of normal strategy review unless explicitly
  requested by a separate execution review flow.

## Routes

Primary page route:

- `GET /api/shadow-review?date=YYYY-MM-DD`

Compatibility alias, if needed:

- `GET /api/workbench/shadow-review?date=YYYY-MM-DD`

Optional detail route, not implemented yet:

- `GET /api/shadow-review/<review_id>?date=YYYY-MM-DD`

These routes should use the normal API envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {
    "page": "shadow-review",
    "selected_date": "2026-05-24",
    "generated_at": "2026-05-24T22:00:00+08:00",
    "version": "v1"
  }
}
```

## Response DTO

```ts
type ShadowReviewPageDto = {
  selectedDate: string;
  status: "missing" | "not_run" | "running" | "ready" | "partial" | "degraded" | "failed";
  generatedAt: string;
  nonExecutable: true;
  displayOnly: true;

  summary: {
    legacyCount: number;
    shadowCount: number;
    comparableCount: number;
    changedCount: number;
    agreementRate?: number;
    highRiskDiffCount?: number;
  };

  artifacts: {
    legacyAdvicePath?: string;
    shadowAdvicePath?: string;
    shadowTracePath?: string;
    retrievalPackPath?: string;
    evalReportPath?: string;
    policyRegistryPath?: string;
    strategySkillRegistryPath?: string;
    exists: {
      legacyAdvice: boolean;
      shadowAdvice: boolean;
      shadowTrace: boolean;
      retrievalPack: boolean;
      evalReport: boolean;
      outcomeEvents: boolean;
      adaptivePolicies: boolean;
      strategySkills: boolean;
    };
    states?: Record<string, string>;
    missing: Array<{
      kind: string;
      path?: string;
      reason: "missing_source" | "not_generated" | "invalid_json" | "empty" | "unsupported_version" | "boundary_violation";
      message: string;
    }>;
  };

  items: ShadowReviewItemDto[];

  runtime: {
    runId?: string;
    status?: string;
    currentStep?: string;
    currentAgent?: string;
    startedAt?: string;
    endedAt?: string;
    lastError?: string;
  };

  guardrails: {
    nonExecutable: true;
    executionDisabled: true;
    affectsPortfolio: false;
    affectsAdviceAccuracy: false;
    affectsLongMemoryPromotion: false;
    allowExecutionEvidence: false;
  };
};
```

Item DTO:

```ts
type ShadowReviewItemDto = {
  reviewId: string;
  fundCode: string;
  fundName: string;
  category: "same" | "changed" | "new_shadow_only" | "legacy_only" | "missing" | "error";
  severity: "info" | "low" | "medium" | "high";
  displayLabel: string;
  nonExecutable: true;
  displayOnly: true;

  legacy?: {
    action?: string;
    confidence?: number;
    thesis?: string;
    risks?: string[];
    evidence?: string[];
    sourcePath?: string;
  };

  shadow?: {
    action?: string;
    confidence?: number;
    thesis?: string;
    risks?: string[];
    evidence?: string[];
    traceId?: string;
    sourcePath?: string;
    fallbackReason?: string;
    missingData?: Record<string, unknown>[];
  };

  diff: {
    actionChanged: boolean;
    confidenceDelta?: number;
    riskChanged: boolean;
    evidenceChanged: boolean;
    notes: string[];
  };

  display: {
    primaryText: string;
    secondaryText?: string;
    badges: Array<{
      label: string;
      tone: "neutral" | "info" | "success" | "warning" | "danger";
    }>;
  };

  guardrails?: Record<string, unknown>;
  softPolicies?: Record<string, unknown>[];
  skillRefs?: Record<string, unknown>[];
  skillOutputs?: Record<string, unknown>[];
  retrieval?: {
    packId?: string;
    traceCompletenessRate?: number;
    missingDataCount?: number;
    ragTraceCount?: number;
  };
  debate?: {
    debateId?: string;
    verdict?: string;
    degraded?: boolean;
    writesTicketFile?: false;
    proposedPatch?: Record<string, unknown>;
  };
  outcomeEvents?: Record<string, unknown>[];
};
```

## Artifact Sources

Initial implementation can read:

- `db/validated_advice/<date>.json`
- `db/action_tickets/<date>.json`
- `db/action_debates/<date>.json`
- `db/retrieval_packs/<date>.json`
- `db/outcome_events/<base_date>__<horizon>.json`
- `db/strategy_memory/policies.json`
- `db/strategy_skills/registry.json`
- optional graph runtime metadata under the future shadow run directory

The API should normalize those artifacts into DTOs. The frontend must not bind
directly to raw JSON internals because early artifact schemas will still evolve.

## Missing Artifact Behavior

Missing shadow artifacts should return `200 ok` with `status="missing"` or
`status="not_run"`, not `404`, when the route itself is valid.

Use `404 not_found` only when the endpoint path or `review_id` is unknown.

Recommended mapping:

- Legacy advice exists, shadow artifact missing: `status="not_run"`,
  `items=[]`, `artifacts.missing[]` explains the missing shadow source.
- Shadow artifact exists but invalid JSON: `status="degraded"` or
  `status="failed"` depending on whether any comparable items can be recovered.
- Shadow artifact has invalid `write_scope` or `non_executable=false`:
  `status="failed"` and no display item is synthesized from that artifact.
- Shadow trace missing but shadow summary exists: `status="partial"`.
- Both legacy and shadow artifacts missing: `status="missing"` with frontend
  empty state.
- Runtime file shows active run: `status="running"` with runtime fields
  populated.

## Error Behavior

- Empty or malformed date: `400 bad_request`.
- Unknown endpoint: `404 not_found`.
- Unexpected parser or filesystem exception: `500 internal_error`, with
  `details.path` when available.
- Do not expose raw stack traces in `error.error_message`.

## Frontend Empty States

The frontend should distinguish these states:

- `missing`: `暂无可对比的影子评审数据。`
- `not_run`: `当前日期尚未运行 shadow review。`
- `running`: `Shadow review 正在生成，稍后刷新。`
- `partial`: `部分 shadow artifact 缺失，当前仅展示可恢复内容。`
- `degraded`: `Shadow review 可展示，但部分证据或 trace 不完整。`
- `failed`: `Shadow review 生成失败，请在系统页查看运行错误。`

For `items=[]`, the UI should not show a broken table. It should show a
page-level empty state plus artifact status details.

## Non-Executable Display Contract

Every response and item must carry a non-execution marker:

```json
{
  "nonExecutable": true,
  "displayOnly": true
}
```

Runtime contract:

- page-level and item-level `nonExecutable` and `displayOnly` are strict true
  literals;
- guardrail fields such as `executionDisabled=true` and
  `affectsPortfolio=false` are strict literals in API DTO and frontend schema;
- frontend schema must not silently coerce `false` into `true`;
- service-level artifact readers must reject boundary-invalid shadow artifacts
  before building comparison rows.

Guardrails:

- No execute, buy, sell, apply, or confirm command should be rendered from this
  payload.
- Shadow review actions are labels only, not trade intents.
- Shadow review must not call `/api/execution-sync/trade`,
  `/api/execution-sync/conversion`, `/api/execution-sync/reconcile/apply`, or
  `/api/long-memory/action`.
- Future user notes should use a separate review-note endpoint and must not
  promote memory or mutate portfolio state.

## Compatibility With Current Workbench

- Add this as a new page route; do not change existing `/api/today`,
  `/api/research`, `/api/review`, or `/api/system` DTOs.
- Keep `app/api_contracts.py` models additive and `extra="allow"`.
- Keep frontend Zod schemas `.passthrough()` for nested shadow fields, but not
  for safety boundary literals.
- Do not wrap `/api/snapshot`; it remains legacy raw payload.
- If fallback is needed, frontend may show an empty shadow review from
  `/api/system.system.ragRuntime` and runtime metadata, but should not
  synthesize review items from unrelated artifacts.

## Implementation Checklist For Phase 7

- Add Pydantic DTOs in `app/api_contracts.py` only after the artifact shape is
  stable.
- Add read-only service assembly in `app/web_api_services.py` or a small
  dedicated service module.
- Add frontend schema in `frontend/src/lib/schemas.ts`.
- Add Workbench query helper rather than raw `request()` calls.
- Add tests for missing files, invalid JSON, ready payload, and non-executable
  markers.
- Add no execution buttons in UI review.
