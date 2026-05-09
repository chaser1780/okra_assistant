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

export type ResearchPayload = {
  meta: string;
  metrics: Metric[];
  rows: Record<string, unknown>[];
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

export type SystemPayload = {
  sourceHealth?: Record<string, unknown>;
  preflightStatus?: string;
  settings?: Record<string, unknown>;
  llmRuntime?: Record<string, unknown>;
  todayAnalysisRuntime?: TodayAnalysisRuntimePayload;
  longMemoryRuntime?: Record<string, unknown>;
  agentRuntime?: Record<string, unknown>;
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
