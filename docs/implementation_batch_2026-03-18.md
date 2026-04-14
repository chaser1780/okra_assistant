# okra assistant 实施批次说明（2026-03-18）

- 文档定位：本轮直接落地的实施清单与验收标准
- 目标：先完成一批“可一次交付完成”的高价值改造，而不是把全部远期想法同时铺开
- 范围：性能热路径、核心工作台界面、交易检查体验、对应测试与文档对齐

## 1. 本轮交付范围

本轮只做以下 6 个主题，并要求全部在代码中落地：

1. 实时链路热路径优化
2. 抓取层连接复用与降级语义增强
3. Dashboard 决策驾驶舱增强
4. Realtime 实时异常监控台增强
5. Research 共识 / 冲突视图增强
6. Trade 交易前后模拟增强

不纳入本轮的内容：

- 全量 UI 栈迁移到 PySide6
- LLM 静态上下文 / 增量上下文双轨架构重写
- 全项目乱码源文件全面清洗
- Review 页 T+1/T+5/T+20 矩阵大改版

## 2. 文件级实施清单

### 2.1 实时链路热路径优化

- [scripts/run_realtime_monitor.py](/F:/okra_assistant/scripts/run_realtime_monitor.py)
  - 并行执行 `fetch_intraday_proxies.py` 与 `fetch_realtime_estimate.py`
  - 新增 `should_sync_units()`，仅在持仓份额确有必要更新时才运行 `sync_portfolio_units.py`
  - 让 manifest 能正确反映并行步骤与跳过步骤
- [scripts/build_realtime_profit.py](/F:/okra_assistant/scripts/build_realtime_profit.py)
  - 新增 `divergence_pct`
  - 新增 `freshness_age_business_days`
  - 新增 `position_weight_pct`
  - 新增 `anomaly_score`
- [scripts/models.py](/F:/okra_assistant/scripts/models.py)
  - 补齐 `RealtimeItem` 的新增字段类型定义

验收：

- 实时刷新链路比原先更短
- 未发生官方净值日期变化时，不重复回写持仓份额
- 实时结果包含异常程度与分歧度字段

### 2.2 抓取层连接复用与降级语义增强

- [scripts/fetch_fund_quotes.py](/F:/okra_assistant/scripts/fetch_fund_quotes.py)
  - 由“每只基金一个 Session”改为“线程级 Session 复用”
- [scripts/fetch_realtime_estimate.py](/F:/okra_assistant/scripts/fetch_realtime_estimate.py)
  - 同上
- [scripts/fetch_fund_news.py](/F:/okra_assistant/scripts/fetch_fund_news.py)
  - 同上
- [scripts/fetch_fund_profiles.py](/F:/okra_assistant/scripts/fetch_fund_profiles.py)
  - 同上

验收：

- 同类抓取脚本内部不再为每个基金重复创建会话
- 抓取失败时保留现有降级逻辑，不破坏输出结构

### 2.3 Dashboard 决策驾驶舱增强

- [app/desktop_shell.py](/F:/okra_assistant/app/desktop_shell.py)
  - 新增 `view_mode`（分析师模式 / 投资用户模式）
  - 绑定 UI 事件并持久化
  - Dashboard 刷新时将 `view_mode` 传入 schema
- [app/ui_prefs.py](/F:/okra_assistant/app/ui_prefs.py)
  - 为 `view_mode` 增加默认值与持久化支持
- [app/views/dashboard.py](/F:/okra_assistant/app/views/dashboard.py)
  - 保持当前布局骨架不重写，但增强首屏语义
- [app/ui_schemas.py](/F:/okra_assistant/app/ui_schemas.py)
  - `build_dashboard_detail_schema()` 增加视角感知
  - `build_portfolio_cockpit_schema()` 增加风险预算、数据可信度与时间语义表达

验收：

- 第一屏更明确回答“今天该不该动”
- 分析师模式强调风险、预算、可信度
- 投资用户模式强调结论、原因、风险和时间语义

### 2.4 Realtime 实时异常监控台增强

- [app/views/realtime.py](/F:/okra_assistant/app/views/realtime.py)
  - 在表格中新增“异常程度”“估值-代理分歧”“仓位占比”列
  - 改成打开即显示全部基金，不再提供搜索 / 筛选项
- [app/desktop_shell.py](/F:/okra_assistant/app/desktop_shell.py)
  - 更新实时排序映射与刷新逻辑
  - `refresh_rt()` 不再做列表过滤，直接展示全量基金
  - 默认支持按异常程度排序
- [app/ui_support.py](/F:/okra_assistant/app/ui_support.py)
  - 更新实时行显示值、摘要文本与辅助格式化
- [app/ui_schemas.py](/F:/okra_assistant/app/ui_schemas.py)
  - `build_realtime_detail_schema()` 增加异常程度、分歧和数据时效分层表达

验收：

- 用户能一眼识别 stale、proxy fallback、estimate/proxy 分歧大、组合影响大的基金
- 不再只按涨跌幅理解“是否值得关注”

### 2.5 Research 共识 / 冲突视图增强

- [app/desktop_shell.py](/F:/okra_assistant/app/desktop_shell.py)
  - `show_fund_detail()` 将 aggregate 结果传入 schema
- [app/ui_schemas.py](/F:/okra_assistant/app/ui_schemas.py)
  - `build_fund_detail_schema()` 增加委员会共识、冲突、风控覆盖摘要
- [app/ui_support.py](/F:/okra_assistant/app/ui_support.py)
  - 新增从 aggregate 中抽取基金级 agent 信号的辅助函数

验收：

- 建议详情能解释“谁支持、谁反对、谁压制了动作”
- 不再只有 thesis / evidence 的静态描述

### 2.6 Trade 交易前后模拟增强

- [app/ui_schemas.py](/F:/okra_assistant/app/ui_schemas.py)
  - `build_trade_precheck_schema()` 新增交易后持仓、现金、上限余量、到账节奏模拟
- [app/views/trade.py](/F:/okra_assistant/app/views/trade.py)
  - 保持两栏结构，但右侧检查台承载更多模拟信息
- [app/ui_support.py](/F:/okra_assistant/app/ui_support.py)
  - 增强交易预览文案与结构化字段

验收：

- 用户提交前可直接看到交易后的基金市值、现金仓、上限余量
- 风险和节奏信息不再埋在长文里

### 2.7 测试与文档对齐

- [tests/test_revaluation_and_realtime.py](/F:/okra_assistant/tests/test_revaluation_and_realtime.py)
  - 覆盖异常程度、分歧度、条件同步份额
- [tests/test_pipeline_logic.py](/F:/okra_assistant/tests/test_pipeline_logic.py)
  - 覆盖实时链路并行 / 同步判定辅助逻辑
- [docs/INDEX.md](/F:/okra_assistant/docs/INDEX.md)
  - 纳入本实施文档入口

验收：

- 新逻辑有自动化测试覆盖
- 文档索引能找到本轮实施说明

## 3. 完成定义

本批次完成必须同时满足：

1. 代码改动已落地，且运行链路没有断
2. 相关测试通过
3. 文档已更新到 `docs/INDEX.md`
4. 最终交付说明能清楚区分“已完成”和“未纳入本轮”
