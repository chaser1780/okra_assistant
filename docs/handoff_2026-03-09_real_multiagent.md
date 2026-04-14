# 续接记录 - 2026-03-10

## 当前结论

昨晚卡住的“真实多智能体最后两层”问题，今天已经实质收敛：

- `risk_manager` 已真实跑通
- `portfolio_trader` 已真实跑通
- `aggregate.json` 已恢复为全量 `all_agents_ok = true`

当前新的剩余问题已经切换为：

- **最终建议层 `generate_llm_advice.py` 仍会因 TabCode 中转连接问题走 `committee_fallback`**

## 今天已完成

### 1. 真实多智能体传输层修复

文件：

- `F:\okra_assistant\scripts\multiagent_utils.py`

改动：

- 从“请求流式响应但非流式读取”彻底改成“真正按 SSE 流式消费”
- 增加 `response.failed / error` 事件识别
- 增加 `stream_error` 场景下的部分恢复
- 增加失败现场日志到 `F:\okra_assistant\logs\llm`
- 增加 `direct` 与 `env_proxy` 双通道尝试
- 增加 `--use-existing` 场景下的依赖预加载

### 2. 真实 manager 层已跑通

已真实成功的 agent：

- `market_analyst`
- `theme_analyst`
- `fund_structure_analyst`
- `fund_quality_analyst`
- `news_analyst`
- `sentiment_analyst`
- `bull_researcher`
- `bear_researcher`
- `research_manager`
- `risk_manager`
- `portfolio_trader`

聚合结果：

- `F:\okra_assistant\db\agent_outputs\2026-03-09\aggregate.json`

当前状态：

- `all_agents_ok = true`
- `failed_agents = []`

### 3. 最终建议层已至少能稳定 fallback

文件：

- `F:\okra_assistant\scripts\generate_llm_advice.py`

现状：

- 真实 `generate_llm_advice.py` 仍未稳定拿到最终 LLM 总结正文
- 但会稳定落到 `committee_fallback`
- 当前 `committee_fallback` 已基于：
  - `portfolio_trader`
  - `research_manager`
  - `risk_manager`
  生成结构化建议

相关文件：

- `F:\okra_assistant\db\llm_advice\2026-03-09.json`
- `F:\okra_assistant\db\llm_raw\2026-03-09.json`

## 已确认的根因

### 根因 1：agent 层原先 SSE 读取方式不正确

这个问题已经修好。

### 根因 2：TabCode 中转对“大请求体 + SSE”更敏感

今天已观察到：

- `research_manager` 请求体量级约 `119 KB`
- `risk_manager` 请求体量级约 `133 KB`
- `portfolio_trader` 也存在较大的委员会输入体

在修复传输层后：

- manager 层仍会出现随机：
  - `server_error`
  - `SSLEOF`
  - `IncompleteRead`
- 但通过双通道重试与低冗长输出参数，已把这层真实跑通

### 根因 3：最终建议层仍在走旧的中转敏感路径

虽然今天已把 `generate_llm_advice.py` 部分迁移到新传输思路，但结果仍显示：

- `committee_fallback`
- 错误典型为：
  - `ProxyError`
  - `Remote end closed connection without response`

说明：

- 多智能体层已基本解决
- **最终总结层仍是下一阶段的主要稳定性瓶颈**

## 代理相关发现

昨天已确认本机存在本地代理痕迹：

- `127.0.0.1:10090`
- 监听进程：`libcore`

今天再次检查时，注册表状态显示：

- `ProxyEnable = 0`
- 但历史故障日志中仍出现明显代理相关报错

判断：

- 本地代理 / 中转环境仍是高可疑因素
- 但当前多智能体层已经通过“直连优先 + 代理回退”显著收敛

## 当前最有价值的结果

### 真实委员会输出已可用

可直接查看：

- `F:\okra_assistant\db\agent_outputs\2026-03-09\research_manager.json`
- `F:\okra_assistant\db\agent_outputs\2026-03-09\risk_manager.json`
- `F:\okra_assistant\db\agent_outputs\2026-03-09\portfolio_trader.json`

当前委员会共识大意：

- 先减法，再观望
- `022365`、`017193` 为高优先级收缩对象
- `024842` 为次级结构收敛对象
- `025857`、`001302` 仅保留，不追涨加仓

## 下一步优先做什么

### 1. 继续攻最终建议层

优先文件：

- `F:\okra_assistant\scripts\generate_llm_advice.py`

目标：

- 让最终总结层也像多智能体层一样稳定真实返回
- 尽量减少 `committee_fallback`

### 2. 重点检查

- `F:\okra_assistant\db\llm_raw\2026-03-09.json`
- `F:\okra_assistant\logs\llm`

关注：

- `direct` 与 `env_proxy` 哪条通道失败更多
- 是否仍出现 `ProxyError`
- 是否存在 `response.failed` 但无正文

### 3. 如果最终建议层仍不稳

再考虑：

- 给最终总结层加同样的失败现场日志
- 再确认是否需要单独的 manager/final 专用会话策略
- 最后再决定要不要动输入规模或总结方式

## 当前状态一句话

**真实多智能体已经完整跑通；剩余问题已从 `risk_manager` 切换为“最终建议层真实直出仍不稳定，当前主要依赖 committee_fallback”。**
