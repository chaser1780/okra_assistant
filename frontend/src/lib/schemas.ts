import { z } from "zod";

const toneSchema = z.enum(["neutral", "accent", "success", "warning", "danger", "info", "purple", "magenta", "amber"]);

const unknownRecordSchema = z.record(z.string(), z.unknown());
const numberRecordSchema = z.record(z.string(), z.coerce.number().catch(0)).catch({});
const financialNumberSchema = z.preprocess((value) => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}, z.number().nullable());
const apiErrorSchema = z.object({
  error_code: z.string(),
  error_message: z.string(),
  retryable: z.boolean().optional(),
  details: unknownRecordSchema.optional()
}).passthrough();

const apiMetaSchema = z.object({
  page: z.string().nullable().optional(),
  selected_date: z.string().nullable().optional(),
  generated_at: z.string().nullable().optional(),
  version: z.string().optional()
}).passthrough();
const chartPointSchema = z.object({ date: z.string(), value: financialNumberSchema }).passthrough();
const metricSchema = z.object({
  title: z.string(),
  value: z.string(),
  body: z.string(),
  tone: toneSchema.optional()
}).passthrough();

const portfolioItemSchema = z.object({
  fundCode: z.string(),
  fundName: z.string(),
  amount: financialNumberSchema,
  amountText: z.string(),
  weight: z.union([z.number(), z.string()]),
  weightText: z.string(),
  risk: z.string(),
  action: z.string(),
  role: z.string(),
  styleGroup: z.string(),
  holdingPnl: financialNumberSchema,
  holdingPnlText: z.string(),
  holdingReturnPct: financialNumberSchema,
  holdingReturnPctText: z.string(),
  officialDailyPnl: financialNumberSchema,
  officialDailyPnlText: z.string().catch("暂无"),
  officialDailyPnlDate: z.string().catch(""),
  officialDailyPnlStatus: z.string().catch(""),
  officialDailyPnlReason: z.string().catch(""),
  costBasis: financialNumberSchema,
  costBasisText: z.string(),
  holdingUnits: financialNumberSchema,
  lastNav: financialNumberSchema,
  lastNavDate: z.string(),
  allowTrade: z.boolean().catch(false),
  fixedDailyBuyAmount: financialNumberSchema,
  allowExtraBuys: z.boolean().catch(false)
}).passthrough();

const allocationRowSchema = z.object({
  name: z.string(),
  value: financialNumberSchema,
  valueText: z.string(),
  weight: financialNumberSchema,
  weightText: z.string()
}).passthrough();

const allocationHistoryPointSchema = z.object({
  date: z.string(),
  values: z.array(z.object({ name: z.string(), weight: financialNumberSchema })).catch([])
}).passthrough();
const portfolioRiskSnapshotSchema = z.object({
  currentDrawdownPct: financialNumberSchema,
  maxDrawdownPct: financialNumberSchema,
  cashWeightPct: financialNumberSchema,
  topHoldingWeightPct: financialNumberSchema,
  topStyleWeightPct: financialNumberSchema,
  asOfDate: z.string().catch("")
}).passthrough();
const portfolioRiskPointSchema = z.object({
  fundCode: z.string(),
  fundName: z.string(),
  weightPct: financialNumberSchema,
  anomalyScore: financialNumberSchema,
  holdingPnl: financialNumberSchema,
  styleGroup: z.string()
}).passthrough();

export const dashboardSchema = z.object({
  meta: z.string(),
  metrics: z.array(metricSchema),
  focus_text: z.string(),
  market_text: z.string(),
  change_text: z.string(),
  summary_text: z.string(),
  detail_text: z.string(),
  primary_fund_code: z.string(),
  committee_text: z.string(),
  provider_text: z.string()
}).passthrough();

export const portfolioSchema = z.object({
  asOfDate: z.string(),
  totalValue: financialNumberSchema,
  totalValueText: z.string(),
  cash: financialNumberSchema,
  cashText: z.string(),
  holdingPnl: financialNumberSchema,
  holdingPnlText: z.string(),
  styleAllocation: z.array(allocationRowSchema),
  roleAllocation: z.array(allocationRowSchema),
  profitLeaders: z.array(portfolioItemSchema),
  lossLeaders: z.array(portfolioItemSchema),
  history: z.object({
    totalValue: z.array(chartPointSchema),
    holdingPnl: z.array(chartPointSchema),
    holdingReturnPct: z.array(chartPointSchema),
    totalValueNormalized: z.array(chartPointSchema).optional(),
    dailyReturnPct: z.array(chartPointSchema).optional(),
    drawdownPct: z.array(chartPointSchema).optional(),
    styleAllocationHistory: z.array(allocationHistoryPointSchema).optional(),
    roleAllocationHistory: z.array(allocationHistoryPointSchema).optional()
  }).passthrough(),
  riskSnapshot: portfolioRiskSnapshotSchema.optional(),
  riskScatter: z.array(portfolioRiskPointSchema).optional(),
  benchmark: z.object({
    status: z.string(),
    name: z.string().optional(),
    key: z.string().optional(),
    normalized: z.array(chartPointSchema),
    excessReturnPct: z.array(chartPointSchema)
  }).passthrough().optional(),
  items: z.array(portfolioItemSchema)
}).passthrough();

export const researchSchema = z.object({
  meta: z.string(),
  metrics: z.array(metricSchema),
  rows: z.array(unknownRecordSchema),
  fund_cards: z.array(
    z.object({
      ticketId: z.string().catch(""),
      fundCode: z.string().catch(""),
      fundName: z.string().catch(""),
      selectedDate: z.string().catch(""),
      section: z.string().catch(""),
      strategyBucket: z.string().catch(""),
      action: z.string().catch("hold"),
      actionLabel: z.string().catch("观察"),
      amount: financialNumberSchema,
      amountText: z.string().catch("不可用"),
      priority: z.number().catch(0),
      confidence: z.number().catch(0),
      confidenceText: z.string().catch("暂无"),
      thesis: z.string().catch("暂无建议理由"),
      evidence: z.array(z.string()).catch([]),
      risks: z.array(z.string()).catch([]),
      agentSupport: z.array(z.string()).catch([]),
      sourceSignalIds: z.array(z.string()).catch([]),
      opposingSignalIds: z.array(z.string()).catch([]),
      policyRuleHits: z.array(z.string()).catch([]),
      constraintHits: z.array(z.string()).catch([]),
      consensusText: z.string().catch("暂无"),
      hasConflict: z.boolean().catch(false),
      isActionable: z.boolean().catch(false),
      portfolio: unknownRecordSchema.catch({}),
      market: unknownRecordSchema.catch({}),
      news: unknownRecordSchema.catch({}),
      profile: unknownRecordSchema.catch({}),
      evidenceRefs: z.array(unknownRecordSchema).catch([])
    }).passthrough()
  ).catch([])
}).passthrough();

export const realtimeSchema = z.object({
  meta: z.string(),
  metrics: z.array(metricSchema),
  items: z.array(unknownRecordSchema),
  summary_text: z.string()
}).passthrough();

export const reviewSchema = z.object({
  meta: z.string(),
  metrics: z.array(metricSchema),
  summary_text: z.string(),
  detail_text: z.string(),
  core_lines: z.array(z.string()),
  strategic_lines: z.array(z.string()),
  replay_lines: z.array(z.string()),
  fund_memory_lines: z.array(z.string()).optional(),
  market_memory_lines: z.array(z.string()).optional(),
  execution_memory_lines: z.array(z.string()).optional(),
  pending_memory_lines: z.array(z.string()).optional(),
  trust: z.object({
    reportDate: z.string().catch(""),
    manifestPath: z.string().catch(""),
    manifestExists: z.boolean().catch(false),
    mode: z.string().catch("blocked"),
    learningEligible: z.boolean().catch(false),
    trustedForLearning: z.boolean().catch(false),
    reasonCodes: z.array(z.string()).catch([]),
    latestReplayAudit: unknownRecordSchema.optional(),
    latestReplayAuditPath: z.string().optional(),
    latestLearningAuditSummary: unknownRecordSchema.optional(),
    latestLearningAuditPath: z.string().optional()
  }).passthrough().optional()
}).passthrough();

const longMemoryRecordSchema = z.object({
  memory_id: z.string(),
  memory_type: z.string(),
  domain: z.string(),
  entity_key: z.string(),
  title: z.string(),
  text: z.string(),
  status: z.string(),
  priority: z.string().optional(),
  confidence: z.number().catch(0),
  support_count: z.number().catch(0),
  contradiction_count: z.number().catch(0),
  last_supported_at: z.string().optional(),
  last_contradicted_at: z.string().optional(),
  approved_by: z.string().optional(),
  approved_at: z.string().optional(),
  can_promote_permanent: z.boolean().optional(),
  source: z.string().optional(),
  metadata: unknownRecordSchema.optional(),
  evidence_refs: z.array(unknownRecordSchema).optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional()
}).passthrough();

export const longMemorySchema = z.object({
  updatedAt: z.string(),
  records: z.array(longMemoryRecordSchema),
  pending: z.array(longMemoryRecordSchema),
  fund: z.array(longMemoryRecordSchema),
  market: z.array(longMemoryRecordSchema),
  execution: z.array(longMemoryRecordSchema),
  portfolio: z.array(longMemoryRecordSchema),
  counts: z.object({
    fund: z.number().optional(),
    market: z.number().optional(),
    execution: z.number().optional(),
    portfolio: z.number().optional(),
    pending: z.number().optional(),
    total: z.number().optional()
  }).passthrough()
}).passthrough();

const fundAnalysisAgentCardSchema = z.object({
  agent_name: z.string(),
  stage: z.string(),
  stageLabel: z.string(),
  stageDescription: z.string().catch(""),
  status: z.string().catch(""),
  summary: z.string().catch(""),
  confidence: z.number().catch(0),
  dependsOn: z.array(z.string()).catch([]),
  consumers: z.array(z.string()).catch([]),
  isCommitteeCore: z.boolean().catch(false),
  portfolioView: unknownRecordSchema.catch({}),
  fundViews: z.array(unknownRecordSchema).catch([]),
  signalCards: z.array(unknownRecordSchema).catch([]),
  decisionCards: z.array(unknownRecordSchema).catch([])
}).passthrough();

const fundAnalysisDetailSchema = z.object({
  agentSummary: unknownRecordSchema.catch({}),
  stageSummary: unknownRecordSchema.catch({}),
  agentCards: z.array(fundAnalysisAgentCardSchema).catch([])
}).passthrough();

const fundHistorySchema = z.object({
  nav: z.array(chartPointSchema).catch([]),
  navNormalized: z.array(chartPointSchema).catch([]),
  dayChangePct: z.array(chartPointSchema).catch([]),
  weekChangePct: z.array(chartPointSchema).catch([]),
  monthChangePct: z.array(chartPointSchema).catch([]),
  proxyNormalized: z.array(chartPointSchema).catch([]),
  proxyDayChangePct: z.array(chartPointSchema).catch([]),
  estimateChangePct: z.array(chartPointSchema).catch([]),
  holdingValue: z.array(chartPointSchema).catch([]),
  holdingPnl: z.array(chartPointSchema).catch([]),
  holdingReturnPct: z.array(chartPointSchema).catch([]),
  holdingUnits: z.array(chartPointSchema).catch([]),
  benchmarkNormalized: z.array(chartPointSchema).catch([]),
  benchmarkDayChangePct: z.array(chartPointSchema).catch([]),
  drawdownPct: z.array(chartPointSchema).catch([]),
  excessReturnPct: z.array(chartPointSchema).catch([]),
  decisionMarkers: z.array(z.object({
    date: z.string(),
    type: z.string(),
    label: z.string(),
    amount: financialNumberSchema.optional(),
    source: z.string()
  }).passthrough()).catch([])
}).passthrough();

const tradeMarkerSchema = z.object({
  date: z.string(),
  action: z.string(),
  amount: financialNumberSchema,
  amountText: z.string(),
  fundCode: z.string(),
  fundName: z.string(),
  source: z.string()
}).passthrough();

const fundLongMemorySchema = z.object({
  fund: z.array(longMemoryRecordSchema).catch([]),
  execution: z.array(longMemoryRecordSchema).catch([]),
  rules: z.array(longMemoryRecordSchema).catch([])
}).passthrough();

export const fundDetailSchema = z.object({
  fundCode: z.string(),
  fundName: z.string(),
  selectedDate: z.string(),
  range: z.string(),
  portfolio: portfolioItemSchema.partial().passthrough().catch({}),
  realtime: unknownRecordSchema.catch({}),
  research: unknownRecordSchema.catch({}),
  analysisDetail: fundAnalysisDetailSchema,
  history: fundHistorySchema,
  performance: z.object({
    stageReturn: z.string(),
    navSource: z.string().catch(""),
    proxySource: z.string().catch(""),
    proxyName: z.string().catch(""),
    benchmarkName: z.string().optional(),
    benchmarkKey: z.string().optional(),
    benchmarkStatus: z.string().optional()
  }).passthrough(),
  tradeMarkers: z.array(tradeMarkerSchema).catch([]),
  longMemory: fundLongMemorySchema
}).passthrough();

export const dailyFirstOpenSchema = z.object({
  decision: unknownRecordSchema,
  analysis: unknownRecordSchema,
  updates: unknownRecordSchema.optional(),
  meta: unknownRecordSchema.optional(),
  brief: z.string(),
  runStatus: z.union([z.string(), z.boolean(), z.number()]).optional(),
  analysisQuality: z.union([z.string(), z.boolean(), z.number()]).optional(),
  memoryEligible: z.union([z.string(), z.boolean(), z.number()]).optional()
}).passthrough();

const ragRuntimeSettingsSchema = unknownRecordSchema.catch({});

export const ragRuntimeSchema = z.object({
  generatedAt: z.string().catch(""),
  enabled: z.boolean().catch(false),
  defaultProfile: z.string().catch(""),
  fallbackToLegacy: z.boolean().catch(true),
  traceEnabled: z.boolean().catch(false),
  dbPath: z.string().catch(""),
  dbExists: z.boolean().catch(false),
  statusError: z.string().optional(),
  counts: numberRecordSchema,
  sourceCounts: numberRecordSchema,
  embeddingStatus: numberRecordSchema,
  agentShadow: ragRuntimeSettingsSchema,
  agentDefault: ragRuntimeSettingsSchema,
  profileEvidence: ragRuntimeSettingsSchema,
  embedding: ragRuntimeSettingsSchema,
  vectorStore: ragRuntimeSettingsSchema,
  latestEval: unknownRecordSchema.catch({}),
  latestTraces: z.array(unknownRecordSchema).catch([]),
  latestIngestRuns: z.array(unknownRecordSchema).catch([]),
  activeManifests: z.array(unknownRecordSchema).catch([])
}).passthrough();

export const systemSchema = z.object({
  sourceHealth: unknownRecordSchema.optional(),
  preflightStatus: z.string().optional(),
  settings: unknownRecordSchema.optional(),
  llmRuntime: unknownRecordSchema.optional(),
  todayAnalysisRuntime: unknownRecordSchema.optional(),
  longMemoryRuntime: unknownRecordSchema.optional(),
  agentRuntime: unknownRecordSchema.optional(),
  ragRuntime: ragRuntimeSchema.optional(),
  rag: ragRuntimeSchema.optional(),
  todayAnalysis: unknownRecordSchema.optional(),
  dailyFirstOpen: unknownRecordSchema.optional()
}).passthrough();

export const executionSyncSchema = z.object({
  updatedAt: z.string(),
  pending: z.array(unknownRecordSchema),
  trades: z.array(unknownRecordSchema),
  deviations: z.array(unknownRecordSchema),
  reconciliationReports: z.array(unknownRecordSchema),
  counts: z.object({
    pending: z.number().optional(),
    trades: z.number().optional(),
    deviations: z.number().optional(),
    reports: z.number().optional()
  }).passthrough()
}).passthrough();

const screenshotPreviewRowSchema = z.object({
  display_name: z.string().catch(""),
  fund_code: z.string().catch(""),
  fund_name: z.string().catch(""),
  matched_fund_code: z.string().catch(""),
  matched_fund_name: z.string().catch(""),
  current_value: financialNumberSchema,
  holding_pnl: financialNumberSchema,
  holding_return_pct: financialNumberSchema,
  page_index: financialNumberSchema,
  row_index: financialNumberSchema
}).passthrough();

const fundSourceLinkSchema = z.object({
  label: z.string().catch("来源"),
  url: z.string().catch("")
}).passthrough();

function firstCandidateText(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (value !== null && value !== undefined && String(value).trim()) return String(value).trim();
  }
  return "";
}

function normalizeSourceLinks(source: Record<string, unknown>) {
  const links: Array<{ label: string; url: string }> = [];
  const add = (label: string, url: unknown) => {
    const normalizedUrl = String(url ?? "").trim();
    if (normalizedUrl && !links.some((item) => item.url === normalizedUrl)) links.push({ label, url: normalizedUrl });
  };
  if (Array.isArray(source.source_links)) {
    source.source_links.forEach((item, index) => {
      if (typeof item === "string") add(`来源 ${index + 1}`, item);
      else if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        add(firstCandidateText(record, ["label", "name", "source_name"]) || `来源 ${index + 1}`, record.url ?? record.source_url);
      }
    });
  }
  add(firstCandidateText(source, ["source_name"]) || "基金详情", source.source_url ?? source.url);
  add("搜索来源", source.search_source_url);
  return links;
}

export const fundLookupCandidateSchema = z.preprocess((value) => {
  if (!value || typeof value !== "object") return value;
  const source = value as Record<string, unknown>;
  return {
    ...source,
    fund_code: firstCandidateText(source, ["fund_code", "code"]),
    fund_name: firstCandidateText(source, ["fund_name", "official_name", "name"]),
    fund_type: firstCandidateText(source, ["fund_type", "type", "category"]),
    company_name: firstCandidateText(source, ["company_name", "fund_company", "company", "management_company"]),
    manager_name: firstCandidateText(source, ["manager_name", "fund_manager", "manager"]),
    latest_nav: source.latest_nav ?? source.nav ?? null,
    nav_date: firstCandidateText(source, ["nav_date", "latest_nav_date"]),
    source_name: firstCandidateText(source, ["source_name"]),
    source_url: firstCandidateText(source, ["source_url", "url"]),
    search_source_url: firstCandidateText(source, ["search_source_url"]),
    source_links: normalizeSourceLinks(source),
    match_score: source.match_score ?? null
  };
}, z.object({
  fund_code: z.string(),
  fund_name: z.string(),
  fund_type: z.string(),
  company_name: z.string(),
  manager_name: z.string(),
  latest_nav: z.union([z.number(), z.string()]).nullable(),
  nav_date: z.string(),
  source_name: z.string(),
  source_url: z.string(),
  search_source_url: z.string(),
  source_links: z.array(fundSourceLinkSchema),
  match_score: financialNumberSchema
}).passthrough());

export const fundLookupResponseSchema = z.object({
  query: z.string().catch(""),
  candidates: z.array(fundLookupCandidateSchema).catch([]),
  warnings: z.array(z.string()).catch([])
}).passthrough();

export const screenshotPreviewSchema = z.object({
  reconcile_id: z.string().catch(""),
  import_id: z.string().catch(""),
  provider: z.string().catch(""),
  generated_at: z.string().catch(""),
  sync_date: z.string().catch(""),
  source: z.string().catch(""),
  platform: z.string().catch(""),
  snapshot_date: z.string().catch(""),
  detected_holdings: z.array(screenshotPreviewRowSchema).catch([]),
  matched_items: z.array(screenshotPreviewRowSchema).catch([]),
  new_items: z.array(screenshotPreviewRowSchema).catch([]),
  unmatched_detected: z.array(screenshotPreviewRowSchema).catch([]),
  new_fund_candidates: z.array(screenshotPreviewRowSchema).catch([]),
  missing_items: z.array(screenshotPreviewRowSchema).catch([]),
  missing_portfolio_funds: z.array(screenshotPreviewRowSchema).catch([]),
  apply_ready: z.boolean().catch(false),
  preview_sha256: z.string().catch(""),
  portfolio_state_sha256: z.string().catch(""),
  warnings: z.array(z.string()).catch([]),
  vision_warnings: z.array(z.string()).catch([]),
  auto_parse_attempted: z.boolean().catch(false),
  auto_parse_ok: z.boolean().catch(false),
  auto_parse_error: z.string().catch("")
}).passthrough();

export const shellPayloadSchema = z.object({
  selectedDate: z.string(),
  dates: z.array(z.string()),
  summary: unknownRecordSchema,
  system: systemSchema
}).passthrough();

export const todayPageSchema = z.object({
  selectedDate: z.string(),
  dashboard: dashboardSchema,
  portfolio: portfolioSchema,
  research: researchSchema.catch({
    meta: "",
    metrics: [],
    rows: [],
    fund_cards: []
  }),
  longMemory: longMemorySchema,
  todayAnalysis: dailyFirstOpenSchema.optional(),
  dailyFirstOpen: dailyFirstOpenSchema,
  system: systemSchema
}).passthrough();

export const portfolioPageSchema = z.object({
  selectedDate: z.string(),
  portfolio: portfolioSchema
}).passthrough();

export const executionPageSchema = z.object({
  selectedDate: z.string(),
  executionSync: executionSyncSchema,
  portfolio: portfolioSchema
}).passthrough();

export const researchPageSchema = z.object({
  selectedDate: z.string(),
  research: researchSchema
}).passthrough();

export const intelligenceSchema = z.object({
  metrics: unknownRecordSchema.optional(),
  source_health: unknownRecordSchema.optional(),
  news_digest: unknownRecordSchema.optional(),
  sentiment_digest: unknownRecordSchema.optional(),
  important_news: z.array(unknownRecordSchema).optional(),
  regulatory_items: z.array(unknownRecordSchema).optional(),
  szse_items: z.array(unknownRecordSchema).optional(),
  related_news_by_fund: z.record(z.string(), z.array(unknownRecordSchema)).optional(),
  source_breakdown: z.union([unknownRecordSchema, z.array(unknownRecordSchema)]).optional(),
  event_risks: z.array(unknownRecordSchema).optional()
}).passthrough();

export const intelligencePageSchema = z.object({
  selectedDate: z.string(),
  intelligence: intelligenceSchema
}).passthrough();

export const realtimePageSchema = z.object({
  selectedDate: z.string(),
  realtime: realtimeSchema
}).passthrough();

export const reviewPageSchema = z.object({
  selectedDate: z.string(),
  review: reviewSchema,
  longMemory: longMemorySchema
}).passthrough();

const shadowReviewStatusSchema = z.enum(["missing", "not_run", "running", "ready", "partial", "degraded", "failed"]);

const shadowReviewBadgeSchema = z.object({
  label: z.string().catch(""),
  tone: z.string().catch("neutral")
}).passthrough();

const shadowReviewItemSchema = z.object({
  reviewId: z.string().catch(""),
  fundCode: z.string().catch(""),
  fundName: z.string().catch(""),
  category: z.string().catch("missing"),
  severity: z.string().catch("info"),
  displayLabel: z.string().catch(""),
  nonExecutable: z.literal(true),
  displayOnly: z.literal(true),
  legacy: unknownRecordSchema.nullable().optional(),
  shadow: unknownRecordSchema.nullable().optional(),
  diff: z.object({
    actionChanged: z.boolean().catch(false),
    confidenceDelta: z.number().nullable().optional(),
    riskChanged: z.boolean().optional(),
    evidenceChanged: z.boolean().optional(),
    notes: z.array(z.string()).catch([])
  }).passthrough(),
  display: z.object({
    primaryText: z.string().optional(),
    secondaryText: z.string().optional(),
    badges: z.array(shadowReviewBadgeSchema).catch([])
  }).passthrough(),
  guardrails: unknownRecordSchema.optional(),
  softPolicies: z.array(unknownRecordSchema).catch([]),
  skillRefs: z.array(unknownRecordSchema).catch([]),
  skillOutputs: z.array(unknownRecordSchema).catch([]),
  retrieval: unknownRecordSchema.nullable().optional(),
  debate: unknownRecordSchema.nullable().optional(),
  outcomeEvents: z.array(unknownRecordSchema).catch([])
}).passthrough();

const shadowReviewMissingArtifactSchema = z.object({
  kind: z.string().catch(""),
  path: z.string().nullable().optional(),
  reason: z.string().catch(""),
  message: z.string().catch("")
}).passthrough();

export const shadowReviewPageSchema = z.object({
  selectedDate: z.string(),
  status: shadowReviewStatusSchema.catch("missing"),
  generatedAt: z.string().catch(""),
  nonExecutable: z.literal(true),
  displayOnly: z.literal(true),
  summary: z.object({
    legacyCount: z.number().catch(0),
    shadowCount: z.number().catch(0),
    comparableCount: z.number().catch(0),
    changedCount: z.number().catch(0),
    agreementRate: z.number().nullable().optional(),
    highRiskDiffCount: z.number().catch(0)
  }).passthrough(),
  artifacts: z.object({
    legacyAdvicePath: z.string().nullable().optional(),
    shadowAdvicePath: z.string().nullable().optional(),
    shadowTracePath: z.string().nullable().optional(),
    evalReportPath: z.string().nullable().optional(),
    exists: z.record(z.string(), z.boolean()).catch({}),
    states: z.record(z.string(), z.string()).optional(),
    missing: z.array(shadowReviewMissingArtifactSchema).catch([])
  }).passthrough(),
  items: z.array(shadowReviewItemSchema).catch([]),
  runtime: unknownRecordSchema.catch({}),
  guardrails: z.object({
    nonExecutable: z.literal(true),
    executionDisabled: z.literal(true),
    affectsPortfolio: z.literal(false),
    affectsAdviceAccuracy: z.literal(false),
    affectsLongMemoryPromotion: z.literal(false),
    allowExecutionEvidence: z.literal(false)
  }).passthrough()
}).passthrough();

export const systemPageSchema = z.object({
  selectedDate: z.string(),
  summary: unknownRecordSchema,
  system: systemSchema
}).passthrough();

export const copilotCitationSchema = z.object({
  id: z.string().catch(""),
  docId: z.string().optional(),
  chunkId: z.string().optional(),
  sourceKind: z.string().optional(),
  sourceRecordId: z.string().optional(),
  sourcePath: z.string().optional(),
  sourceTier: z.string().optional(),
  title: z.string().optional(),
  summary: z.string().optional(),
  asOfDate: z.string().optional(),
  availableFrom: z.string().optional(),
  publishedAt: z.string().optional(),
  domain: z.string().optional(),
  entityId: z.string().optional(),
  fundCodes: z.array(z.string()).catch([]),
  score: z.coerce.number().optional(),
  stale: z.boolean().optional(),
  freshnessStatus: z.string().optional(),
  visibility: z.string().optional(),
  status: z.string().optional(),
  url: z.string().optional()
}).passthrough();

export const copilotResponseSchema = z.object({
  answer: z.string().catch(""),
  mode: z.string().optional(),
  sourceDate: z.string().optional(),
  traceId: z.string().optional(),
  citations: z.array(copilotCitationSchema).catch([]),
  retrieval: unknownRecordSchema.catch({}),
  traceSummary: unknownRecordSchema.catch({}),
  fallbackReason: z.string().optional(),
  ragFallbackReason: z.string().optional()
}).passthrough();

export function apiEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.object({
    ok: z.boolean(),
    data: dataSchema.nullable(),
    error: apiErrorSchema.nullable().optional(),
    meta: apiMetaSchema.optional()
  }).passthrough();
}
