# okra assistant 续接备忘录（2026-03-11）

## 1. 今日结论

今天的主目标已经完成：

- `F:\okra_assistant\docs\development_todo.md` 中所有条目已推进到完成状态
- 当前工程已完成从 P0 到 P3 的本轮 TODO 落地

换句话说，**本轮 todo 已全部收口**。

---

## 2. 本轮完成的核心事项

### 2.1 金融准确性与时间语义

- 已完成每日官方净值重估
- 已接入夜间链路
- 已在 UI / 报告中显示组合估值日期
- 已接入多周期复盘（至少已跑通 `T+1`）
- 已统一官方净值 / 实时估值 / 代理行情的新鲜度语义

相关关键文件：

- `F:\okra_assistant\scripts\revalue_portfolio_official_nav.py`
- `F:\okra_assistant\scripts\review_advice.py`
- `F:\okra_assistant\scripts\build_nightly_review_report.py`
- `F:\okra_assistant\scripts\common.py`
- `F:\okra_assistant\scripts\build_realtime_profit.py`

### 2.2 工程结构

- 已完成核心 JSON TypedDict 模型层骨架
- 已完成配置漂移清理：
  - `agents.toml`
  - `review.toml`
  - `realtime_valuation.toml`
- 已完成运行 manifest 结构化
- 已完成测试基础版扩展
- 已完成桌面壳分层第一轮重构
- 已完成文档与乱码清理

相关关键文件：

- `F:\okra_assistant\scripts\models.py`
- `F:\okra_assistant\scripts\provider_adapters.py`
- `F:\okra_assistant\scripts\run_manifest_utils.py`
- `F:\okra_assistant\app\ui_support.py`
- `F:\okra_assistant\app\task_state.py`
- `F:\okra_assistant\app\task_runtime.py`

### 2.3 研究与产品增强

- 已完成组合暴露分析
- 已接入基金基本画像 slow factors
- 已加入交易现实约束（锁定金额 / 可卖金额 / 到账时效）
- 已加入无操作基线复盘
- 已完成 Dashboard 三问式首页、变化解释、告警层、通俗版总结
- 已完成交易前后对比输出

相关关键文件：

- `F:\okra_assistant\scripts\portfolio_exposure.py`
- `F:\okra_assistant\scripts\fetch_fund_profiles.py`
- `F:\okra_assistant\scripts\trade_constraints.py`
- `F:\okra_assistant\scripts\record_trade.py`
- `F:\okra_assistant\app\desktop_shell.py`
- `F:\okra_assistant\app\ui_support.py`

---

## 3. 当前验证状态

### 3.1 自动化验证

已执行：

- `python -X utf8 -m unittest discover -s F:\okra_assistant\tests -p test_*.py`

结果：

- **30 个测试，全部通过**

### 3.2 真实/半真实链路验证

已确认：

- `realtime_monitor` 真跑成功
- `nightly` 真跑成功
- `intraday --llm-mock` 全链路成功

### 3.3 当前唯一需要记住的运行层观察

今天尝试过：

- `run_daily_pipeline.py --mode intraday`（真实模型）

结果：

- **在模型阶段超时（约 15 分钟）**

这更像是：

- 模型 / 中转层 / 推理时延问题
- 而不是本轮代码改造导致的结构性错误

因为：

- 真实子链路（realtime / nightly）能跑
- `intraday --llm-mock` 整条链能跑
- 编译与测试均通过

因此明天如果继续追稳定性，优先方向不是改业务逻辑，而是：

1. 观察真实 `intraday` manifest / 日志
2. 判断是否需要放宽超时或拆更细的真实模型调用
3. 重点排查 news 抓取与真实 LLM 阶段的时间占用

---

## 4. 当前 TODO 状态

文件：

- `F:\okra_assistant\docs\development_todo.md`

当前状态：

- 所有条目均已标记为完成
- 不存在仍为 `[todo]` 或 `[doing]` 的开发项

这意味着明天继续时，不再是“继续完成 todo”，而是进入：

- 后续优化 / 新目标 / 稳定性追踪阶段

---

## 5. 明天建议的直接续接点

如果明天继续，建议直接从下面 3 条里选一条开始：

### 方向 A：真实日内链路稳定性

目标：

- 把真实 `intraday` 跑通得更稳定

建议切入点：

- 读取最新 run manifest
- 读取最新 desktop / llm 日志
- 定位真实模型阶段耗时与超时原因

### 方向 B：桌面壳第二轮拆层

目标：

- 继续把 `desktop_shell.py` 中剩余页面刷新和事件控制拆出去

当前已具备的基础模块：

- `F:\okra_assistant\app\ui_support.py`
- `F:\okra_assistant\app\task_state.py`
- `F:\okra_assistant\app\task_runtime.py`

### 方向 C：慢变量数据第二阶段

目标：

- 在当前基础画像之上，继续接入更实用的基金慢变量

建议扩展字段：

- 规模变化
- 管理费/托管费更稳定抓取
- 经理变动历史
- 回撤与风格漂移

---

## 6. 本轮新增/重要文件清单

### 新增

- `F:\okra_assistant\scripts\models.py`
- `F:\okra_assistant\scripts\provider_adapters.py`
- `F:\okra_assistant\scripts\run_manifest_utils.py`
- `F:\okra_assistant\scripts\portfolio_exposure.py`
- `F:\okra_assistant\scripts\fetch_fund_profiles.py`
- `F:\okra_assistant\scripts\trade_constraints.py`
- `F:\okra_assistant\app\ui_support.py`
- `F:\okra_assistant\app\task_state.py`
- `F:\okra_assistant\app\task_runtime.py`
- `F:\okra_assistant\tests\helpers.py`
- `F:\okra_assistant\tests\test_provider_adapters.py`
- `F:\okra_assistant\tests\test_portfolio_exposure.py`
- `F:\okra_assistant\tests\test_fund_profiles.py`
- `F:\okra_assistant\tests\test_review_baseline.py`
- `F:\okra_assistant\docs\INDEX.md`

### 重要更新

- `F:\okra_assistant\scripts\run_daily_pipeline.py`
- `F:\okra_assistant\scripts\run_realtime_monitor.py`
- `F:\okra_assistant\scripts\build_llm_context.py`
- `F:\okra_assistant\scripts\build_realtime_profit.py`
- `F:\okra_assistant\scripts\review_advice.py`
- `F:\okra_assistant\scripts\build_nightly_review_report.py`
- `F:\okra_assistant\scripts\validate_llm_advice.py`
- `F:\okra_assistant\scripts\record_trade.py`
- `F:\okra_assistant\scripts\run_multiagent_research.py`
- `F:\okra_assistant\app\desktop_shell.py`
- `F:\okra_assistant\config\settings.toml`
- `F:\okra_assistant\config\agents.toml`
- `F:\okra_assistant\config\realtime_valuation.toml`
- `F:\okra_assistant\config\portfolio.json`
- `F:\okra_assistant\references\source_priority.md`
- `F:\okra_assistant\docs\development_todo.md`

---

## 7. 一句话续接摘要

**todo 已全部完成；当前最值得明天继续的，不是补功能，而是优先攻克真实 intraday 链路的模型时延/超时稳定性。**
