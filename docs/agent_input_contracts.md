# Agent 输入契约表

- 文档定位：约束 `run_multiagent_research.py` 中各 agent prompt 所声明的输入，与 `build_llm_context.py` / `build_agent_input()` 实际提供的输入保持一致
- 更新日期：2026-03-13

## 总原则

1. prompt 中提到的关键输入，必须能在传入 JSON 中找到
2. 暂无真实数据的字段，不在 prompt 中伪装成“已存在”
3. `external_reference` 当前只承诺：
   - `manual_theme_reference_enabled`
   - `manual_biases`
4. 当前系统没有真实接入可量化的“养基宝热度数值”字段，因此 prompt 不再把它表述为已提供的结构化输入

## Agent -> 输入映射

### market_analyst

- 来自 `portfolio_summary`
  - `risk_profile`
  - stale 统计
- 来自 `funds[*]`
  - `quote`
  - `intraday_proxy`
  - `estimated_nav`

### theme_analyst

- 来自 `funds[*]`
  - tactical 基金基础字段
  - `quote`
  - `intraday_proxy`
  - `estimated_nav`
  - `recent_news`
- 来自 `external_reference`
  - `manual_theme_reference_enabled`
  - `manual_biases`

### fund_structure_analyst

- 来自 `funds[*]`
  - `role`
  - `style_group`
  - `current_value`
  - `cap_value`
  - `locked_amount`
  - `allow_trade`

### fund_quality_analyst

- 来自 `funds[*]`
  - `fund_profile`
  - `quote`
  - `recent_news`
  - `role`
  - `style_group`

### news_analyst

- 来自 `funds[*]`
  - `recent_news`

### sentiment_analyst

- 来自 `funds[*]`
  - `quote`
  - `intraday_proxy`
  - `estimated_nav`
- 来自 `external_reference`
  - `manual_theme_reference_enabled`
  - `manual_biases`
- 来自 `memory_digest`
  - 最近 lessons / bias / feedback

### bull_researcher / bear_researcher

- 来自 `funds[*]`
  - tactical 决策所需字段
- 来自 analyst outputs
  - 压缩后的 analyst 结论

### research_manager / risk_manager / portfolio_trader

- 来自 `funds[*]`
  - tactical 决策字段
- 来自 analyst / researcher / manager outputs
  - 压缩后的岗位输出
- 来自 `constraints`
  - 预算
  - cash hub floor
  - DCA / 固定持有约束
- 来自 `memory_digest`
  - 最近偏差与偏置调整

## 当前仍未接入、但后续可以新增的输入

- 实时板块热度数值
- 真实基金底层持仓穿透
- 同类排名与回撤数据库
- 实时成交量/趋势确认信号

这些字段在正式接线前，不应在 prompt 中写成“当前输入已经提供”。
