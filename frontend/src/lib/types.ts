export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info" | "purple" | "magenta" | "amber";

export type Metric = {
  title: string;
  value: string;
  body: string;
  tone?: Tone;
};

export type DashboardPayload = {
  meta: string;
  metrics: Metric[];
  focus_text: string;
  market_text: string;
  change_text: string;
  summary_text: string;
  detail_text: string;
  primary_fund_code: string;
  committee_text: string;
  provider_text: string;
};

export type PortfolioItem = {
  fundCode: string;
  fundName: string;
  amount: number;
  amountText: string;
  weight: number | string;
  weightText: string;
  risk: string;
  action: string;
  role: string;
  styleGroup: string;
  holdingPnl: number;
  holdingPnlText: string;
  holdingReturnPct: number;
  holdingReturnPctText: string;
  costBasis: number;
  costBasisText: string;
  holdingUnits: number;
  lastNav: number;
  lastNavDate: string;
  allowTrade: boolean;
  fixedDailyBuyAmount: number;
  allowExtraBuys: boolean;
};

export type ChartPoint = {
  date: string;
  value: number;
};

export type AllocationRow = {
  name: string;
  value: number;
  valueText: string;
  weight: number;
  weightText: string;
};

export type PortfolioPayload = {
  asOfDate: string;
  totalValue: number;
  totalValueText: string;
  cash: number;
  cashText: string;
  holdingPnl: number;
  holdingPnlText: string;
  styleAllocation: AllocationRow[];
  roleAllocation: AllocationRow[];
  profitLeaders: PortfolioItem[];
  lossLeaders: PortfolioItem[];
  history: {
    totalValue: ChartPoint[];
    holdingPnl: ChartPoint[];
    holdingReturnPct: ChartPoint[];
  };
  items: PortfolioItem[];
};

export type ResearchDigestEntry = Record<string, unknown> & {
  news_id?: string;
  id?: string;
  title?: string;
  summary?: string;
  provider?: string;
  source_key?: string;
  source_name?: string;
  source_role?: string;
  evidence_type?: string;
  query_type?: string;
  label?: string;
  name?: string;
  key?: string;
  status?: string;
  count?: number | string;
  item_count?: number | string;
  mapped_item_count?: number | string;
  unique_item_count?: number | string;
  heat_score?: number | string;
  virality_score?: number | string;
  sentiment_score?: number | string;
  sentiment_label?: string;
  risk_level?: string;
  severity?: string;
  fund_code?: string;
  code?: string;
  canonical_url?: string;
  source_url?: string;
  url?: string;
  published_at?: string;
  evidence_url?: string;
  notes?: string[] | string;
};

export type ResearchDigestBreakdown = Record<string, unknown> | ResearchDigestEntry[];

export type ResearchSourceHealthPayload = {
  report_date?: string;
  generated_at?: string;
  summary?: Record<string, unknown>;
  items?: ResearchDigestEntry[];
};

export type ResearchNewsDigest = Record<string, unknown> & {
  item_count?: number | string;
  mapped_item_count?: number | string;
  unique_item_count?: number | string;
  duplicate_item_count?: number | string;
  by_source_role?: Record<string, unknown>;
  by_evidence_type?: Record<string, unknown>;
  source_breakdown?: ResearchDigestBreakdown;
  query_breakdown?: ResearchDigestBreakdown;
  top_heat_items?: ResearchDigestEntry[];
  top_risk_items?: ResearchDigestEntry[];
  latest?: ResearchDigestEntry[];
};

export type ResearchSentimentBlock = Record<string, unknown> & {
  label?: string;
  sentiment_label?: string;
  score?: number | string;
  item_count?: number | string;
  positive_count?: number | string;
  neutral_count?: number | string;
  negative_count?: number | string;
  mixed_count?: number | string;
};

export type ResearchSentimentDigest = Record<string, unknown> & {
  item_count?: number | string;
  provider_count?: number | string;
  sentiment_score?: number | string;
  text_sentiment_score?: number | string;
  heat_score?: number | string;
  derived_sentiment_score?: number | string;
  max_virality_score?: number | string;
  providers?: ResearchDigestEntry[];
  source_health?: ResearchDigestEntry[];
  provider_health?: ResearchDigestBreakdown;
  classifier_health?: ResearchDigestBreakdown;
  disabled_sources?: Array<string | ResearchDigestEntry>;
  latest?: ResearchDigestEntry[];
  text_sentiment?: ResearchSentimentBlock;
  heat_sentiment?: ResearchSentimentBlock;
  derived_sentiment?: ResearchSentimentBlock;
};

export type ResearchPayload = {
  meta: string;
  metrics: Metric[];
  rows: Record<string, unknown>[];
  source_health?: ResearchSourceHealthPayload;
  news_digest?: ResearchNewsDigest;
  sentiment_digest?: ResearchSentimentDigest;
  event_risks?: ResearchDigestEntry[];
};

export type NewsIntelligencePayload = Record<string, unknown> & {
  metrics?: Record<string, unknown>;
  source_health?: ResearchSourceHealthPayload;
  news_digest?: ResearchNewsDigest;
  sentiment_digest?: ResearchSentimentDigest;
  important_news?: ResearchDigestEntry[];
  regulatory_items?: ResearchDigestEntry[];
  szse_items?: ResearchDigestEntry[];
  related_news_by_fund?: Record<string, ResearchDigestEntry[]>;
  source_breakdown?: ResearchDigestBreakdown;
  event_risks?: ResearchDigestEntry[];
};

export type FundAnalysisAgentCard = {
  agent_name: string;
  stage: string;
  stageLabel: string;
  stageDescription: string;
  status: string;
  summary: string;
  confidence: number;
  dependsOn: string[];
  consumers: string[];
  isCommitteeCore: boolean;
  portfolioView: Record<string, unknown>;
  fundViews: Record<string, unknown>[];
  signalCards: Record<string, unknown>[];
  decisionCards: Record<string, unknown>[];
};

export type FundAnalysisDetailPayload = {
  agentSummary: Record<string, unknown>;
  stageSummary: Record<string, unknown>;
  agentCards: FundAnalysisAgentCard[];
};

export type RealtimePayload = {
  meta: string;
  metrics: Metric[];
  items: Record<string, unknown>[];
  summary_text: string;
};

export type ReviewPayload = {
  meta: string;
  metrics: Metric[];
  summary_text: string;
  detail_text: string;
  core_lines: string[];
  strategic_lines: string[];
  replay_lines: string[];
  fund_memory_lines?: string[];
  market_memory_lines?: string[];
  execution_memory_lines?: string[];
  pending_memory_lines?: string[];
};

export type MemoryStatus = "candidate" | "strategic" | "permanent" | "archived" | "rejected";
export type MemoryDomain = "fund" | "market" | "execution" | "portfolio";
export type MemoryAction = "approve" | "reject" | "archive" | "demote";

export type LongMemoryRecord = {
  memory_id: string;
  memory_type: string;
  domain: MemoryDomain | string;
  entity_key: string;
  title: string;
  text: string;
  status: MemoryStatus | string;
  priority?: string;
  confidence: number;
  support_count: number;
  contradiction_count: number;
  last_supported_at?: string;
  last_contradicted_at?: string;
  approved_by?: string;
  approved_at?: string;
  can_promote_permanent?: boolean;
  source?: string;
  metadata?: Record<string, unknown>;
  evidence_refs?: Array<Record<string, unknown>>;
  created_at?: string;
  updated_at?: string;
};

export type LongMemoryPayload = {
  updatedAt: string;
  records: LongMemoryRecord[];
  pending: LongMemoryRecord[];
  fund: LongMemoryRecord[];
  market: LongMemoryRecord[];
  execution: LongMemoryRecord[];
  portfolio: LongMemoryRecord[];
  counts: {
    fund?: number;
    market?: number;
    execution?: number;
    portfolio?: number;
    pending?: number;
    total?: number;
  };
};

export type DailyFirstOpenPayload = {
  decision: Record<string, unknown>;
  analysis: Record<string, unknown>;
  updates?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  brief: string;
  runStatus?: string | number | boolean;
  analysisQuality?: string | number | boolean;
  memoryEligible?: boolean | string | number;
};

export type TodayAnalysisPayload = DailyFirstOpenPayload;

export type TodayAnalysisSystemPayload = {
  selectedDate?: string;
  today?: string;
  autoRunNeeded?: boolean;
  todayWorkspace?: string;
  todayDecisionPath?: string;
  todayDecisionExists?: boolean;
  hasRunToday?: boolean;
  runAt?: string;
  runTime?: string;
  runStatus?: string;
  analysisQuality?: string | number | boolean;
  memoryEligible?: boolean | string;
  memoryCycleSummary?: Record<string, unknown>;
};

export type TodayAnalysisRuntimePayload = {
  runId?: string;
  pid?: number;
  status?: string;
  startedAt?: string;
  endedAt?: string;
  heartbeatAt?: string;
  elapsedSeconds?: number;
  currentStep?: string;
  currentAgent?: string;
  currentAgentStage?: string;
  resultReady?: boolean;
  resultRunId?: string;
  lastError?: string;
};

export type RagRuntimePayload = Record<string, unknown> & {
  generatedAt: string;
  enabled: boolean;
  defaultProfile: string;
  fallbackToLegacy: boolean;
  traceEnabled: boolean;
  dbPath: string;
  dbExists: boolean;
  counts: Record<string, number>;
  sourceCounts: Record<string, number>;
  embeddingStatus: Record<string, number>;
  agentShadow: Record<string, unknown>;
  agentDefault: Record<string, unknown>;
  profileEvidence: Record<string, unknown>;
  embedding: Record<string, unknown>;
  vectorStore: Record<string, unknown>;
  latestEval: Record<string, unknown>;
  latestTraces: Array<Record<string, unknown>>;
  latestIngestRuns: Array<Record<string, unknown>>;
  activeManifests: Array<Record<string, unknown>>;
  statusError?: string;
};

export type SystemPayload = {
  sourceHealth?: Record<string, unknown>;
  preflightStatus?: string;
  settings?: Record<string, unknown>;
  llmRuntime?: Record<string, unknown>;
  todayAnalysisRuntime?: TodayAnalysisRuntimePayload;
  longMemoryRuntime?: Record<string, unknown>;
  agentRuntime?: Record<string, unknown>;
  ragRuntime?: RagRuntimePayload;
  rag?: RagRuntimePayload;
  todayAnalysis?: TodayAnalysisSystemPayload;
  dailyFirstOpen?: TodayAnalysisSystemPayload;
};

export type ExecutionSyncPayload = {
  updatedAt: string;
  pending: Record<string, unknown>[];
  trades: Record<string, unknown>[];
  deviations: Record<string, unknown>[];
  reconciliationReports: Record<string, unknown>[];
  counts: {
    pending?: number;
    trades?: number;
    deviations?: number;
    reports?: number;
  };
};

export type Snapshot = {
  selectedDate: string;
  dates: string[];
  summary: Record<string, unknown>;
  dashboard: DashboardPayload;
  portfolio: PortfolioPayload;
  research: ResearchPayload;
  intelligence?: NewsIntelligencePayload;
  realtime: RealtimePayload;
  review: ReviewPayload;
  longMemory: LongMemoryPayload;
  executionSync: ExecutionSyncPayload;
  todayAnalysis?: TodayAnalysisPayload;
  dailyFirstOpen: DailyFirstOpenPayload;
  system: SystemPayload;
};

export type ApiEnvelopeMeta = {
  page?: string | null;
  selected_date?: string | null;
  generated_at?: string | null;
  version?: string;
};

export type ApiEnvelopeError = {
  error_code: string;
  error_message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
};

export type ApiEnvelope<T> = {
  ok: boolean;
  data: T | null;
  error?: ApiEnvelopeError | null;
  meta?: ApiEnvelopeMeta;
};

export type ShellPayload = Pick<Snapshot, "selectedDate" | "dates" | "summary" | "system">;
export type TodayPagePayload = Pick<Snapshot, "selectedDate" | "dashboard" | "portfolio" | "longMemory" | "todayAnalysis" | "dailyFirstOpen" | "system">;
export type PortfolioPagePayload = Pick<Snapshot, "selectedDate" | "portfolio">;
export type ExecutionPagePayload = Pick<Snapshot, "selectedDate" | "executionSync" | "portfolio">;
export type ResearchPagePayload = Pick<Snapshot, "selectedDate" | "research">;
export type IntelligencePagePayload = Pick<Snapshot, "selectedDate"> & { intelligence: NewsIntelligencePayload };
export type RealtimePagePayload = Pick<Snapshot, "selectedDate" | "realtime">;
export type ReviewPagePayload = Pick<Snapshot, "selectedDate" | "review" | "longMemory">;
export type SystemPagePayload = Pick<Snapshot, "selectedDate" | "summary" | "system">;

export type CopilotRequest = {
  context: string;
  question: string;
  page: string;
  selectedDate?: string;
  fundCode?: string;
};

export type CopilotCitation = {
  id: string;
  docId?: string;
  chunkId?: string;
  sourceKind?: string;
  sourceRecordId?: string;
  sourcePath?: string;
  sourceTier?: string;
  title?: string;
  summary?: string;
  asOfDate?: string;
  availableFrom?: string;
  publishedAt?: string;
  domain?: string;
  entityId?: string;
  fundCodes?: string[];
  score?: number;
  stale?: boolean;
  freshnessStatus?: string;
  visibility?: string;
  status?: string;
  url?: string;
};

export type CopilotRetrieval = {
  intent?: string;
  profile?: string;
  hitCount?: number;
  missingData?: Record<string, unknown>[];
  sourceCoverage?: Record<string, unknown>;
  candidateCountBeforeFilter?: number;
  candidateCountAfterFilter?: number;
};

export type CopilotResponse = {
  answer: string;
  mode?: string;
  sourceDate?: string;
  traceId?: string;
  citations?: CopilotCitation[];
  retrieval?: CopilotRetrieval;
  traceSummary?: Record<string, unknown>;
  fallbackReason?: string;
  ragFallbackReason?: string;
};

export type TradeMarker = {
  date: string;
  action: string;
  amount: number;
  amountText: string;
  fundCode: string;
  fundName: string;
  source: string;
};

export type FundLongMemoryPayload = {
  fund: LongMemoryRecord[];
  execution: LongMemoryRecord[];
  rules: LongMemoryRecord[];
};

export type FundDetailPayload = {
  fundCode: string;
  fundName: string;
  selectedDate: string;
  range: string;
  portfolio: Partial<PortfolioItem>;
  realtime: Record<string, unknown>;
  research: Record<string, unknown>;
  analysisDetail: FundAnalysisDetailPayload;
  history: {
    nav: ChartPoint[];
    navNormalized: ChartPoint[];
    dayChangePct: ChartPoint[];
    weekChangePct: ChartPoint[];
    monthChangePct: ChartPoint[];
    proxyNormalized: ChartPoint[];
    proxyDayChangePct: ChartPoint[];
    estimateChangePct: ChartPoint[];
    holdingValue: ChartPoint[];
    holdingPnl: ChartPoint[];
    holdingReturnPct: ChartPoint[];
    holdingUnits: ChartPoint[];
  };
  performance: {
    stageReturn: string;
    navSource: string;
    proxySource: string;
    proxyName: string;
  };
  tradeMarkers: TradeMarker[];
  longMemory: FundLongMemoryPayload;
};
