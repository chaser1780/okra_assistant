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
  amount: number | null;
  amountText: string;
  weight: number | string;
  weightText: string;
  risk: string;
  action: string;
  role: string;
  styleGroup: string;
  holdingPnl: number | null;
  holdingPnlText: string;
  holdingReturnPct: number | null;
  holdingReturnPctText: string;
  officialDailyPnl: number | null;
  officialDailyPnlText: string;
  officialDailyPnlDate: string;
  officialDailyPnlStatus: string;
  officialDailyPnlReason: string;
  costBasis: number | null;
  costBasisText: string;
  holdingUnits: number | null;
  lastNav: number | null;
  lastNavDate: string;
  allowTrade: boolean;
  fixedDailyBuyAmount: number | null;
  allowExtraBuys: boolean;
};

export type ChartPoint = {
  date: string;
  value: number | null;
};

export type DataContext = {
  snapshotId: string;
  selectedDate: string;
  portfolioAsOfDate: string;
  realtimeAsOfDate: string;
  latestRetrievedAt: string;
  decisionCutoff: string;
  sessionStatus: string;
  freshnessStatus: "latest" | "market_closed" | "official_nav_pending" | "proxy_observation" | "delayed_1d" | "delayed_multi_day" | "unavailable" | "conflict" | string;
  freshnessReason: string;
  sourceKey: string;
  sourceAuthority: string;
  sourceConfidence: number | null;
  payloadHash: string;
  itemCount?: number;
  staleItemCount?: number;
  conflictItemCount?: number;
  modeCounts?: Record<string, number>;
};

export type SimulationTrack = {
  trackId: "user_simulation" | "strategy_simulation";
  label: string;
  description?: string;
  formalTrack: boolean;
  affectsFormalPortfolio: boolean;
  executionMode?: string;
  asOfDate?: string;
  positionCount?: number;
  operationCounts?: Record<string, number>;
  experimentCount?: number;
  activeExperimentCount?: number;
  experiments?: Array<Record<string, unknown>>;
};

export type SimulationPayload = {
  activeTrack: "user_simulation";
  formalTrack: "user_simulation";
  simulationOnly: true;
  updatedAt: string;
  tracks: SimulationTrack[];
  userSimulation: SimulationTrack;
  strategySimulation: SimulationTrack;
};

export type StrategySimulationOverview = {
  simulationOnly: true;
  formalTrack: "user_simulation";
  experiments: Array<Record<string, unknown> & {
    experimentId: string;
    label: string;
    status: string;
    actionCount: number;
    asOfDate?: string;
    totalValue?: number | null;
    initialTotalValue?: number | null;
    valueDelta?: number | null;
    actionCounts?: Record<string, number>;
    holdingPnl?: number | null;
  }>;
};

export type AllocationRow = {
  name: string;
  value: number | null;
  valueText: string;
  weight: number | null;
  weightText: string;
};

export type AllocationHistoryPoint = {
  date: string;
  values: Array<{ name: string; weight: number | null }>;
};

export type PortfolioRiskSnapshot = {
  currentDrawdownPct: number | null;
  maxDrawdownPct: number | null;
  cashWeightPct: number | null;
  topHoldingWeightPct: number | null;
  topStyleWeightPct: number | null;
  asOfDate: string;
};

export type PortfolioRiskPoint = {
  fundCode: string;
  fundName: string;
  weightPct: number | null;
  anomalyScore: number | null;
  holdingPnl: number | null;
  styleGroup: string;
};

export type PortfolioRiskBreakdown = {
  fundCode: string;
  fundName: string;
  weightPct: number | null;
  freshnessRisk: number | null;
  dataConflictRisk: number | null;
  volatilityRisk: number | null;
  crowdingRisk: number | null;
  newsRisk: number | null;
  executionFrictionRisk: number | null;
  totalAnomalyScore: number | null;
  observedAnomalyScore: number | null;
  historicalPercentile: number | null;
  historicalSampleCount: number;
  dataCoverage: { availableComponentCount: number; componentCount: number; isPartial: boolean };
  reasons: Record<string, string>;
  methodology: string;
};

export type PortfolioRiskSummary = {
  selectedDate: string;
  methodology: string;
  scoredFundCount: number;
  fundCount: number;
  weightedTotalAnomalyScore: number | null;
  partialCoverageFundCount: number;
  historicalPercentileAvailableCount: number;
};

export type PortfolioBenchmark = {
  status: "available" | "not_configured" | "missing_data" | string;
  name?: string;
  key?: string;
  normalized: ChartPoint[];
  excessReturnPct: ChartPoint[];
};

export type PortfolioPerformanceMetrics = {
  status: string;
  methodology: string;
  periodStart: string;
  periodEnd: string;
  cashflowCount: number;
  twr: { available: boolean; returnPct: number | null };
  mwr: { available: boolean; returnPct: number | null };
  cashflowAdjustedDrawdown?: { available: boolean; currentPct: number | null; maxPct: number | null; series: ChartPoint[] };
  reason: string;
};

export type PortfolioPayload = {
  asOfDate: string;
  totalValue: number | null;
  totalValueText: string;
  cash: number | null;
  cashText: string;
  holdingPnl: number | null;
  holdingPnlText: string;
  styleAllocation: AllocationRow[];
  roleAllocation: AllocationRow[];
  profitLeaders: PortfolioItem[];
  lossLeaders: PortfolioItem[];
  history: {
    totalValue: ChartPoint[];
    holdingPnl: ChartPoint[];
    holdingReturnPct: ChartPoint[];
    totalValueNormalized?: ChartPoint[];
    dailyReturnPct?: ChartPoint[];
    drawdownPct?: ChartPoint[];
    styleAllocationHistory?: AllocationHistoryPoint[];
    roleAllocationHistory?: AllocationHistoryPoint[];
  };
  riskSnapshot?: PortfolioRiskSnapshot;
  riskScatter?: PortfolioRiskPoint[];
  riskBreakdown?: PortfolioRiskBreakdown[];
  riskSummary?: PortfolioRiskSummary;
  benchmark?: PortfolioBenchmark;
  performanceMetrics?: PortfolioPerformanceMetrics;
  dataContext?: DataContext;
  simulation?: SimulationPayload;
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
  classification_confidence?: number | string | null;
  classifier?: string;
  classification_status?: string;
  classifier_model_run_id?: string;
  classifier_prompt_version?: string;
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

export type FundResearchCard = {
  ticketId: string;
  fundCode: string;
  fundName: string;
  selectedDate: string;
  section: string;
  strategyBucket: string;
  action: string;
  actionLabel: string;
  amount: number | null;
  amountText: string;
  priority: number;
  confidence: number;
  confidenceText: string;
  thesis: string;
  evidence: string[];
  risks: string[];
  agentSupport: string[];
  sourceSignalIds: string[];
  opposingSignalIds: string[];
  policyRuleHits: string[];
  constraintHits: string[];
  consensusText: string;
  hasConflict: boolean;
  isActionable: boolean;
  portfolio: Record<string, unknown> & {
    currentValue?: number;
    currentValueText?: string;
    holdingPnl?: number;
    holdingPnlText?: string;
    holdingReturnPct?: number;
    holdingReturnPctText?: string;
    role?: string;
    styleGroup?: string;
    allowTrade?: boolean;
    fixedDailyBuyAmount?: number;
  };
  market: Record<string, unknown> & {
    dayChangePct?: number | null;
    dayChangePctText?: string;
    estimateChangePct?: number | null;
    estimateChangePctText?: string;
    proxyChangePct?: number | null;
    proxyChangePctText?: string;
    officialNav?: number | string;
    officialNavDate?: string;
    estimateTime?: string;
    quoteFreshness?: string;
    estimateFreshness?: string;
    proxyFreshness?: string;
  };
  news: Record<string, unknown> & {
    items?: ResearchDigestEntry[];
    riskItems?: ResearchDigestEntry[];
    count?: number;
    riskCount?: number;
    topTitle?: string;
    topRiskTitle?: string;
  };
  profile: Record<string, unknown> & {
    manager?: string;
    company?: string;
    category?: string;
    riskLevel?: string;
    benchmark?: string;
  };
  evidenceRefs: Record<string, unknown>[];
};

export type ResearchPayload = {
  meta: string;
  metrics: Metric[];
  rows: Record<string, unknown>[];
  fund_cards: FundResearchCard[];
  source_health?: ResearchSourceHealthPayload;
  news_digest?: ResearchNewsDigest;
  sentiment_digest?: ResearchSentimentDigest;
  event_risks?: ResearchDigestEntry[];
  events?: ResearchDigestEntry[];
  eventSummary?: Record<string, unknown>;
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
  dataContext?: DataContext;
  observationOnly?: boolean;
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
  trust?: {
    reportDate: string;
    manifestPath: string;
    manifestExists: boolean;
    mode: string;
    learningEligible: boolean;
    trustedForLearning: boolean;
    reasonCodes: string[];
    latestReplayAudit?: Record<string, unknown>;
    latestReplayAuditPath?: string;
    latestLearningAuditSummary?: Record<string, unknown>;
    latestLearningAuditPath?: string;
  };
  decisionTrace?: Record<string, unknown> & {
    available: boolean;
    reportDate: string;
    source?: string;
    track?: string;
    executionEligible?: boolean;
    decisionCount?: number;
    evidenceCount?: number;
    modelRunCount?: number;
    availableArtifactCount?: number;
    decisions?: Array<Record<string, unknown>>;
  };
};

export type ShadowReviewStatus = "missing" | "not_run" | "running" | "ready" | "partial" | "degraded" | "failed";
export type ShadowReviewCategory = "same" | "changed" | "new_shadow_only" | "legacy_only" | "missing" | "error";
export type ShadowReviewSeverity = "info" | "low" | "medium" | "high";

export type ShadowReviewItem = Record<string, unknown> & {
  reviewId: string;
  fundCode: string;
  fundName: string;
  category: ShadowReviewCategory | string;
  severity: ShadowReviewSeverity | string;
  displayLabel: string;
  nonExecutable: true;
  displayOnly: true;
  legacy?: Record<string, unknown> | null;
  shadow?: Record<string, unknown> | null;
  diff: Record<string, unknown> & {
    actionChanged?: boolean;
    confidenceDelta?: number | null;
    notes?: string[];
  };
  display: Record<string, unknown> & {
    primaryText?: string;
    secondaryText?: string;
    badges?: Array<{ label: string; tone: Tone | string }>;
  };
  guardrails?: Record<string, unknown>;
  softPolicies?: Array<Record<string, unknown>>;
  skillRefs?: Array<Record<string, unknown>>;
  skillOutputs?: Array<Record<string, unknown>>;
  retrieval?: Record<string, unknown> | null;
  debate?: Record<string, unknown> | null;
  outcomeEvents?: Array<Record<string, unknown>>;
};

export type ShadowReviewMissingArtifact = {
  kind: string;
  path?: string | null;
  reason: string;
  message: string;
};

export type ShadowReviewPagePayload = Record<string, unknown> & {
  selectedDate: string;
  status: ShadowReviewStatus;
  generatedAt: string;
  nonExecutable: true;
  displayOnly: true;
  summary: {
    legacyCount: number;
    shadowCount: number;
    comparableCount: number;
    changedCount: number;
    agreementRate?: number | null;
    highRiskDiffCount?: number;
  };
  artifacts: Record<string, unknown> & {
    legacyAdvicePath?: string | null;
    shadowAdvicePath?: string | null;
    shadowTracePath?: string | null;
    evalReportPath?: string | null;
    exists: Record<string, boolean>;
    states?: Record<string, string>;
    missing: ShadowReviewMissingArtifact[];
  };
  items: ShadowReviewItem[];
  runtime: Record<string, unknown>;
  guardrails: Record<string, unknown> & {
    nonExecutable: true;
    executionDisabled: true;
    affectsPortfolio: false;
    affectsAdviceAccuracy: false;
    affectsLongMemoryPromotion: false;
    allowExecutionEvidence: false;
  };
  strategyExperiments?: Array<Record<string, unknown> & {
    experimentId: string;
    label: string;
    status: string;
    actionCount: number;
    asOfDate?: string;
    totalValue?: number | null;
    initialTotalValue?: number | null;
    valueDelta?: number | null;
    actionCounts?: Record<string, number>;
  }>;
};

export type MemoryStatus = "candidate" | "experimental_active" | "validated_strategy" | "strategic" | "permanent" | "archived" | "rejected";
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
  valid_until?: string;
  isExpired?: boolean;
  effectiveStatus?: MemoryStatus | string;
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
  lifecycle?: {
    statusCounts?: Record<string, number>;
    trackCounts?: Record<string, number>;
  };
  recentEvents?: Array<Record<string, unknown> & {
    eventId: string;
    memoryId: string;
    eventType: string;
    fromStatus: string;
    toStatus: string;
    actor: string;
    note: string;
    sourceTrack: string;
    experimentId: string;
    createdAt: string;
  }>;
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
  phase?: string;
  reportDate?: string;
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
  failureType?: string;
  retryable?: boolean;
  degradationMode?: string;
  decisionMode?: string;
  executionEligible?: boolean;
  committeeReady?: boolean;
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
  hybrid: Record<string, unknown>;
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
  simulation?: SimulationPayload;
};

export type ScreenshotPreviewRow = Record<string, unknown> & {
  display_name: string;
  fund_code: string;
  fund_name: string;
  matched_fund_code: string;
  matched_fund_name: string;
  current_value: number | null;
  holding_pnl: number | null;
  holding_return_pct: number | null;
  page_index: number | null;
  row_index: number | null;
};

export type UnmatchedHolding = ScreenshotPreviewRow;

export type FundSourceLink = {
  label: string;
  url: string;
};

export type FundLookupCandidate = Record<string, unknown> & {
  fund_code: string;
  fund_name: string;
  fund_type: string;
  company_name: string;
  manager_name: string;
  latest_nav: number | string | null;
  nav_date: string;
  source_name: string;
  source_url: string;
  search_source_url: string;
  source_links: FundSourceLink[];
  match_score: number | null;
};

export type FundLookupResponse = Record<string, unknown> & {
  query: string;
  candidates: FundLookupCandidate[];
  warnings: string[];
};

export type ScreenshotPreview = Record<string, unknown> & {
  reconcile_id: string;
  import_id: string;
  provider: string;
  generated_at: string;
  sync_date: string;
  source: string;
  platform: string;
  snapshot_date: string;
  detected_holdings: ScreenshotPreviewRow[];
  matched_items: ScreenshotPreviewRow[];
  new_items: ScreenshotPreviewRow[];
  unmatched_detected: UnmatchedHolding[];
  new_fund_candidates: ScreenshotPreviewRow[];
  missing_items: ScreenshotPreviewRow[];
  missing_portfolio_funds: ScreenshotPreviewRow[];
  apply_ready: boolean;
  preview_sha256: string;
  portfolio_state_sha256: string;
  warnings: string[];
  vision_warnings: string[];
  auto_parse_attempted: boolean;
  auto_parse_ok: boolean;
  auto_parse_error: string;
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
export type TodayPagePayload = Pick<Snapshot, "selectedDate" | "dashboard" | "portfolio" | "research" | "longMemory" | "todayAnalysis" | "dailyFirstOpen" | "system">;
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
  intent?: "general_chat" | "page_explain" | "fund_explain" | "decision_explain" | "risk_review" | "execution_review" | "memory_review";
  useRag?: boolean;
  messages?: CopilotMessage[];
};

export type CopilotMessage = {
  role: "user" | "assistant";
  content: string;
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
  amount: number | null;
  amountText: string;
  fundCode: string;
  fundName: string;
  source: string;
};

export type DecisionMarker = {
  date: string;
  type: "buy" | "sell" | "dca" | "hold" | "rule" | string;
  label: string;
  amount?: number | null;
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
    benchmarkNormalized?: ChartPoint[];
    benchmarkDayChangePct?: ChartPoint[];
    drawdownPct?: ChartPoint[];
    excessReturnPct?: ChartPoint[];
    decisionMarkers?: DecisionMarker[];
  };
  performance: {
    stageReturn: string;
    navSource: string;
    proxySource: string;
    proxyName: string;
    benchmarkName?: string;
    benchmarkKey?: string;
    benchmarkStatus?: string;
  };
  tradeMarkers: TradeMarker[];
  longMemory: FundLongMemoryPayload;
  dataContext?: DataContext;
  simulation?: SimulationPayload;
};
