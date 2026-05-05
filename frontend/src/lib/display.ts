const styleLabels: Record<string, string> = {
  industrial_metal: "工业金属",
  tech_growth: "科技成长",
  carbon_neutral: "碳中和",
  high_end_equipment: "高端装备",
  growth_rotation: "成长轮动",
  china_us_internet: "中美互联网",
  ai: "人工智能",
  cash_buffer: "现金缓冲",
  bond_anchor: "债券锚",
  sp500_core: "标普500核心",
  precious_metals: "贵金属",
  grain_agriculture: "粮食农业",
  nasdaq_core: "纳指核心",
  chemical: "化工",
  grid_equipment: "电网设备"
};

const roleLabels: Record<string, string> = {
  tactical: "战术仓位",
  cash_hub: "现金池",
  fixed_hold: "固定持有",
  core_dca: "核心定投",
  core_long_term: "长期核心",
  satellite_mid_term: "中期卫星",
  tactical_short_term: "短期战术",
  cash_defense: "现金防守"
};

const actionLabels: Record<string, string> = {
  buy: "买入",
  add: "加仓",
  sell: "卖出",
  reduce: "减仓",
  hold: "观察",
  locked: "固定持有",
  scheduled_dca: "计划定投",
  planned_dca: "计划定投",
  not_applicable: "不适用",
  switch: "转换"
};

const statusLabels: Record<string, string> = {
  candidate: "候选",
  strategic: "策略",
  permanent: "永久",
  archived: "归档",
  rejected: "驳回",
  active: "生效",
  inactive: "停用"
};

const domainLabels: Record<string, string> = {
  fund: "基金画像",
  market: "大盘策略",
  execution: "执行纪律",
  portfolio: "组合策略",
  global: "全局"
};

const keyLabels: Record<string, string> = {
  require_signal_confirmation_before_add: "加仓前必须确认信号一致",
  do_not_trim_strength_too_early: "不要过早削减强势仓位",
  cash_floor: "保留现金底仓",
  cash_buffer: "现金缓冲",
  qdii_confirmation_lag_check: "检查 QDII 确认延迟",
  redeem_fee_requires_edge_check: "赎回费需要收益边际覆盖",
  manual_trade_deviation_tracking: "单独跟踪真实交易偏离",
  add_requires_confirmation: "加仓需要二次确认",
  reduce_tends_too_early: "减仓容易过早",
  scheduled_dca_needs_timing_check: "定投需要检查时点",
  signal_or_timing_sensitive: "信号和时点敏感",
  add_signal_has_edge: "加仓信号有优势",
  growth: "成长风格",
  dividend: "红利风格",
  hong_kong: "港股",
  us_qdii: "美股/QDII",
  bond_cash: "债券与现金",
  resource: "资源品",
  defensive: "防御风格",
  mixed: "混合震荡"
};

const titleLabels: Record<string, string> = {
  ...keyLabels,
  RequireSignalConfirmationBeforeAdd: "加仓前必须确认信号一致",
  "Require Signal Confirmation Before Add": "加仓前必须确认信号一致",
  "Do Not Trim Strength Too Early": "不要过早削减强势仓位",
  "Cash Floor": "保留现金底仓",
  "QDII Confirmation Lag": "检查 QDII 确认延迟",
  "Market regime memory": "大盘状态记忆"
};

const textLabels: Record<string, string> = {
  "Do not add tactical positions unless signal confirmation is aligned across proxy, estimate, and the immediate thesis path.":
    "除非代理指数、估算净值和即时投资逻辑都形成一致确认，否则不要增加战术仓位。",
  "Do not de-risk too early when the position remains strong and weakness is not yet confirmed.":
    "当仓位仍然强势、弱势尚未确认时，不要过早降风险或减仓。",
  "Check confirmation lag before QDII or delayed-confirmation buys; split or defer weak-window scheduled entries.":
    "买入 QDII 或确认延迟品种前，先检查确认错位；弱势窗口的计划买入应拆单或顺延。",
  "Do not reduce positions unless expected edge survives redemption fee and settlement friction.":
    "除非预期收益能够覆盖赎回费和到账摩擦，否则不要减仓。",
  "Track actual trades separately from system advice so execution drift does not contaminate advice accuracy.":
    "真实交易要和系统建议分开记录，避免执行偏差污染建议胜率。"
};

const wordLabels: Record<string, string> = {
  require: "要求",
  signal: "信号",
  confirmation: "确认",
  before: "前",
  add: "加仓",
  do: "",
  not: "不要",
  trim: "削减",
  strength: "强势",
  too: "过",
  early: "早",
  cash: "现金",
  floor: "底仓",
  qdii: "QDII",
  redeem: "赎回",
  fee: "费用",
  requires: "需要",
  edge: "收益边际",
  check: "检查",
  manual: "人工",
  trade: "交易",
  deviation: "偏离",
  tracking: "跟踪",
  market: "大盘",
  regime: "状态",
  memory: "记忆",
  advice: "建议",
  profile: "画像",
  fund: "基金",
  rule: "规则",
  policy: "策略"
};

export function styleLabel(value: unknown) {
  return mappedLabel(value, styleLabels, "未分组");
}

export function roleLabel(value: unknown) {
  return mappedLabel(value, roleLabels, "未标注");
}

export function actionLabel(value: unknown) {
  return mappedLabel(value, actionLabels, "观察");
}

export function statusLabel(value: unknown) {
  return mappedLabel(value, statusLabels, "未知状态");
}

export function domainLabel(value: unknown) {
  return mappedLabel(value, domainLabels, "未知领域");
}

export function entityLabel(value: unknown) {
  const key = String(value ?? "").trim();
  if (!key) return "全局";
  if (/^\d{5,6}$/.test(key) || /^[A-Z]?\d+[A-Z]?$/.test(key)) return key;
  return styleLabels[key] || roleLabels[key] || domainLabels[key] || keyLabels[key] || titleFromIdentifier(key);
}

export function memoryTitle(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return "未命名记忆";
  if (titleLabels[raw]) return titleLabels[raw];
  const normalized = normalizeIdentifier(raw);
  if (titleLabels[normalized]) return titleLabels[normalized];

  const fundProfile = raw.match(/^(.+?)\s+advice profile$/i);
  if (fundProfile) return `${fundProfile[1]} 建议画像`;

  const marketRegime = raw.match(/^Market regime memory:\s*(.+)$/i);
  if (marketRegime) return `大盘状态记忆：${entityLabel(marketRegime[1])}`;

  return titleFromIdentifier(raw);
}

export function memoryText(value: unknown) {
  const raw = String(value ?? "").trim();
  if (!raw) return "暂无规则说明。";
  if (textLabels[raw]) return textLabels[raw];

  const fundProfile = raw.match(
    /^(.+?) has (\d+) reviewed system advice samples; success_rate=([\d.]+)%, success=(\d+), failure=(\d+)\. Top diagnostics: (.+)\.$/i
  );
  if (fundProfile) {
    const [, name, count, rate, success, failure, diagnostics] = fundProfile;
    return `${name} 已完成 ${count} 条系统建议复盘，建议胜率 ${rate}%，买对/卖对 ${success} 次，买错/卖错 ${failure} 次。主要诊断：${diagnosticsLabel(diagnostics)}。`;
  }

  const marketRegime = raw.match(
    /^Regime (.+?) appeared on (\d+) advice days; review success_rate=([\d.]+)%, supportive=(\d+), adverse=(\d+), missed=(\d+)\.$/i
  );
  if (marketRegime) {
    const [, regime, days, rate, supportive, adverse, missed] = marketRegime;
    return `${entityLabel(regime)} 状态出现在 ${days} 个建议日；复盘胜率 ${rate}%，有效 ${supportive} 次，反向 ${adverse} 次，错过上涨 ${missed} 次。`;
  }

  return translateCommonSentence(raw);
}

export function evidencePathLabel(path: unknown) {
  const raw = String(path ?? "").trim();
  if (!raw) return "证据";
  return raw.replace(/\\/g, "/").replace(/^.*\/db\//, "db/");
}

export function fieldLabel(value: unknown) {
  const key = String(value ?? "").trim();
  const map: Record<string, string> = {
    selected_date: "查看日期",
    advice_mode: "建议模式",
    decision_source: "决策来源",
    transport_name: "调用通道",
    advice_is_fallback: "是否兜底",
    failed_agent_names: "失败智能体",
    preflight_status: "预检状态",
    api: "接口",
    home: "项目目录",
    version: "版本",
    data_root: "数据目录",
    long_memory: "长期记忆",
    daily_workspace: "每日工作台",
    provider_metadata: "数据源信息",
    provider_name: "数据源名称",
    freshness_status: "新鲜度",
    confidence: "置信度",
    status: "状态",
    source: "来源",
    source_key: "来源标识",
    stale_count: "过期数量",
    error_count: "错误数量",
    updated_at: "更新时间",
    created_at: "创建时间",
    run_date: "运行日期",
    fund_code: "基金代码",
    fund_name: "基金名称",
    style_group: "风格分组",
    role: "组合角色",
    mode: "模式",
    items: "项目",
    counts: "数量",
    total: "总数",
    pending: "待确认",
    fund: "基金画像",
    market: "大盘策略",
    execution: "执行纪律",
    portfolio: "组合策略",
    summary: "摘要",
    detail: "详情",
    error: "错误",
    ok: "正常",
    pid: "进程号",
    task: "任务",
    date: "日期"
  };
  return map[key] || entityLabel(key);
}

export function valueLabel(value: unknown): string {
  if (value === true) return "是";
  if (value === false) return "否";
  if (value === null || value === undefined || value === "") return "暂无";
  if (typeof value === "number") return String(value);
  const raw = String(value);
  const map: Record<string, string> = {
    unknown: "未知",
    ok: "正常",
    warning: "注意",
    error: "错误",
    failed: "失败",
    success: "成功",
    stale: "已过期",
    fresh: "新鲜",
    low: "低",
    medium: "中",
    high: "高",
    research: "研究模式",
    fallback: "兜底",
    local: "本地",
    api: "接口",
    daily: "每日首启",
    realtime: "实时刷新",
    nightly: "夜间复盘",
    proxy_fallback: "代理行情兜底",
    estimate: "基金估值",
    official_nav: "官方净值"
  };
  return (
    map[raw] ||
    styleLabels[raw] ||
    roleLabels[raw] ||
    actionLabels[raw] ||
    statusLabels[raw] ||
    domainLabels[raw] ||
    keyLabels[raw] ||
    raw
  );
}

function mappedLabel(value: unknown, mapping: Record<string, string>, fallback: string) {
  const key = String(value ?? "").trim();
  if (!key) return fallback;
  return mapping[key] || titleFromIdentifier(key);
}

function normalizeIdentifier(value: string) {
  return value
    .replace(/([a-z])([A-Z])/g, "$1_$2")
    .replace(/[\s-]+/g, "_")
    .toLowerCase();
}

function titleFromIdentifier(value: string) {
  const normalized = normalizeIdentifier(value);
  if (!/[_:]/.test(normalized)) return value;
  return normalized
    .split(/[_:]+/)
    .filter(Boolean)
    .map((part) => wordLabels[part] ?? valueLabel(part))
    .filter(Boolean)
    .join("");
}

function diagnosticsLabel(value: string) {
  return value
    .split(",")
    .map((item) => {
      const [key, count] = item.trim().split("=");
      if (!key) return "";
      const label =
        {
          none: "暂无",
          signal_failure: "信号失效",
          timing_drag: "时点拖累",
          missed_upside: "错过上涨",
          good_risk_reduction: "风险控制有效",
          proxy_mismatch: "代理指数偏差"
        }[key] || entityLabel(key);
      return count ? `${label} ${count} 次` : label;
    })
    .filter(Boolean)
    .join("，");
}

function translateCommonSentence(raw: string) {
  return raw
    .replace(/\bDo not\b/gi, "不要")
    .replace(/\bde-risk\b/gi, "降风险")
    .replace(/\btrim\b/gi, "削减")
    .replace(/\bstrength\b/gi, "强势")
    .replace(/\bposition\b/gi, "仓位")
    .replace(/\bpositions\b/gi, "仓位")
    .replace(/\bconfirmation\b/gi, "确认")
    .replace(/\bsignal\b/gi, "信号")
    .replace(/\bproxy\b/gi, "代理指数")
    .replace(/\bestimate\b/gi, "估算净值")
    .replace(/\bconfidence\b/gi, "置信度");
}
