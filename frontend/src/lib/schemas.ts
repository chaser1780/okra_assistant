import { z } from "zod";

const toneSchema = z.enum(["neutral", "accent", "success", "warning", "danger", "info", "purple", "magenta", "amber"]);

const unknownRecordSchema = z.record(z.string(), z.unknown());
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

export const systemSchema = z.object({
  sourceHealth: unknownRecordSchema.optional(),
  preflightStatus: z.string().optional(),
  settings: unknownRecordSchema.optional(),
  llmRuntime: unknownRecordSchema.optional(),
  todayAnalysisRuntime: unknownRecordSchema.optional(),
  longMemoryRuntime: unknownRecordSchema.optional(),
  agentRuntime: unknownRecordSchema.optional(),
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

export const realtimePageSchema = z.object({
  selectedDate: z.string(),
  realtime: realtimeSchema
}).passthrough();

export const reviewPageSchema = z.object({
  selectedDate: z.string(),
  review: reviewSchema,
  longMemory: longMemorySchema
}).passthrough();

export const systemPageSchema = z.object({
  selectedDate: z.string(),
  summary: unknownRecordSchema,
  system: systemSchema
}).passthrough();

export function apiEnvelopeSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.object({
    ok: z.boolean(),
    data: dataSchema.nullable(),
    error: apiErrorSchema.nullable().optional(),
    meta: apiMetaSchema.optional()
  }).passthrough();
}
