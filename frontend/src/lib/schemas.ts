import { z } from "zod";

const toneSchema = z.enum(["neutral", "accent", "success", "warning", "danger", "info", "purple", "magenta", "amber"]);

const unknownRecordSchema = z.record(z.string(), z.unknown());
const numberRecordSchema = z.record(z.string(), z.coerce.number().catch(0)).catch({});
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
const chartPointSchema = z.object({ date: z.string(), value: z.number().catch(0) }).passthrough();
const metricSchema = z.object({
  title: z.string(),
  value: z.string(),
  body: z.string(),
  tone: toneSchema.optional()
}).passthrough();

const portfolioItemSchema = z.object({
  fundCode: z.string(),
  fundName: z.string(),
  amount: z.number().catch(0),
  amountText: z.string(),
  weight: z.union([z.number(), z.string()]),
  weightText: z.string(),
  risk: z.string(),
  action: z.string(),
  role: z.string(),
  styleGroup: z.string(),
  holdingPnl: z.number().catch(0),
  holdingPnlText: z.string(),
  holdingReturnPct: z.number().catch(0),
  holdingReturnPctText: z.string(),
  officialDailyPnl: z.number().nullable().catch(null),
  officialDailyPnlText: z.string().catch("暂无"),
  officialDailyPnlDate: z.string().catch(""),
  officialDailyPnlStatus: z.string().catch(""),
  officialDailyPnlReason: z.string().catch(""),
  costBasis: z.number().catch(0),
  costBasisText: z.string(),
  holdingUnits: z.number().catch(0),
  lastNav: z.number().catch(0),
  lastNavDate: z.string(),
  allowTrade: z.boolean().catch(false),
  fixedDailyBuyAmount: z.number().catch(0),
  allowExtraBuys: z.boolean().catch(false)
}).passthrough();

const allocationRowSchema = z.object({
  name: z.string(),
  value: z.number().catch(0),
  valueText: z.string(),
  weight: z.number().catch(0),
  weightText: z.string()
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
  totalValue: z.number().catch(0),
  totalValueText: z.string(),
  cash: z.number().catch(0),
  cashText: z.string(),
  holdingPnl: z.number().catch(0),
  holdingPnlText: z.string(),
  styleAllocation: z.array(allocationRowSchema),
  roleAllocation: z.array(allocationRowSchema),
  profitLeaders: z.array(portfolioItemSchema),
  lossLeaders: z.array(portfolioItemSchema),
  history: z.object({
    totalValue: z.array(chartPointSchema),
    holdingPnl: z.array(chartPointSchema),
    holdingReturnPct: z.array(chartPointSchema)
  }).passthrough(),
  items: z.array(portfolioItemSchema)
}).passthrough();

export const researchSchema = z.object({
  meta: z.string(),
  metrics: z.array(metricSchema),
  rows: z.array(unknownRecordSchema)
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
  pending_memory_lines: z.array(z.string()).optional()
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
  holdingUnits: z.array(chartPointSchema).catch([])
}).passthrough();

const tradeMarkerSchema = z.object({
  date: z.string(),
  action: z.string(),
  amount: z.number().catch(0),
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
    proxyName: z.string().catch("")
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
  nonExecutable: z.literal(true).catch(true),
  displayOnly: z.literal(true).catch(true),
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
  retrieval: unknownRecordSchema.optional(),
  debate: unknownRecordSchema.optional(),
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
  nonExecutable: z.literal(true).catch(true),
  displayOnly: z.literal(true).catch(true),
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
    nonExecutable: z.literal(true).catch(true),
    executionDisabled: z.literal(true).catch(true),
    affectsPortfolio: z.literal(false).catch(false),
    affectsAdviceAccuracy: z.literal(false).catch(false),
    affectsLongMemoryPromotion: z.literal(false).catch(false),
    allowExecutionEvidence: z.literal(false).catch(false)
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
