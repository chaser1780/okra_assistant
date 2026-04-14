# 基金多智能体研究系统设计与实施计划

- 文档版本：v2
- 更新日期：2026-03-09
- 数据根目录：`F:\okra_assistant`
- 代码目录：`F:\okra_assistant`

## 1. 目标

将当前“多智能体研究 + 规则校验 + 中文报告 + 复盘记忆”的基金研究系统，升级为：

- 更强的投研型 prompt 体系
- 更稳定的委员会式建议生成链路
- 可持续进化的复盘记忆闭环
- 未来可直接桌面化的本地研究工作台

## 2. 总体原则

- 大模型负责研究、归因、分歧讨论与建议草案。
- 规则层只做硬约束，不替代研究判断。
- 新增日志、快照、文档、缓存优先落到 `F:`。
- 尽量不新增 `C:` 占用；如需新增，仅保留最小代码变更。
- 每次建议都要可追溯、可复盘、可比较。

## 3. 分期实施

### Phase 1：Prompt / Schema 基础层

目标：

- 重构多智能体 prompt 为“岗位说明书”而不是一句话角色标签。
- 升级统一输出 schema，增强可复核性。
- 修正 `news_analyst` 角色错位问题。

执行内容：

1. 升级 `multiagent_utils.py` 通用 schema
2. 重构 `run_multiagent_research.py`
3. 新增 `fund_quality_analyst`
4. 新增 `portfolio_trader`
5. 更新 `agents.toml`

验收标准：

- 每个 agent 都输出：
  - `confidence`
  - `evidence_strength`
  - `data_freshness`
  - `abstain`
  - `portfolio_view`
  - `fund_views`
- 委员会链路可完整落盘到 `db/agent_outputs`

### Phase 2：委员会化最终建议

目标：

- 让最终建议更强依赖多智能体输出，而不是把 agent 仅当附加上下文。
- 降低大 prompt 流式失败概率。

执行内容：

1. 将 `portfolio_trader + research_manager + risk_manager` 设为委员会核心输入
2. 压缩 final summarizer prompt
3. fallback 从“manager_fallback”升级为“committee_fallback”

验收标准：

- 最终建议优先依赖委员会输出
- 流式失败时仍能生成高质量 fallback

### Phase 3：复盘记忆闭环

目标：

- 让 nightly review 不只统计结果，而是真正影响次日判断偏置。

执行内容：

1. 新增 `review_memory_agent`
2. 写入 `lessons`
3. 写入 `bias_adjustments`
4. 写入 `agent_feedback`
5. 在 `build_llm_context.py` 中回灌到 `memory_digest`

验收标准：

- memory 中出现可供第二天 prompt 使用的调整项
- 各 agent 输入能看到近期偏差与风险提醒

### Phase 4：桌面端产品化准备

目标：

- 在不重构研究引擎的前提下，准备桌面应用落地。

执行内容：

1. 输出桌面端 PRD
2. 明确页面信息架构
3. 明确任务触发、报告查看、交易录入、复盘查看交互
4. 规划 PySide6 本地桌面壳

验收标准：

- PRD 可直接指导 UI/桌面端开发

### Phase 5：减小 C 盘占用

目标：

- 在不影响功能前提下继续把增量占用转移到 `F:`

执行内容：

1. 文档全部落 `F:\okra_assistant\docs`
2. TEMP/TMP 指向 `F:\okra_assistant\temp`
3. 日志落 `F:\okra_assistant\logs`
4. Python 字节码尽量禁用或转移
5. 清理代码目录中已有 `__pycache__`

验收标准：

- 新增运行痕迹不再明显增长 `C:` 占用

## 4. 本轮立即执行项

- [x] 重写多智能体通用 schema
- [x] 重写多智能体 prompt 骨架
- [x] 新增 `fund_quality_analyst`
- [x] 新增 `portfolio_trader`
- [x] 强化最终建议委员会依赖
- [x] 新增 `review_memory_agent`
- [ ] 输出桌面端 PRD
- [ ] 清理现有 `__pycache__`
- [ ] 跑静态校验与一次 mock 验证

## 5. 当前目录影响

本轮重点修改：

- `F:\okra_assistant\scripts\multiagent_utils.py`
- `F:\okra_assistant\scripts\run_multiagent_research.py`
- `F:\okra_assistant\scripts\build_llm_context.py`
- `F:\okra_assistant\scripts\generate_llm_advice.py`
- `F:\okra_assistant\scripts\update_review_memory.py`
- `F:\okra_assistant\config\agents.toml`

## 6. 下一步

本轮代码层完成后，优先执行：

1. 静态编译检查
2. mock 运行委员会链路
3. 输出桌面端 PRD
4. 再决定是否进入 PySide6 壳层搭建
