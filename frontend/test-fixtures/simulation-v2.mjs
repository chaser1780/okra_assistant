// 虚构 simulation_v2 契约 fixtures（仅用于前端离线验证，非真实账户/行情数据）。
// 字段对齐 frontend/src/lib/schemas.ts 的 todayPageSchema / researchPageSchema 等。
export const FIXTURE_DATE = "2026-10-28";

export const fixturePortfolioItem = {
  fundCode: "FICT01", fundName: "虚构混合基金A", amount: 50000, amountText: "50,000.00",
  weight: 0.5, weightText: "50.00%", risk: "中", action: "add", role: "core_long_term",
  styleGroup: "平衡型", holdingPnl: 2000, holdingPnlText: "2,000.00", holdingReturnPct: 4,
  holdingReturnPctText: "4.00%", officialDailyPnl: 100, officialDailyPnlText: "100.00",
  officialDailyPnlDate: "2026-10-27", officialDailyPnlStatus: "", officialDailyPnlReason: "",
  costBasis: 48000, costBasisText: "48,000.00", holdingUnits: 10000, lastNav: 5.0,
  lastNavDate: "2026-10-27", allowTrade: true, fixedDailyBuyAmount: 0, allowExtraBuys: true
};

export const fixturePortfolio = {
  asOfDate: FIXTURE_DATE, totalValue: 100000, totalValueText: "100,000.00", cash: 10000,
  cashText: "10,000.00", holdingPnl: 5000, holdingPnlText: "5,000.00", styleAllocation: [],
  roleAllocation: [], profitLeaders: [fixturePortfolioItem], lossLeaders: [],
  history: { totalValue: [], holdingPnl: [], holdingReturnPct: [] }, items: [fixturePortfolioItem]
};

// v2 建议：sizeTier=medium(25%)，decisionAt 带时区 offset
export const fixtureV2Card = {
  ticketId: "v2-fict-1", fundCode: "FICT01", fundName: "虚构混合基金A", selectedDate: FIXTURE_DATE,
  section: "核心", strategyBucket: "core", action: "add", actionLabel: "加仓",
  schemaVersion: "simulation_v2", sizeTier: "medium", sizeRatio: 0.25,
  sizingBasis: "fund_position_value", basisPositionValue: 50000, basisSnapshotSha256: "sha256:fict",
  horizon: "中期(3-6月)", evidenceQuality: "medium", decisionAt: FIXTURE_DATE + "T09:00:00+08:00",
  amount: null, amountText: "不可用", priority: 1, confidence: 0.72, confidenceText: "0.72",
  thesis: "估值回落，建议中仓参与。", evidence: ["近3月回撤收敛"], risks: ["流动性风险"],
  agentSupport: [], sourceSignalIds: [], opposingSignalIds: [], policyRuleHits: [],
  constraintHits: [], consensusText: "共识", hasConflict: false, isActionable: true,
  portfolio: {}, market: {}, news: { items: [], riskItems: [], count: 0, riskCount: 0 },
  profile: {}, evidenceRefs: []
};

// legacy 建议：sizeTier='legacy'，前端不得反推档位
export const fixtureLegacyCard = {
  ticketId: "leg-fict-1", fundCode: "FICT02", fundName: "虚构债券基金B", selectedDate: FIXTURE_DATE,
  section: "防守", strategyBucket: "defense", action: "add", actionLabel: "加仓",
  schemaVersion: "simulation_v1", sizeTier: "legacy", amount: 2000, amountText: "2,000.00",
  priority: 2, confidence: 0.6, confidenceText: "0.60", thesis: "利率下行，建议增配。",
  evidence: [], risks: [], agentSupport: [], sourceSignalIds: [], opposingSignalIds: [],
  policyRuleHits: [], constraintHits: [], consensusText: "共识", hasConflict: false,
  isActionable: true, portfolio: {}, market: {}, news: { items: [], riskItems: [], count: 0, riskCount: 0 },
  profile: {}, evidenceRefs: []
};

export const fixtureResearch = {
  meta: "fixture", metrics: [], rows: [], fund_cards: [fixtureV2Card, fixtureLegacyCard], source_health: {}
};

export const fixtureLongMemory = {
  updatedAt: "", records: [], pending: [], fund: [], market: [], execution: [], portfolio: [], counts: {}
};

export const fixtureToday = {
  selectedDate: FIXTURE_DATE,
  dashboard: {
    meta: "fixture", metrics: [], focus_text: "重点关注虚构基金", market_text: "市场震荡",
    change_text: "", summary_text: "今日摘要", detail_text: "", primary_fund_code: "FICT01",
    committee_text: "投委会结论：中仓参与核心。", provider_text: ""
  },
  portfolio: fixturePortfolio,
  research: fixtureResearch,
  longMemory: fixtureLongMemory,
  dailyFirstOpen: { decision: {}, analysis: {}, brief: "今日首开：市场震荡。" },
  system: {}
};

export const fixtureExecutionSync = {
  updatedAt: FIXTURE_DATE, pending: [], trades: [], deviations: [], reconciliationReports: [], counts: {}
};
