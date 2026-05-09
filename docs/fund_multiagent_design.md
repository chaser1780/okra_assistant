# 基金多智能体研究系统设计

- 文档版本：v3
- 更新日期：2026-05-08
- 项目目录：`F:\okra_assistant`

## 1. 目标

当前主链路不是“多个 agent 各写一段观点”这么简单，而是把多智能体研究收口为一条可复盘、可验证、可落地到工作台的正式链路：

- 上游多智能体负责研究、分歧暴露、风险否决、组合建议。
- 中游 canonical committee 负责把核心观点收敛成结构化投委会结论。
- 下游 validated advice 负责生成当前可被回顾、验证、复盘、写入记忆体系的正式建议。
- execution boundary 负责隔离真实操作数据，避免污染基金画像、市场规律、建议胜率学习。

## 2. 当前主链路

按当前实现，核心链路是：

1. `scripts/run_today_analysis.py`
   - canonical today-analysis CLI 入口。
2. `scripts/today_orchestrator.py`
   - 编排 preflight、execution sync、数据刷新、review、long-memory、multi-agent、advice 和 runtime 写盘。
3. `scripts/run_multiagent_research.py`
   - 产出多智能体原始结果和聚合结果。
4. `db/agent_outputs/<date>/aggregate.json`
   - canonical committee 的结构化来源。
5. `db/committee_advice/<date>.json`
   - 委员会口径的建议产物。
6. `db/validated_advice/<date>.json`
   - 当前下游默认使用的正式建议产物。

## 3. Canonical Committee

当前设计里，committee 不是装饰性摘要，而是正式的中间决策层。它至少要保留：

- `bull_case`
- `bear_case`
- `risk_vetoes`
- `manager_decision`
- `committee_confidence`
- `decision_source`

设计要求：

- committee 必须能反映核心 agent 的一致意见、冲突意见、以及风险侧 veto。
- committee 必须能在工作台 Today/Research 页直接展示，不依赖重新解析自由文本。
- 当最终建议退化为 fallback 时，committee 仍然是最可信的结构化轨迹。

## 4. Validated Advice

`validated_advice` 是当前对外、对下游、对记忆系统更稳定的建议层。

它的职责是：

- 收敛最终买卖/持有/观察结论。
- 作为 review、daily report、memory promotion 的默认输入。
- 作为工作台 Today 页的正式建议来源。

设计要求：

- validated advice 必须与 committee artifacts 同步日期、同步上下文。
- validated advice 可以引用 committee 结论，但不能丢失必要的约束信息和可执行性判断。
- 当系统后续做 replay、review、memory promotion 时，应优先把 validated advice 视为 advice truth，而不是直接回读任意 agent 原文。

## 5. Execution Boundary

真实操作与系统建议学习之间必须保持硬边界。

当前边界规则：

- 系统建议和系统复盘驱动：
  - 基金画像学习
  - 市场规律学习
  - 建议胜率与偏差复盘
- 真实交易和真实持仓驱动：
  - 当前组合状态
  - 现金/可卖份额/确认中份额约束
  - execution memory
  - 对系统建议的执行偏差记录

这意味着：

- 用户真实买对或买错，不直接改写系统建议本身是否正确。
- `db/execution_sync/actual_trades/` 只能进入 execution memory，不应混入 fund profile 或 market regime 学习。
- conversion 必须作为一组转换单建模，不能拆成失去关联的买卖碎片。

## 6. Today Analysis Runtime

当前 today-analysis 已经具备运行时状态写盘能力，核心事实如下：

- 运行状态文件：`db/daily_workspace/<date>/today_analysis_runtime.json`
- 运行元数据文件：`db/daily_workspace/<date>/today_analysis_meta.json`
- 结果文件：`db/daily_workspace/<date>/today_analysis.json`
- 决策文件：`db/daily_workspace/<date>/today_decision.json`

运行时用途：

- 防止同日重复启动。
- 给前端 Today 页和 System 页提供 phase、currentStep、currentAgent、runId 等状态。
- 支持 `POST /api/run/daily` 返回 `already_running` 时的轮询恢复。

## 7. API 与工作台落点

当前桌面工作台不是直接读散落 JSON，而是通过 `app/web_api.py` 聚合：

- `GET /api/workbench/today`
- `GET /api/workbench/research`
- `GET /api/workbench/system`
- `GET /api/workbench/execution`
- `GET /api/fund/<fund_code>`
- `POST /api/run/daily`

设计含义：

- Today 页看 validated advice + committee trace + runtime。
- Research 页看 agent stage、committee views、fund-level analysis。
- Execution 页看真实操作、确认进度、截图对账预览与应用。
- System 页看整体状态与任务运行信息。

## 8. 当前约束

- 文档、运行时、页面展示必须优先对齐当前主链路，不再继续扩散旧的 `daily_first_open` 口径。
- 新增设计描述时，优先说明 canonical source 在哪里落盘，而不是只讲概念。
- 不把真实交易行为反向写成“系统学到的新投资规律”，除非明确经过独立审批与边界设计。

## 9. 最小验证口径

这份设计文档对应的最小事实核对点包括：

1. `scripts/run_today_analysis.py` 仍是 today-analysis 正式入口。
2. `app/web_api.py` 暴露 `/api/workbench/*`、`/api/run/daily`、`/api/execution-sync/*`。
3. `db/validated_advice/`、`db/committee_advice/`、`db/agent_outputs/<date>/aggregate.json` 仍是当前建议链路的关键产物。
4. `scripts/long_memory_store.py` 对 execution memory 的读取边界仍限定在 execution sync 数据域。
