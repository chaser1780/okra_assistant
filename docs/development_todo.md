# okra assistant 开发任务拆解 TODO

- 文档定位：后续版本升级的执行清单
- 依据文档：`F:\okra_assistant\docs\improvement_recommendations.md`
- 更新日期：2026-03-11

## 状态说明

- `[todo]`：尚未开始
- `[doing]`：正在实施
- `[done]`：已完成
- `[blocked]`：存在外部依赖或等待决策

---

## A. P0：金融准确性与时间语义

### A1. 每日官方净值重估引擎

- 状态：`[done]`
- 目标：
  - 建立“按持有份额 × 官方净值”的每日组合重估步骤
  - 更新单基金与组合层市值、盈亏与估值日期
- 交付物：
  - 新增独立脚本执行每日官方净值重估
  - 更新 `portfolio.json`
  - 生成结构化重估结果文件
- 验收：
  - 每日可落一份重估快照
  - 组合 `total_value / holding_pnl / as_of_date` 与单基金数据同步更新
  - 缺失官方净值的基金会被明确标记

### A2. 夜间链路接入官方净值重估

- 状态：`[done]`
- 目标：
  - 将 A1 接入夜间主链路，形成固定收盘后更新
- 交付物：
  - 修改 `run_daily_pipeline.py --mode nightly`
  - 重估步骤进入夜间顺序编排
- 验收：
  - 夜间任务跑完后，持仓文件自动更新为最新官方口径

### A3. 在 UI / 报告中展示组合估值日期

- 状态：`[done]`
- 目标：
  - 清楚告诉用户当前组合市值对应哪一天
- 交付物：
  - Dashboard 增加组合估值日期
  - Settings 页增加估值产物路径
  - 夜间复盘卡可看到“今日是否已完成重估”
- 验收：
  - 用户能一眼区分：
    - 查看日期
    - 任务运行日期
    - 组合估值日期

### A4. 多周期复盘接入主链路

- 状态：`[done]`
- 目标：
  - 从当前 `horizon=0` 扩展到 `T+1 / T+5 / T+20`
- 交付物：
  - 接入 `review.toml`
  - 批量生成多周期 review result
  - 记忆更新时区分短期与中期经验
- 验收：
  - 复盘不再只看单日结果

### A5. stale / 时间语义统一

- 状态：`[done]`
- 目标：
  - 对实时估值、官方净值、代理行情统一表达新鲜度
- 交付物：
  - 全链路统一时间字段命名与 UI 展示规则
  - 对 stale 数据增加统一提示
- 验收：
  - 不同页面时间含义一致，不混淆

---

## B. P1：工程结构与可维护性

### B1. 核心 JSON 数据模型类型化

- 状态：`[done]`
- 目标：
  - 逐步用显式模型替代裸 `dict`
- 范围：
  - `llm_context`
  - agent output
  - final advice
  - validated advice
  - realtime snapshot
  - review memory
- 交付物：
  - `models/` 或统一 schema/model 层
- 验收：
  - 核心结构有静态字段边界

### B2. 配置漂移清理

- 状态：`[done]`
- 目标：
  - 收敛“配置存在但代码未使用”的问题
- 范围：
  - `agents.toml`
  - `review.toml`
  - `realtime_valuation.toml`
- 交付物：
  - 清理无效配置或正式接线
- 验收：
  - 代码行为与配置表达一致

### B3. Provider Adapter 层统一

- 状态：`[done]`
- 目标：
  - 给 quotes/news/proxy/estimate 建立统一 provider 接口
- 交付物：
  - provider adapter 基类或统一约定
  - 统一失败与 stale 处理
- 验收：
  - 后续替换数据源不需要改业务层

### B4. 运行元数据结构化

- 状态：`[done]`
- 目标：
  - 为每次运行生成结构化 manifest
- 交付物：
  - run id
  - step timing
  - model transport
  - failed step / failed agent
- 验收：
  - 性能、故障、运行历史可做程序化分析

### B5. 自动化测试体系

- 状态：`[done]`
- 目标：
  - 为主链路建立可回归验证
- 优先顺序：
  - `validate_llm_advice`
  - `build_realtime_profit`
  - `update_portfolio_from_trade`
  - `review_advice`
  - `run_multiagent_research` mock 路径
- 验收：
  - 主链路关键结构有测试保护

### B6. 桌面壳拆层

- 状态：`[done]`
- 目标：
  - 拆分 `desktop_shell.py`
- 拆分方向：
  - services
  - state
  - views
  - formatters
- 验收：
  - UI 可继续扩展而不继续堆单文件

### B7. 文档与编码清理

- 状态：`[done]`
- 目标：
  - 清理乱码、重复说明、陈旧文档
- 范围：
  - `references/source_priority.md`
  - 其他遗留乱码文件
- 验收：
  - 文档可直接用于开发交接

---

## C. P2：金融研究能力增强

### C1. 组合暴露分析增强

- 状态：`[done]`
- 目标：
  - 超越 `style_group`，增加真实组合风险画像
- 建议项：
  - 主题集中度
  - 风格集中度
  - 海外/国内暴露
  - QDII 风险
- 验收：
  - `risk_manager` 有更实质的组合层输入

### C2. 基金慢变量数据接入

- 状态：`[done]`
- 目标：
  - 为主动基金与部分指数基金补足中期质量数据
- 建议项：
  - 基金经理稳定性
  - 规模变化
  - 风格漂移
  - 回撤特征
  - 费率
- 验收：
  - `fund_quality_analyst` 不再主要依赖文字推断

### C3. 交易现实约束建模

- 状态：`[done]`
- 目标：
  - 使建议更贴近场外基金真实执行逻辑
- 范围：
  - 持有期限制
  - 赎回到账时滞
  - QDII 时差
  - 转换规则
- 验收：
  - 提高可执行性与复盘解释力

### C4. “无操作基线”复盘

- 状态：`[done]`
- 目标：
  - 不仅评估“做了是否对”，还评估“若不做会怎样”
- 交付物：
  - no-trade baseline compare
- 验收：
  - 系统价值评估更客观

---

## D. P3：用户体验与产品表达

### D1. Dashboard 三问式首页

- 状态：`[done]`
- 目标：
  - 直接回答：
    - 今天最重要看什么
    - 今天建议变了什么
    - 今天要不要操作

### D2. 建议变化解释

- 状态：`[done]`
- 目标：
  - 解释与上一日相比为什么改变

### D3. 交易前后对比页

- 状态：`[done]`
- 目标：
  - 交易录入后立即展示持仓变化前后对比

### D4. 异常告警层

- 状态：`[done]`
- 目标：
  - 对未生成、stale、agent 失败等情况进行显式提醒

### D5. 通俗版解释模式

- 状态：`[done]`
- 目标：
  - 给非专业用户提供简化阅读路径

---

## E. 推荐执行顺序

### 第 1 波（现在开始）

1. A1 每日官方净值重估引擎
2. A2 夜间链路接入官方净值重估
3. A3 在 UI / 报告中展示组合估值日期

### 第 2 波

1. A4 多周期复盘接入主链路
2. B2 配置漂移清理
3. B5 自动化测试体系基础版

### 第 3 波

1. B6 桌面壳拆层
2. B4 运行元数据结构化
3. C1 组合暴露分析增强

### 第 4 波

1. C2 基金慢变量数据接入
2. C3 交易现实约束建模
3. D1 / D2 / D3 / D4 / D5 产品表达增强

---

## F. 当前执行记录

- `2026-03-11`
  - `[done]` A1 每日官方净值重估引擎
  - `[done]` A2 夜间链路接入官方净值重估
  - `[done]` A3 在 UI / 报告中展示组合估值日期
  - `[done]` A4 多周期复盘接入主链路
  - `[done]` A5 stale / 时间语义统一
  - `[done]` B1 核心 JSON 数据模型类型化（TypedDict 模型骨架已接入关键模块）
  - `[done]` B2 配置漂移清理（`review.toml` / `agents.toml` / `realtime_valuation.toml` 已接线）
  - `[done]` B3 Provider Adapter 层统一（quotes/news/proxy/estimate 已接入统一 provider helper）
  - `[done]` B4 运行元数据结构化（pipeline / realtime manifest 已落盘）
  - `[done]` B5 自动化测试体系（已覆盖 freshness、配置接线、多周期复盘、规则校验、交易回写、官方净值重估、实时收益、多智能体 mock）
  - `[done]` B6 桌面壳拆层（已形成 task_state / task_runtime / ui_support 分层）
  - `[done]` B7 文档与编码清理（乱码参考文档已重写，docs 索引已建立）
  - `[done]` C1 组合暴露分析增强（已接入 llm_context / Dashboard / 组合报告）
  - `[done]` C2 基金慢变量数据接入（已接入基础画像 slow factors）
  - `[done]` C3 交易现实约束建模（已支持锁定金额 / 可卖金额 / 到账时效）
  - `[done]` C4 “无操作基线”复盘（已纳入 review result 与夜间报告）
  - `[done]` D1 Dashboard 三问式首页
  - `[done]` D2 建议变化解释
  - `[done]` D3 交易前后对比页
  - `[done]` D4 异常告警层
  - `[done]` D5 通俗版解释模式
  - 全部 TODO 已完成，下一步为最终全链路验证与收口
