# OKRA 统一向量 RAG 架构方案

> 面向右侧 OKRA 智能助手问答与未来每日分析链路的统一底层检索架构设计。
>
> 当前版本定位：产品 + 技术落地方案，供后续开发拆任务实现。

## 1. 背景与目标

OKRA 当前已经具备比较完整的本地投资研究工作流：

- 每日数据采集：基金净值、实时估值、代理 ETF、新闻、监管事件、源健康状态。
- 每日分析：`run_daily_pipeline.py` 生成多 Agent 分析、委员会输出、验证后建议。
- 长期记忆：`long_memory_store.py` 管理基金、市场、组合、执行等记忆域，并已经存在 SQLite + FTS5 全文索引。
- 右侧智能助手：`CopilotPanel.tsx -> POST /api/copilot/explain -> app/copilot_service.py`，当前主要把页面上下文压缩后直接交给 LLM。
- 现有证据检索：`scripts/evidence_index.py` 为每日 Agent 输入提供规则检索与打分，但不是统一向量索引。

用户希望先独立开发问答 RAG 链路，完整落地后再把每日分析等链路逐步迁移到 RAG 化。这个方向是合理的，但不能把它做成普通聊天知识库。OKRA 的投资场景有强约束：

- 日期不能穿越，历史日期问答与回测必须严格禁止未来数据。
- 基金不能错配，明确基金代码时不能拿相似主题基金替代。
- 持仓、净值、金额等数值必须来自结构化事实源，不能由向量召回文本推断。
- 长期记忆有状态、有效期、覆盖关系，不能让 archived/rejected 记忆默认复活。
- 真实交易和执行记忆不能污染基金画像、市场规律或系统建议胜率学习。

因此，本方案目标是建设一套 **统一、可审计、带硬过滤的向量 RAG 底座**：

- 短期先服务 OKRA 智能助手自然语言问答。
- 中期复用到每日分析 Agent 的证据获取。
- 长期让复盘、长期记忆、回测、执行解释共享同一个证据索引与检索协议。

## 2. 产品定位

### 2.1 OKRA 智能助手

右侧智能助手负责与用户交互，回答：

- 今天为什么建议加仓/减仓/观望某基金？
- 当前组合哪里偏离目标？
- 某基金最近风险来自哪里？
- 之前有没有类似经验或踩坑？
- 某次真实交易为什么和系统建议不同？
- 历史某一天系统为什么这么判断？

它的输出应当是解释型、证据引用型，而不是直接替代每日分析做交易决策。它可以解释、追问、指出缺数据、总结证据链，但涉及新交易建议时必须引用已有约束和每日分析结果，避免绕过验证链路。

### 2.2 每日分析 RAG 化

每日分析仍然由现有多 Agent 和委员会链路承担深度判断。RAG 化的作用是：

- 替代或增强 `scripts/evidence_index.py` 的规则检索。
- 让不同 Agent 按角色、日期、基金、证据域检索自己需要的材料。
- 保证 Agent 输入遵守无未来数据、基金匹配、来源优先级、记忆有效期等约束。
- 为每次分析输出可审计的 `retrieval_trace`，便于复盘。

### 2.3 统一底座

问答和每日分析不应各自维护一套索引。底层统一为：

- 统一文档切分模型。
- 统一 metadata schema。
- 统一 embedding 配置。
- 统一过滤与 rerank 策略。
- 统一检索 trace 和引用格式。

区别只在上层 retrieval profile：

- Copilot profile：面向用户问答，重视可解释、引用、缺证据说明。
- Agent profile：面向自动分析，重视角色证据覆盖、约束严格性和 token 预算。
- Review profile：面向复盘与历史经验，允许召回 archived/rejected 作为反例。

## 3. 现状链路与可复用资产

### 3.1 右侧智能助手现状

当前路径：

```text
frontend/src/components/okra/CopilotPanel.tsx
  -> frontend/src/lib/api.ts askCopilot()
  -> app/web_api.py OkraWebApi.explain()
  -> OkraWebApi._copilot_evidence()
  -> app/copilot_service.py call_copilot_llm()
```

当前 `_copilot_evidence()` 的核心行为：

- 读取 selected date 的 snapshot。
- 根据 page 取当前页面 payload。
- 对 payload 做 JSON 压缩。
- 如 fundDetail 且有 fundCode，则追加基金详情。

问题：

- 缺少独立检索层。
- 证据依赖当前页面，可回答范围受限。
- 没有统一引用、召回 trace、过滤条件记录。
- 不区分“当前问答”和“历史日期问答”的数据可见性。

### 3.2 长期记忆现状

`scripts/long_memory_store.py` 已有：

- `db/long_memory/memory.sqlite`：主记忆表。
- `db/long_memory/index.sqlite`：FTS5 全文索引。
- `memory_records` 字段：`domain`、`entity_key`、`status`、`confidence`、`valid_from`、`valid_until`、`metadata_json`、`evidence_refs_json` 等。
- `search_long_memory()`：基于 FTS5 的全文检索。

这部分可以作为 RAG 的一个 source adapter，不建议废弃。向量检索应读取同一套长期记忆记录，并尊重原有状态和生命周期。

### 3.3 每日分析现状

当前每日分析入口：

```text
scripts/today_orchestrator.py
  -> run_daily_pipeline.py
  -> build_llm_context.py
  -> run_multiagent_research.py
  -> agent_inputs.py
  -> evidence_index.retrieve_agent_evidence()
```

`scripts/evidence_index.py` 已经做了：

- 从 `llm_context` 构建 evidence entries。
- 按 fund_code、source_role、evidence_type、token 建索引。
- 针对不同 agent 设置 `ROLE_PREFERENCES`。
- 根据规则打分、返回 portfolio hits 和 fund hits。

问题：

- 主要是规则/关键词检索，不是向量检索。
- 只覆盖 `llm_context` 内的 evidence_items，不覆盖所有本地证据。
- 无统一 query intent、日期穿越防护和记忆生命周期控制。
- 不能直接服务自然语言问答。

结论：`evidence_index.py` 应作为旧检索能力迁移对象，第一阶段可并行保留，第二阶段由统一 RAG retriever 替代或包裹。

## 4. 总体架构

### 4.1 模块图

```text
                         +-------------------------+
                         |  OKRA Copilot UI        |
                         |  frontend right sidebar |
                         +-----------+-------------+
                                     |
                                     v
                         +-------------------------+
                         |  /api/copilot/explain   |
                         +-----------+-------------+
                                     |
                                     v
+------------------+     +-------------------------+     +------------------+
| Daily Analysis   | --> |  RAG Retrieval Service  | <-- | Debug / Admin    |
| Agent Inputs     |     |  app/rag_service.py     |     | /api/rag/search  |
+------------------+     +-----------+-------------+     +------------------+
                                     |
                +--------------------+--------------------+
                |                    |                    |
                v                    v                    v
      +------------------+  +------------------+  +------------------+
      | Query Planner    |  | Hard Filter      |  | Reranker         |
      | intent/date/fund |  | no future, scope |  | source/date/etc. |
      +------------------+  +------------------+  +------------------+
                                     |
                                     v
                         +-------------------------+
                         | Vector Store Adapter    |
                         | SQLite metadata +       |
                         | Chroma/FAISS/API embed  |
                         +-----------+-------------+
                                     |
        +----------------------------+-----------------------------+
        |              |             |              |              |
        v              v             v              v              v
 long_memory     llm_context     portfolio     decisions      execution
 memories        news/events     snapshots     committee      sync/review
```

### 4.2 新增核心模块建议

建议新增以下文件：

```text
app/rag_service.py
app/rag_query_planner.py
app/rag_answering.py

scripts/rag_models.py
scripts/rag_ingest.py
scripts/rag_index_store.py
scripts/rag_vector_store.py
scripts/rag_sources.py
scripts/rag_retriever.py
scripts/rag_rerank.py
scripts/rag_eval.py
```

职责：

- `rag_models.py`：定义 RAG 文档、chunk、metadata、query、hit、trace 的数据结构。
- `rag_sources.py`：从长期记忆、每日上下文、持仓、新闻、决策等数据源抽取标准文档。
- `rag_ingest.py`：按日期/域增量构建索引。
- `rag_vector_store.py`：封装 embedding API、向量库适配器。
- `rag_index_store.py`：维护 metadata、checksum、source manifest、重建状态。
- `rag_retriever.py`：执行硬过滤、向量召回、混合 rerank。
- `rag_query_planner.py`：把用户问题或 Agent profile 转成检索计划。
- `rag_answering.py`：把检索结果变成 LLM evidence pack。
- `rag_eval.py`：做固定问题集、无未来数据、基金错配等回归测试。

## 5. 数据模型设计

### 5.1 RAG Document

Document 是一个原始可索引证据单元，通常来自一个 JSON 节点、一条记忆、一条新闻、一只基金状态、一条决策。

建议字段：

```json
{
  "doc_id": "lm:portfolio:core_qdii_fixed_dca_only:5e252bda05f7",
  "source_kind": "long_memory",
  "source_path": "db/long_memory/memory.sqlite",
  "source_record_id": "portfolio:core_qdii_fixed_dca_only:5e252bda05f7",
  "title": "核心QDII仅允许固定定投",
  "text": "...",
  "summary": "...",
  "as_of_date": "2026-05-20",
  "event_date": "2026-05-08",
  "published_at": "",
  "valid_from": "2026-05-08",
  "valid_until": "",
  "entity_type": "portfolio",
  "entity_id": "core_qdii_fixed_dca_only",
  "fund_codes": ["016452", "017641"],
  "domains": ["portfolio"],
  "tags": ["core_dca", "us_qdii", "fixed_rule"],
  "status": "permanent",
  "confidence": 0.98,
  "source_tier": "memory_approved",
  "freshness_status": "valid",
  "is_stale": false,
  "is_negative_example": false,
  "visibility": "default",
  "payload": {}
}
```

### 5.2 RAG Chunk

Chunk 是实际 embedding 的文本片段。大多数短文档一条 doc 对应一个 chunk；大型报告或 agent 输出需要切多个 chunk。

```json
{
  "chunk_id": "lm:portfolio:...#c0",
  "doc_id": "lm:portfolio:...",
  "chunk_index": 0,
  "text_for_embedding": "标题：... 内容：... 标签：...",
  "text_for_llm": "可给模型引用的较完整证据文本",
  "token_estimate": 220,
  "metadata": {}
}
```

原则：

- embedding 文本应包含标题、实体、日期、标签、正文摘要。
- LLM 引用文本应尽量短，保留关键数值和出处。
- 不把大型 JSON 原样 embedding。
- 数值型事实必须保留结构化 payload，不能只变成自然语言。

### 5.3 Metadata 必填字段

统一 metadata 是本方案成败关键。建议所有 chunk 必填：

| 字段 | 用途 |
|---|---|
| `source_kind` | long_memory / llm_context / news / portfolio_state / validated_advice / committee_bundle / agent_output / execution_sync / review_result |
| `source_path` | 本地文件或表路径，便于审计 |
| `source_record_id` | 原始记录 id |
| `as_of_date` | 该证据被系统使用或生成的日期 |
| `event_date` | 证据描述事件发生日期 |
| `published_at` | 新闻/公告发布时间 |
| `available_from` | 系统最早可见时间，用于禁止未来数据 |
| `fund_codes` | 明确关联基金 |
| `entity_type` | fund / portfolio / market / execution / news / decision |
| `entity_id` | fund_code、规则 key、决策 id 等 |
| `domain` | fund / market / portfolio / execution / news / decision / system |
| `status` | memory status 或 source status |
| `valid_from` | 规则/记忆有效起点 |
| `valid_until` | 规则/记忆有效终点 |
| `superseded_by` | 被新记忆覆盖时记录 |
| `confidence` | 来源置信度 |
| `source_tier` | 来源等级 |
| `freshness_status` | same_day / previous_trading_day / stale / warning |
| `is_stale` | 是否陈旧 |
| `is_negative_example` | 是否反例 |
| `visibility` | default / review_only / debug_only |

### 5.4 Source Tier

建议定义来源等级，rerank 时使用：

| source_tier | 优先级 | 示例 |
|---|---:|---|
| `structured_current` | 100 | 当前持仓、官方净值、validated advice |
| `decision_trace` | 90 | committee bundle、agent output |
| `memory_approved` | 85 | permanent memory |
| `memory_strategic` | 75 | strategic memory |
| `official_notice` | 70 | 监管公告、基金公告 |
| `market_data` | 65 | quote、intraday proxy、estimated nav |
| `news_verified` | 55 | dedup 后新闻 |
| `memory_candidate` | 45 | candidate memory |
| `sentiment_signal` | 35 | 情绪/热度 |
| `negative_memory` | 30 | archived/rejected，仅历史复盘 |
| `debug_artifact` | 10 | 调试产物 |

## 6. 索引数据源

### 6.1 第一批必须索引

为了同时覆盖问答与每日分析底座，第一版索引以下源：

1. `db/long_memory/memory.sqlite`
   - permanent / strategic / candidate 默认索引。
   - archived / rejected 索引但 `visibility=review_only`，默认不召回。

2. `db/long_memory/exports/all_memory.json`
   - 作为兼容导出，不作为最终主源。
   - 若 SQLite 可读，以 SQLite 为准。

3. `db/llm_context/YYYY-MM-DD.json`
   - portfolio_summary
   - exposure_summary
   - constraints
   - memory_digest
   - news_digest
   - sentiment_digest
   - event_risks
   - funds
   - evidence_items

4. `db/portfolio_state/current.json` 与 `db/portfolio_state/snapshots/*.json`
   - 当前/历史持仓快照。
   - 每只基金一条文档，组合整体一条文档。

5. `db/validated_advice/YYYY-MM-DD.json`
   - tactical_actions
   - dca_actions
   - hold_actions
   - market_view
   - cross_fund_observations
   - optimization_summary

6. `db/committee_decision_bundle/YYYY-MM-DD.json`
   - committee decision
   - execution eligibility
   - degradation mode
   - notes

7. `db/agent_outputs/YYYY-MM-DD/aggregate.json`
   - 各 agent summary、fund_views、signal_cards、decision_cards。
   - 按 agent + fund_code 切分。

8. `db/execution_sync/**`
   - actual trades、pending confirmations、reconciliation。
   - domain=execution，默认仅用于执行解释、真实持仓解释和历史复盘。

### 6.2 第二批可索引

- `raw/news/YYYY-MM-DD.json`：原始新闻，可做更细粒度新闻检索。
- `db/review_results/*.json`：复盘结果。
- `db/replay_experiments/*.json`：回测和记忆影响实验。
- `reports/daily/*.md`：日报文本。
- `db/evidence_index/*.json`：旧 evidence index 兼容。

### 6.3 不建议直接索引的内容

- API key、config secret。
- 大型 runtime log 原文。
- lock 文件。
- 临时 stdout/stderr。
- 未清洗、编码损坏严重且无法修复的全文。

## 7. 向量与存储方案

### 7.1 Embedding 使用 API

用户已确认可以接受调用 API 做 embedding。建议在 `config/llm.toml` 中新增 embedding 配置：

```toml
[embedding]
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 1536
batch_size = 64
timeout_seconds = 60
cache_enabled = true
```

如果当前 provider 是 Responses 兼容代理，需要确认是否支持 embeddings endpoint。若代理不支持，允许单独配置：

```toml
[embedding_provider.OpenAI]
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
api_key_file = "F:\\okra_assistant\\config\\openai_api_key.txt"
```

### 7.2 Vector Store 选型

建议做适配层，第一版推荐两种路径：

#### 方案 A：Chroma

优点：

- 本地持久化简单。
- Python API 成熟。
- metadata filter 使用方便。
- 适合快速落地。

缺点：

- 引入依赖较多。
- 长期稳定性和迁移需要封装好。

#### 方案 B：SQLite metadata + FAISS vectors

优点：

- 本地轻量。
- 性能好。
- metadata 完全由 SQLite 控制。

缺点：

- Windows 依赖可能麻烦。
- metadata filter 需要先筛候选或维护分片。

建议：**业务层只依赖 `RagVectorStore` 接口，第一实现可用 Chroma；metadata/checksum/trace 仍落 SQLite。**

### 7.3 本地目录

建议新增：

```text
db/rag/
  rag.sqlite
  vector_store/
  manifests/
  traces/
  eval/
```

`rag.sqlite` 表：

- `rag_documents`
- `rag_chunks`
- `rag_embeddings`
- `rag_source_manifests`
- `rag_query_traces`
- `rag_ingest_runs`

### 7.4 Checksum 与增量更新

每条 document 计算：

```text
content_hash = sha256(source_kind + source_record_id + normalized_text + normalized_metadata)
```

索引时：

- hash 未变：跳过 embedding。
- hash 变化：更新 doc、chunk、embedding。
- 源文件删除：标记 inactive，不立即物理删除。
- 记忆状态变化：更新 metadata，必要时从 default visibility 降为 review_only。

## 8. 硬过滤策略

### 8.1 日期与无未来数据

这是最高优先级。

定义：

- `query_date`：用户或系统指定的分析日期。
- `available_from`：证据在系统中可见的时间。
- `as_of_date`：证据快照日期。
- `event_date`：事件发生日期。

规则：

1. 历史日期问答：
   - `available_from <= query_date end_of_day`
   - `as_of_date <= query_date`
   - `published_at <= query_date end_of_day`
   - 禁止读取 query_date 之后生成的 validated advice、memory、review。

2. 回测：
   - 更严格，使用 `available_from`，不能只看 `event_date`。
   - 例如 2026-05-18 的长期记忆即使描述 2026-05-08，也不能用于 2026-05-08 回测。

3. 当前问答：
   - 如果用户问“最新/现在”，允许使用最新 current。
   - 如果 UI selectedDate 是历史日期，但问题说“现在”，需要明确切换到 current profile，并在 trace 标注。

4. 每日分析：
   - intraday 模式：只能用当日已采集数据。
   - after_close 模式：可用收盘后生成的 validated、review、memory cycle。

### 8.2 基金过滤

如果问题显式包含基金代码或 fundDetail 页面传入 fundCode：

- 必须设置 `fund_codes contains fundCode OR entity_id == fundCode`。
- 允许组合级记忆作为辅助，但不能替代基金级证据。
- 若找不到该基金证据，返回缺证据。

如果问题是主题/行业：

- 可根据 style_group/theme_family 扩展候选基金。
- 扩展必须在 trace 中记录，例如 `expanded_from_theme=ai -> fund_codes=[011840,022365]`。

如果问题是组合：

- 不强制 fund_code。
- 优先 portfolio_state、exposure_summary、allocation_plan、portfolio memory。

### 8.3 记忆状态过滤

默认：

- include：`permanent`, `strategic`, `candidate`
- exclude：`archived`, `rejected`

历史经验/踩坑复盘：

- include：`archived`, `rejected`
- 但必须标 `is_negative_example=true`
- 答案中必须说明“这是历史反例/已废弃规则”，不能作为当前建议依据。

有效期：

- `valid_from <= query_date`
- `valid_until` 为空或 `valid_until >= query_date`
- `metadata.superseded_by` 存在时默认排除，除非历史复盘要求看演化过程。

### 8.4 执行边界

真实交易、支付宝持仓同步、pending confirmation：

- 可用于回答：
  - 当前真实持仓是多少？
  - 为什么系统记录和支付宝不同？
  - 某笔交易是否确认？
  - 执行偏差来自哪里？

- 不可用于：
  - 直接评价系统建议买对/买错。
  - 改写基金画像。
  - 改写市场规律。
  - 参与系统建议胜率学习。

RAG metadata 必须有：

```json
{
  "domain": "execution",
  "learning_scope": "execution_only"
}
```

每日分析默认不召回 execution domain，除非 portfolio_trader 或 execution review profile 明确要求。

### 8.5 数值事实优先结构化

以下问题不能只靠向量命中文本回答：

- 当前持仓金额。
- 收益率、盈亏、净值。
- 当日建议金额。
- 交易额度、现金底仓。
- 是否允许交易。

这些必须走结构化 source adapter：

- `portfolio_state`
- `validated_advice`
- `llm_context.constraints`
- `quote / estimated_nav / intraday_proxy`

向量检索只能补充解释性证据。

## 9. Query Planner

### 9.1 问答意图

建议识别以下 intent：

| intent | 示例 |
|---|---|
| `current_portfolio` | 我现在组合怎么样 |
| `fund_explain` | 为什么这只基金今天建议减仓 |
| `decision_explain` | 今天为什么是 hold_only |
| `risk_explain` | 风险来自哪里 |
| `news_explain` | 今天相关新闻有什么影响 |
| `memory_lookup` | 长期记忆里有没有类似规则 |
| `review_lesson` | 之前踩过类似坑吗 |
| `execution_explain` | 我实际操作和建议有什么偏差 |
| `historical_qa` | 5月8日为什么建议这样 |
| `backtest_replay` | 如果回到那天，系统能看到什么 |
| `data_freshness` | 数据是不是过期 |
| `debug_trace` | 这个答案用了哪些证据 |

### 9.2 Planner 输出

```json
{
  "query": "为什么今天不该继续加 AI？",
  "query_date": "2026-05-20",
  "time_mode": "current",
  "intent": "risk_explain",
  "fund_codes": ["011840"],
  "domains": ["portfolio", "market", "fund", "news", "decision", "memory"],
  "include_negative_memory": false,
  "allow_current_data": true,
  "allow_future_data": false,
  "require_structured_facts": true,
  "retrieval_profile": "copilot_qa",
  "top_k": 24
}
```

### 9.3 不确定时的处理

如果问题没有明确日期：

- UI 有 selectedDate：默认 selectedDate。
- 如果用户说“现在/最新”：使用 current。
- 如果 selectedDate 不是最新，但用户问题含“今天”，使用 selectedDate 并在答案里显示日期。

如果基金名模糊：

- 先在 portfolio/watchlist/funds 中解析。
- 多个候选时返回澄清问题。
- 不要直接用主题相似度猜。

## 10. Rerank 设计

最终分数：

```text
final_score =
  vector_similarity * 0.45
  + source_tier_score * 0.18
  + date_fit_score * 0.14
  + entity_match_score * 0.12
  + freshness_score * 0.05
  + confidence_score * 0.04
  + diversity_score * 0.02
  - penalties
```

惩罚：

- stale 且问题要求最新：强惩罚。
- 基金不匹配：强惩罚或直接过滤。
- archived/rejected 非复盘场景：直接过滤。
- superseded：默认过滤。
- source_health warning：轻惩罚。
- 同 URL/同标题重复新闻：去重。

对于每日分析 Agent，权重可按角色调整：

- news_analyst：news/official_notice 权重高。
- risk_manager：风险、stale、crowding、regulatory 权重高。
- portfolio_trader：constraints、validated、portfolio_state、execution eligibility 权重高。
- market_analyst：proxy、quote、market_news、regime memory 权重高。

## 11. Copilot 问答链路设计

### 11.1 新链路

```text
OkraWebApi.explain(payload)
  -> RagQueryPlanner.plan_copilot_query()
  -> RagRetriever.retrieve()
  -> build_copilot_evidence_pack()
  -> call_copilot_llm()
  -> return answer + citations + trace_id
```

### 11.2 API 返回

当前 `askCopilot()` 返回：

```json
{
  "answer": "...",
  "mode": "llm",
  "sourceDate": "2026-05-20"
}
```

建议扩展为：

```json
{
  "answer": "...",
  "mode": "rag_llm",
  "sourceDate": "2026-05-20",
  "traceId": "ragq_...",
  "citations": [
    {
      "citation_id": "C1",
      "title": "...",
      "source_kind": "validated_advice",
      "source_path": "db/validated_advice/2026-05-20.json",
      "as_of_date": "2026-05-20",
      "fund_codes": ["011840"]
    }
  ],
  "retrieval": {
    "intent": "fund_explain",
    "filters": {},
    "hitCount": 12,
    "missingData": []
  }
}
```

前端可以先只展示 answer，后续显示 citations。

### 11.3 Prompt 约束

Copilot system prompt 需要改为：

- 只基于 evidence pack 回答。
- 先给结论，再给证据和风险。
- 引用证据编号。
- 如果缺少当日 validated advice、持仓或行情，必须说明缺什么。
- archived/rejected 只能称为历史反例，不能当作当前规则。
- 不得编造净值、收益、新闻或交易结论。

## 12. 每日分析接入设计

### 12.1 第一阶段：并行影子检索

不直接替换 `evidence_index.py`。先在 `run_daily_pipeline.py` 中生成统一 RAG index，并在 `agent_inputs.py` 中增加可选字段：

```json
{
  "rag_retrieved_evidence": {...},
  "rag_retrieval_trace_id": "..."
}
```

旧字段 `retrieved_evidence` 保留。

验证：

- 比较旧检索和新 RAG 对每个 Agent 的证据覆盖。
- 检查是否引入未来数据。
- 检查基金级证据是否错配。

### 12.2 第二阶段：Agent Profile 化

为每个 Agent 定义 retrieval profile：

```toml
[rag.agent_profiles.market_analyst]
domains = ["market", "news", "fund"]
source_kinds = ["llm_context", "news", "portfolio_state", "long_memory"]
top_k_portfolio = 8
top_k_per_fund = 3
allow_negative_memory = false

[rag.agent_profiles.risk_manager]
domains = ["market", "portfolio", "news", "memory"]
prefer_evidence_types = ["regulatory_notice", "risk_event", "stale_data", "crowding"]
top_k_portfolio = 12
```

### 12.3 第三阶段：替换旧 evidence_index

当 RAG 检索通过回归测试后：

- `scripts/evidence_index.py` 降级为 fallback。
- `agent_inputs.attach_retrieved_evidence()` 改为调用 `rag_retriever.retrieve_for_agent()`。
- 输出结构保持兼容，避免大改 Agent prompt。

## 13. 需要重构的旧代码影响

### 13.1 `app/web_api.py`

影响：

- `OkraWebApi.explain()` 增加 RAG 调用。
- `_copilot_evidence()` 从页面压缩升级为 `build_copilot_rag_pack()`。
- 增加 `/api/rag/search` 调试接口。
- 增加 `/api/rag/reindex` 可选管理接口。

兼容策略：

- RAG 失败时 fallback 到现有 local_copilot_answer。
- API 返回保留 `answer/mode/sourceDate`。

### 13.2 `app/copilot_service.py`

影响：

- system prompt 改成 evidence-grounded。
- user prompt 从 pageData 改为 evidence pack。
- 支持 citations。

需要顺手修复：

- 当前文件中中文字符串存在明显 mojibake，应在改 prompt 时统一修复为 UTF-8 中文。

### 13.3 `frontend/src/components/okra/CopilotPanel.tsx`

影响：

- 显示 citations。
- 显示 mode：RAG / local fallback。
- 可增加“证据来源”折叠区。
- 可增加“按当前日期回答/按最新回答”切换。

第一版可以不改 UI，仅接收 answer。

### 13.4 `scripts/evidence_index.py`

影响：

- 第一阶段保留。
- 第二阶段迁移 ROLE_PREFERENCES 到 RAG agent profiles。
- 第三阶段作为 fallback 或移除每日主链路依赖。

### 13.5 `scripts/build_llm_context.py`

影响：

- 不建议让它直接负责 embedding。
- 可以在生成 `llm_context` 后触发 `rag_ingest.py --date`。
- `llm_context` 里的 evidence_items 可作为 RAG source adapter 的输入。

### 13.6 `scripts/today_orchestrator.py`

影响：

- 在 `run_daily_pipeline.py` 前后加入 RAG 索引刷新。
- after_close memory cycle 后再次刷新长期记忆索引。
- runtime 中增加 `rag_index_status`。

### 13.7 `scripts/long_memory_store.py`

影响：

- `upsert_memory_record()` 后可触发 RAG memory doc 更新。
- 或者先由 nightly/手动 ingest 增量同步。
- 保留现有 FTS5，不必强行替换。

### 13.8 配置文件

新增：

```text
config/rag.toml
```

内容包括：

- embedding provider
- vector backend
- source enable/disable
- default filters
- profile definitions
- top_k/token budget
- retention

## 14. 全项目 LLM 调用接入矩阵

统一 RAG 底座的最终目标不是只让右侧 Copilot 更会聊天，而是让 **项目里所有需要文本证据的大模型调用** 都走同一个检索、过滤、引用、trace 协议。这样后续新增 Agent、复盘任务、长期记忆任务、问答入口时，不再各自拼 prompt、各自读文件、各自承担日期穿越和基金错配风险。

### 14.1 统一调用原则

所有文本型 LLM 调用应逐步收敛到同一套调用前置流程：

```text
业务入口
  -> build_rag_query_plan()
  -> retrieve_rag_evidence()
  -> build_evidence_pack()
  -> call_llm_with_evidence()
  -> persist answer + citations + retrieval_trace
```

原则：

- LLM 不直接自由读取本地文件，只读取经过 RAG hard filter 和 source adapter 处理后的 evidence pack。
- 结构化事实先读结构化 source adapter，再由 RAG 提供解释性补充。
- 任何涉及历史日期、回测、复盘的问题，默认启用 `allow_future_data=false`。
- 明确基金代码时，`fund_code` 是硬约束，不允许用主题相似基金替代主证据。
- execution 数据默认只服务 execution 问答、执行偏差解释、真实持仓对账，不进入基金画像、市场规律和系统建议胜率学习。
- 视觉/OCR 类调用可以使用 RAG 提供约束和字段解释，但图片内容本身仍由 vision parser 处理，不能把截图当普通文本知识库。

### 14.2 现有 LLM 调用入口与改造目标

| 入口 | 当前文件 | 当前行为 | RAG 改造目标 | 优先级 |
|---|---|---|---|---|
| 右侧 Copilot 问答 | `app/web_api.py`、`app/copilot_service.py` | 压缩当前页面 payload 后直接交给 LLM | 改为 Copilot profile 检索 evidence pack，返回 citations/trace | P0 |
| 多 Agent 每日研究 | `scripts/run_multiagent_research.py`、`scripts/agent_inputs.py` | 使用 `evidence_index.py` 规则检索 + agent prompt | 先 shadow 注入 `rag_retrieved_evidence`，通过评估后替代默认 evidence | P1 |
| 最终建议生成 | `scripts/generate_llm_advice.py` | 汇总 agent aggregate 和 committee bundle | 使用 decision profile 检索约束、当日证据、历史相似情形，但不绕过 committee | P1 |
| 长期记忆分析 | `scripts/run_long_memory_analysis.py` | 从 validated/review/agent 输出提炼记忆 | 使用 memory profile 检索已有记忆和 superseded 关系，避免重复、冲突和记忆复活 | P1 |
| 复盘与回放 | `scripts/review_advice.py`、`scripts/run_replay_experiment.py` | 读取 advice、review result、ledger | 使用 review profile，允许 archived/rejected 作为反例，并强制标注 negative example | P2 |
| 支付宝持仓截图解析 | `scripts/sync_portfolio_from_screenshots.py` | vision 模型解析截图 | RAG 仅提供基金清单、字段定义、执行边界；图片 OCR 结果不进入普通 RAG | P2 |
| preflight 探测 | `scripts/preflight_check.py` | 小模型连通性探测 | 不需要 RAG，只记录 embedding endpoint 可用性 | P3 |

### 14.3 新增统一服务边界

建议将 RAG 调用边界分为两层：

```text
scripts/rag_*.py     # 可被 CLI、daily pipeline、测试直接调用
app/rag_*.py         # Web API / Copilot 的轻封装
```

`scripts/` 层负责确定性能力：

- 读取配置。
- 抽取标准文档。
- 写入索引。
- 执行过滤、召回、rerank。
- 写 retrieval trace。
- 提供 CLI 和测试入口。

`app/` 层负责产品接口：

- 将前端 payload 转成 RAG query。
- 调用 `scripts` 层服务。
- 拼接 Copilot evidence pack。
- 暴露 `/api/rag/search`、`/api/rag/reindex`、`/api/rag/trace`。
- 保持现有 `/api/copilot/explain` 返回兼容。

## 15. 详细实施路线

下面的阶段按“先底座、再问答、再影子接入、最后替换主链路”的顺序执行。每一步都要有可回退开关，避免一次性重写当前稳定链路。

### Phase 0：配置、开关与目录骨架

目标：先把 RAG 作为项目级能力注册进配置和目录，不影响现有运行。

新增文件：

```text
config/rag.toml
scripts/rag_models.py
scripts/rag_config.py
scripts/rag_index_store.py
scripts/rag_vector_store.py
tests/test_rag_config.py
tests/test_rag_index_store.py
```

`config/rag.toml` 第一版建议：

```toml
[rag]
enabled = false
default_profile = "copilot_qa"
index_dir = "db/rag"
trace_enabled = true
fallback_to_legacy = true

[rag.embedding]
enabled = false
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 1536
batch_size = 64
timeout_seconds = 60
cache_enabled = true
dry_run = true

[rag.vector_store]
backend = "sqlite_mock"
sqlite_path = "db/rag/rag.sqlite"
allow_chroma = false
allow_faiss = false

[rag.sources]
long_memory = true
portfolio_state = true
llm_context = true
evidence_index = true
validated_advice = true
committee_bundle = true
agent_outputs = false
execution_sync = false
raw_news = false

[rag.safety]
require_available_from = true
require_source_path = true
exclude_archived_by_default = true
exclude_rejected_by_default = true
exclude_execution_by_default = true
```

工作步骤：

1. 在 `scripts/common.py` 中新增 `rag_dir()`、`rag_db_path()`、`rag_trace_dir()`、`rag_manifest_path()` 路径 helper，或先在 `rag_config.py` 内部实现，避免过早污染公共模块。
2. `rag_models.py` 定义 `RagDocument`、`RagChunk`、`RagQueryPlan`、`RagHit`、`RagTrace`，第一版用 `TypedDict` 或 dataclass 均可，但字段名必须稳定。
3. `rag_config.py` 读取 `config/rag.toml`，缺文件时返回安全默认值：`enabled=false`、`dry_run=true`。
4. `rag_index_store.py` 初始化 `db/rag/rag.sqlite`，表结构至少包括 `documents`、`chunks`、`source_manifest`、`embedding_cache`、`traces`。
5. `rag_vector_store.py` 第一版实现 `sqlite_mock`：不调用 API，只保存 checksum 和伪向量状态，保证 dry-run 可测试。

SQLite 表建议：

```sql
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  as_of_date TEXT NOT NULL,
  event_date TEXT NOT NULL DEFAULT '',
  published_at TEXT NOT NULL DEFAULT '',
  available_from TEXT NOT NULL,
  entity_type TEXT NOT NULL DEFAULT '',
  entity_id TEXT NOT NULL DEFAULT '',
  fund_codes_json TEXT NOT NULL DEFAULT '[]',
  domain TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  valid_from TEXT NOT NULL DEFAULT '',
  valid_until TEXT NOT NULL DEFAULT '',
  source_tier TEXT NOT NULL DEFAULT '',
  visibility TEXT NOT NULL DEFAULT 'default',
  learning_scope TEXT NOT NULL DEFAULT '',
  is_negative_example INTEGER NOT NULL DEFAULT 0,
  content_sha256 TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text_for_embedding TEXT NOT NULL,
  text_for_llm TEXT NOT NULL,
  token_estimate INTEGER NOT NULL DEFAULT 0,
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_status TEXT NOT NULL DEFAULT 'pending',
  embedding_sha256 TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
);
```

验收：

- `python -m unittest discover -s tests -p test_rag_config.py`
- `python -m unittest discover -s tests -p test_rag_index_store.py`
- 删除 `config/rag.toml` 时，现有 daily pipeline 和 Copilot 行为不变。
- 初始化 `db/rag/rag.sqlite` 不需要网络和 API key。

回退策略：

- `rag.enabled=false` 时所有新增代码只作为 CLI/debug 能力存在。
- `fallback_to_legacy=true` 时任何 RAG 错误都不阻断 Copilot 和 daily pipeline。

### Phase 1：Source Adapter 与标准文档抽取

目标：把当前项目已有产物转换成统一 `RagDocument/RagChunk`，先不做真实 embedding。

新增文件：

```text
scripts/rag_sources.py
scripts/rag_ingest.py
tests/test_rag_sources.py
tests/test_rag_ingest.py
```

第一批 source adapter：

| Adapter | 输入 | 输出粒度 | 默认 visibility | 注意事项 |
|---|---|---|---|---|
| `long_memory_documents()` | `db/long_memory/memory.sqlite` | 一条 memory 一条 doc | `default` 或 `review_only` | 尊重 `status/valid_from/valid_until/superseded_by` |
| `portfolio_documents()` | `db/portfolio_state/current.json`、`snapshots/*.json` | 组合整体 + 每只基金 | `default` | 数值保留在 payload，不靠文本推断 |
| `llm_context_documents()` | `db/llm_context/YYYY-MM-DD.json` | summary、constraints、digest、fund rows | `default` | `available_from` 等于 context 生成时间或文件日期 |
| `evidence_item_documents()` | `llm_context.evidence_items` 或 `db/evidence_index` | 一条 evidence 一条 doc | `default` | 继承 `fund_codes/evidence_type/source_tier/stale` |
| `validated_advice_documents()` | `db/validated_advice/YYYY-MM-DD.json` | market view + 每条 action | `default` | 决策事实优先级高于普通新闻 |
| `committee_bundle_documents()` | `db/committee_decision_bundle/YYYY-MM-DD.json` | bundle + 每只基金 decision | `default` | 用于解释“为什么这么决策” |

暂缓 source adapter：

- `agent_outputs`: 体积大、结构复杂，Phase 2 以后再接，先只使用 `aggregate` 中 committee-ready 的压缩字段。
- `raw/news`: 第一版先用 `llm_context.evidence_items` 中已清洗新闻，避免重复和噪声。
- `execution_sync`: Phase 3 单独做 execution profile，默认隔离。
- `llm_raw/logs`: 不索引。

工作步骤：

1. 为每个 adapter 设计 `iter_*_documents(agent_home, date=None)` 生成器。
2. 每条 doc 必须填 `source_kind/source_path/source_record_id/doc_id/available_from/as_of_date/domain/source_tier`。
3. `available_from` 规则：
   - 文件有 `generated_at/retrieved_at/updated_at` 时优先使用。
   - 历史 artifact 缺 timestamp 时使用文件日期的 `23:59:59+08:00`，并在 trace 中标 `available_from_inferred=true`。
   - 新闻必须使用 `published_at` 与 `retrieved_at` 双字段，历史查询 hard filter 用 `available_from`。
4. `content_sha256` 由关键 payload 和 `text_for_llm` 生成，避免无意义重嵌。
5. `rag_ingest.py` 支持：

```powershell
python scripts\rag_ingest.py --date 2026-05-20 --domain long_memory --domain portfolio --dry-run
python scripts\rag_ingest.py --date 2026-05-20 --all --dry-run
python scripts\rag_ingest.py --date 2026-05-20 --all --write
```

验收：

- 2026-05-20 的 `llm_context` 能抽出不少于 `evidence_items` 数量的 evidence docs。
- `long_memory` 中 `permanent/strategic/candidate` 默认可检索，`archived/rejected` 默认 `visibility=review_only`。
- 同一文件重复 ingest 不重复写入，checksum 不变则不更新 chunk。
- `execution_sync` 在默认配置下不会被 ingest。

回退策略：

- adapter 失败时记录 source manifest error，不影响其他 adapter。
- `rag_ingest.py --dry-run` 输出将要写入的 doc count、chunk count、跳过原因。

### Phase 2：Embedding Client、向量存储与混合召回

目标：在保留 SQLite metadata 主控的基础上，接入真实 embedding 或本地 mock，并实现可替换 vector backend。

新增或完善：

```text
scripts/rag_embedding_client.py
scripts/rag_vector_store.py
scripts/rag_retriever.py
scripts/rag_rerank.py
tests/test_rag_embedding_client.py
tests/test_rag_retriever_filters.py
```

工作步骤：

1. `rag_embedding_client.py` 读取 `[rag.embedding]` 和可选 `[embedding_provider.*]`。
2. 如果当前 Responses 代理不支持 embeddings endpoint，则允许单独配置 embedding base URL 和 key file。
3. embedding 请求只发送 `text_for_embedding`，不发送完整 `payload_json`、截图 OCR 原文、交易流水明细。
4. `embedding_cache` 按 `embedding_model + text_sha256` 缓存。
5. `rag_vector_store.py` 提供统一接口：

```python
class RagVectorStore:
    def upsert(self, chunks: list[RagChunk], vectors: list[list[float]]) -> None: ...
    def search(self, query_vector: list[float], *, filters: dict, top_k: int) -> list[VectorCandidate]: ...
    def delete_missing(self, manifest_id: str) -> None: ...
```

6. 第一版 backend 优先级：
   - `sqlite_mock`: dry-run 和测试。
   - `chroma`: 快速落地真实向量。
   - `sqlite_faiss`: 后续优化，不作为第一批阻塞项。
7. `rag_retriever.py` 先执行 hard filters，再执行向量召回；如果 backend 不支持复杂 metadata filter，则先用 SQLite 选候选 doc/chunk，再向 vector store 查询候选集合。
8. `rag_rerank.py` 实现文档中的 score，但第一版权重写入 `config/rag.toml`，方便调整。

验收：

- embedding API 不可用时，RAG 可降级为 FTS/mock，不阻断 pipeline。
- query embedding 失败时，Copilot fallback 到旧页面上下文回答。
- 单次 ingest 对 unchanged chunks 不重复调用 embedding。
- 检索结果 trace 中包含 backend、embedding_model、candidate_count、filtered_count。

回退策略：

- `rag.embedding.enabled=false` 时走 FTS/mock。
- `rag.vector_store.backend` 可从 `chroma` 切回 `sqlite_mock`。
- 所有真实 embedding 调用前先跑 `preflight_check.py --scope rag`。

### Phase 3：硬过滤、Query Planner 与 Trace

目标：把 OKRA 投资场景的业务约束放到检索层，而不是指望 prompt 自觉。

新增或完善：

```text
app/rag_query_planner.py
scripts/rag_query_planner.py
scripts/rag_trace.py
tests/test_rag_no_future.py
tests/test_rag_fund_match.py
tests/test_rag_memory_visibility.py
tests/test_rag_execution_boundary.py
```

Query plan 必须包含：

```json
{
  "query": "...",
  "query_date": "2026-05-20",
  "time_mode": "current|selected_date|historical|backtest",
  "intent": "fund_explain",
  "fund_codes": ["011840"],
  "domains": ["portfolio", "fund", "news", "decision", "memory"],
  "retrieval_profile": "copilot_qa",
  "allow_future_data": false,
  "include_negative_memory": false,
  "include_execution": false,
  "require_structured_facts": true,
  "top_k": 24,
  "token_budget": 6000
}
```

硬过滤规则：

1. 日期：
   - `available_from <= query_date end_of_day`。
   - `as_of_date <= query_date`。
   - `published_at <= query_date end_of_day`。
   - `generated_at` 晚于 query date 的 validated/review/memory 默认不可见。
2. 基金：
   - 明确 `fund_code` 时，主证据必须 `fund_codes contains fund_code` 或 `entity_id == fund_code`。
   - 组合级证据允许作为辅助，但 trace 标 `scope=portfolio_supporting`。
   - 主题扩展必须记录 `expanded_from_theme`，不能静默替代。
3. 记忆：
   - 默认 include `permanent/strategic/candidate`。
   - `archived/rejected` 只有 review profile 或 explicit 复盘问题可见。
   - `superseded_by` 存在时默认排除。
4. execution：
   - 默认 `include_execution=false`。
   - execution profile 仅用于真实交易、待确认、对账、执行偏差。
   - `learning_scope=execution_only` 的 doc 不进入 fund/market/decision profile。
5. 陈旧数据：
   - `stale=true` 不一定过滤，但必须降低权重并在 evidence pack 标注。
   - 如果问题问“最新/现在”，陈旧数据只能作为背景。

Trace 文件：

```text
db/rag/traces/YYYY-MM-DD/{trace_id}.json
```

Trace 必填字段：

- `trace_id`
- `created_at`
- `caller`
- `query_plan`
- `hard_filters`
- `source_manifest_ids`
- `candidate_count_before_filter`
- `candidate_count_after_filter`
- `rejected_samples`
- `final_hits`
- `missing_data`
- `token_budget`
- `evidence_pack_sha256`
- `answer_citation_ids`
- `fallback_reason`

验收：

- 历史日期查询不会召回未来 validated advice、未来 memory、未来 portfolio snapshot。
- 明确基金代码时，top hits 中主证据不出现其他基金。
- 普通 Copilot 问答不会召回 execution actual trades。
- “有没有踩坑/历史反例”才允许 archived/rejected，并在 hit 上标 `is_negative_example=true`。

回退策略：

- Query planner 不确定基金时，返回澄清问题或只用组合级证据，不做主题猜测。
- hard filter 过滤到 0 条时，返回 `missingData`，不放宽到未来数据或错配基金。

### Phase 4：Copilot RAG 接入

目标：右侧智能助手成为第一个真实消费方，回答带引用、可追踪、可回退。

修改文件：

```text
app/web_api.py
app/copilot_service.py
app/rag_service.py
app/rag_answering.py
frontend/src/lib/types.ts
frontend/src/lib/api.ts
frontend/src/components/okra/CopilotPanel.tsx
tests/test_web_api_rag_copilot.py
```

工作步骤：

1. 新增 `app/rag_service.py`：
   - `build_copilot_rag_pack(payload) -> dict`
   - 内部调用 planner、retriever、answering。
2. `OkraWebApi.explain()` 流程改为：

```text
_copilot_evidence()
  -> build_copilot_rag_pack()
  -> call_copilot_llm(context, question, evidence_pack)
  -> return answer + citations + retrieval
```

3. 保留旧 `_copilot_evidence()` 作为 fallback，并作为页面上下文补充，而不是唯一证据。
4. `call_copilot_llm()` prompt 改为 evidence-grounded：
   - 只能基于 evidence pack 回答。
   - 必须引用 `[C1]`、`[C2]`。
   - 缺少 validated advice、持仓、行情、新闻时必须说明。
   - 不得根据 actual trade 推断系统建议对错。
5. API 返回兼容扩展：

```json
{
  "answer": "...",
  "mode": "rag_llm",
  "sourceDate": "2026-05-20",
  "traceId": "ragq_...",
  "citations": [],
  "retrieval": {
    "intent": "fund_explain",
    "hitCount": 12,
    "missingData": []
  }
}
```

6. 前端第一步只接收并保存 citations，不强制展示；第二步增加“证据来源”折叠区。
7. `_copilot_evidence.page_payloads` 补齐 `execution`、`intelligence`、`fundDetail` 等页面映射，避免不识别页面时回落 dashboard。

验收：

- `askCopilot()` 旧调用不报错。
- RAG 关闭时返回 `mode=llm` 或 `local_fallback`，行为接近当前版本。
- RAG 开启时返回 `mode=rag_llm`、`traceId`、`citations`。
- 问“今天为什么不建议继续加仓某基金”能引用持仓、validated advice、当日 evidence、相关长期记忆。
- 问“这个回答用了哪些证据”能返回 trace 摘要。

回退策略：

- RAG 异常：fallback 到当前 `_copilot_evidence()`。
- LLM 异常：fallback 到 `local_copilot_answer()`，但本地摘要中附 `retrieval.missingData`。

### Phase 5：每日多 Agent Shadow 接入

目标：不改变每日建议输出的前提下，让 RAG 与旧 `evidence_index.py` 并行跑，收集对比结果。

修改文件：

```text
scripts/agent_inputs.py
scripts/run_multiagent_research.py
scripts/run_daily_pipeline.py
scripts/rag_eval.py
tests/test_rag_agent_shadow.py
tests/test_pipeline_logic.py
```

工作步骤：

1. 在 `config/rag.toml` 增加：

```toml
[rag.agent_shadow]
enabled = false
write_trace = true
inject_into_prompt = false
compare_legacy = true
```

2. `run_daily_pipeline.py` 在 `build_evidence_index.py` 后新增可选步骤：

```text
rag_ingest.py --date {date} --daily
rag_eval.py --date {date} --compare-legacy
```

3. `STEP_OUTPUT_CHECKS` 增加 `rag_ingest.py` 的 outputs/inputs：
   - 输出：`db/rag/manifests/{date}.json`
   - 输入：`llm_context`、`evidence_index`、`validated_advice`、`committee_bundle`、`long_memory_export`
4. `agent_inputs.attach_retrieved_evidence()` 在 shadow 开启时额外写：

```json
{
  "rag_retrieved_evidence": {...},
  "rag_retrieval_trace_id": "...",
  "rag_legacy_diff": {...}
}
```

5. `inject_into_prompt=false` 时，不把 RAG 证据放入 agent prompt，只写到 aggregate/debug artifact。
6. `rag_eval.py` 对比：
   - legacy top hits vs RAG top hits。
   - fund match rate。
   - source coverage。
   - stale hit count。
   - token budget。
   - no-future violation。

验收：

- Shadow 开启后，每日分析最终 `validated_advice` 不因 RAG 变化。
- 每个 agent 有独立 `trace_id`。
- `rag_eval` 输出 `db/rag/eval/YYYY-MM-DD.json`。
- 旧 `evidence_index.py` 仍是默认主输入。

回退策略：

- `rag.agent_shadow.enabled=false` 即完全关闭。
- RAG eval 失败只标 degraded，不阻断 daily pipeline，除非显式 `--rag-strict`。

### Phase 6：Agent Profile 化与默认接入

目标：当 shadow 评估稳定后，让不同 Agent 使用不同 RAG profile，同时保留旧检索 fallback。

新增配置：

```toml
[rag.agent_profiles.market_analyst]
domains = ["market", "news", "fund"]
source_kinds = ["llm_context", "evidence_item", "long_memory"]
prefer_evidence_types = ["quote_snapshot", "intraday_proxy", "market_news", "policy_news"]
top_k_portfolio = 8
top_k_per_fund = 3
allow_negative_memory = false
include_execution = false

[rag.agent_profiles.risk_manager]
domains = ["market", "portfolio", "news", "memory"]
prefer_evidence_types = ["regulatory_notice", "risk_event", "stale_data", "crowding"]
top_k_portfolio = 12
top_k_per_fund = 4
allow_negative_memory = false
include_execution = false

[rag.agent_profiles.portfolio_trader]
domains = ["portfolio", "decision", "fund", "market"]
prefer_source_tiers = ["structured_current", "decision_trace", "market_data"]
top_k_portfolio = 10
top_k_per_fund = 4
include_execution = false
```

工作步骤：

1. 将 `evidence_index.ROLE_PREFERENCES` 映射到 `rag.agent_profiles`，不要一次删除旧常量。
2. `agent_inputs.py` 默认读 RAG profile；RAG 失败或 hit 不足时回退 legacy `retrieve_agent_evidence()`。
3. `run_multiagent_research.py` 的 `workflow_meta` 记录：
   - `retrieval_backend`
   - `rag_enabled`
   - `fallback_used`
   - 每个 agent 的 `trace_id`
4. 对 agent prompt 做最小修改：字段名兼容 `retrieved_evidence`，新增 `rag_retrieved_evidence` 时不破坏旧模型输出。
5. 在 `tests/test_multiagent_and_review.py` 增加 mock 模式下 RAG fallback 和 profile 读取测试。

验收：

- mock daily pipeline 通过。
- 开启 RAG 默认输入后，agent output schema 不变。
- 关闭 RAG 后，旧链路行为不变。
- 对同一日期重复运行时，agent reuse metadata 可正确识别 RAG manifest 是否变化。

回退策略：

- 每个 agent profile 可独立关闭。
- `fallback_to_legacy=true` 时 legacy evidence 自动补位。
- 若 RAG 召回 token 超预算，优先降级新闻/情绪/低 tier 证据，保留结构化事实和决策证据。

### Phase 7：最终建议、复盘、长期记忆接入

目标：让后续重要 LLM 调用也共享 RAG evidence pack，减少 prompt 手工拼接和历史证据遗漏。

修改文件：

```text
scripts/generate_llm_advice.py
scripts/run_long_memory_analysis.py
scripts/review_advice.py
scripts/run_replay_experiment.py
tests/test_rag_decision_memory_review.py
```

工作步骤：

1. `generate_llm_advice.py`：
   - 使用 decision profile 检索当日 committee、validated candidate、约束、组合状态。
   - RAG 只提供证据，不允许绕过 `committee_decision_bundle`。
   - 输出中记录 `rag_trace_id`。
2. `run_long_memory_analysis.py`：
   - 使用 memory profile 检索已有同域同实体 memory。
   - 写入新 memory 前检查 duplicate、contradiction、superseded。
   - 对 permanent/strategic/candidate 的生命周期给出依据。
3. `review_advice.py`：
   - 使用 review profile。
   - 允许 archived/rejected，但必须标 `negative_example`。
   - review 输出不能把 rejected 规则当当前规则。
4. `run_replay_experiment.py`：
   - 使用 backtest profile。
   - 强制 `available_from <= replay_date`。
   - 每次 replay 写 no-future audit。

验收：

- 长期记忆分析不会重复生成同一条已 permanent 的规则。
- review 能引用历史反例，但不会污染当前建议。
- replay 对历史日期不召回未来记忆和未来持仓。
- decision profile 缺少 committee bundle 时明确 missing，而不是用新闻生成新建议。

回退策略：

- 记忆写入保持人工审批链路。
- 复盘 profile 和当前建议 profile 物理隔离配置。
- replay 默认 strict no-future，违规直接 fail。

### Phase 8：Execution Profile 与隐私隔离

目标：支持“真实交易为什么和系统建议不同”“当前真实持仓为何不同”等问题，同时防止执行数据污染投研模型。

修改文件：

```text
scripts/rag_sources.py
scripts/execution_sync.py
scripts/long_memory_store.py
app/web_api.py
frontend/src/app/pages/ExecutionPage.tsx
tests/test_rag_execution_boundary.py
```

工作步骤：

1. 新增 `execution_documents()`，默认不启用。
2. execution doc 必填：

```json
{
  "domain": "execution",
  "learning_scope": "execution_only",
  "visibility": "execution_only",
  "source_kind": "execution_sync"
}
```

3. 只索引摘要，不 embedding 完整截图 OCR、账户截图、流水明细。
4. Copilot planner 只有在 intent 为 `execution_explain`、`position_reconcile`、`pending_confirmation` 时打开 `include_execution=true`。
5. `long_memory_store.build_execution_memory()` 继续只产出 execution memory，不进入 `build_fund_memory()`。

验收：

- 问真实持仓/待确认交易时能召回 execution。
- 问基金是否值得买、系统建议胜率、市场规律时不能召回 actual trades。
- execution trace 中所有 hit 都有 `learning_scope=execution_only`。

回退策略：

- `rag.sources.execution_sync=false` 为默认。
- 用户可在设置页显式开启 execution RAG。
- 出现隐私或误召回风险时，删除 `db/rag` execution docs 不影响原始 execution_sync 数据。

### Phase 9：管理界面、可观测性与维护

目标：让 RAG 不是黑盒，能看索引状态、source 健康、trace 和失败原因。

新增或修改：

```text
app/web_api.py
app/web_api_services.py
frontend/src/app/pages/SystemPage.tsx
frontend/src/app/pages/ResearchPage.tsx
scripts/rag_maintenance.py
tests/test_web_api_rag_admin.py
```

接口：

```text
GET  /api/rag/status
POST /api/rag/search
POST /api/rag/reindex
GET  /api/rag/trace?id=...
POST /api/rag/eval
```

状态页展示：

- RAG enabled / shadow / fallback 状态。
- 最近 ingest 时间。
- documents/chunks 数量。
- 各 source doc count。
- embedding pending/error count。
- 最近 10 次 trace。
- no-future/fund-match eval 是否通过。

维护任务：

- `rag_maintenance.py --vacuum`
- `rag_maintenance.py --rebuild --domain long_memory`
- `rag_maintenance.py --purge-domain execution`
- `rag_maintenance.py --check-integrity`

验收：

- 用户能从系统页看到 RAG 是否真的启用。
- 出错时能看到哪个 source、哪个文件、哪个 trace 失败。
- 重新索引不会删除原始业务数据。

回退策略：

- reindex 先写临时 manifest，完成后再切换 active manifest。
- 支持按 source/domain 单独 purge。

## 16. 测试与评估

### 16.1 必测用例

1. 当前问答：
   - 问当前组合仓位。
   - 问今天某基金建议原因。
   - 问数据是否过期。
   - 问“这个回答用了哪些证据”。

2. 历史问答：
   - 选 2026-05-08，不能召回 2026-05-18 生成的记忆。
   - 选 2026-05-18，不能召回 2026-05-20 的持仓快照。
   - 历史日期不能召回之后生成的 review result。

3. 基金错配：
   - 问 `011840`，不能用 `022365` 当主证据。
   - 可引用组合级约束，但要说明是组合级。
   - 主题扩展必须写入 trace，不能静默扩展。

4. 反例召回：
   - 普通问题不出现 rejected memory。
   - “历史上有没有踩坑”允许 rejected/archived，并标反例。
   - rejected memory 不得作为当前建议依据。

5. 执行边界：
   - 问真实交易可以召回 execution。
   - 问系统建议胜率不能用 actual trade 改写结论。
   - execution doc 不进入 fund/market profile。

6. 数据陈旧：
   - stale estimated_nav 命中时答案必须标注陈旧。
   - 如果用户问“最新”，stale hit 只能作为背景，不能作为主结论。

7. Agent shadow：
   - RAG shadow 开启不改变 validated advice。
   - 每个 agent 都能写 trace。
   - legacy/RAG diff 有 fund-match、source coverage、token budget。

8. 增量索引：
   - unchanged chunk 不重复 embedding。
   - 删除或修改 source 后 manifest 能反映变化。
   - reindex 中断不会破坏 active index。

### 16.2 指标

核心质量指标：

- Top-k 基金匹配率。
- 无未来数据违规数。
- 引用证据覆盖率。
- 缺证据识别准确率。
- execution 误召回次数。
- archived/rejected 非预期召回次数。

工程指标：

- Copilot 首答延迟。
- query embedding 耗时。
- ingest 总耗时。
- embedding 缓存命中率。
- 每日分析 token 预算变化。
- fallback 使用率。
- trace 写入成功率。

建议阈值：

| 指标 | Phase 4 阈值 | Phase 6 阈值 |
|---|---:|---:|
| no-future 违规 | 0 | 0 |
| 明确 fund_code 主证据错配 | 0 | 0 |
| Copilot P95 首答延迟 | < 12s | < 8s |
| embedding 缓存命中率 | > 60% | > 85% |
| Agent token 增量 | 仅 shadow | < 15% |
| RAG fallback 率 | 可高 | < 10% |

### 16.3 自动化测试命令

第一批测试：

```powershell
python -m unittest discover -s tests -p test_rag_config.py
python -m unittest discover -s tests -p test_rag_index_store.py
python -m unittest discover -s tests -p test_rag_sources.py
python -m unittest discover -s tests -p test_rag_retriever_filters.py
```

Copilot 接入后：

```powershell
python -m unittest discover -s tests -p test_web_api_rag_copilot.py
cd frontend
npm run build
```

Daily shadow 后：

```powershell
python -m unittest discover -s tests -p test_pipeline_logic.py
python -m unittest discover -s tests -p test_multiagent_and_review.py
python scripts\run_daily_pipeline.py --date 2026-05-20 --mode intraday --demo --llm-mock --resume-existing
python scripts\rag_eval.py --date 2026-05-20 --compare-legacy
```

Execution profile 后：

```powershell
python -m unittest discover -s tests -p test_rag_execution_boundary.py
python -m unittest discover -s tests -p test_execution_sync.py
```

### 16.4 人工验收问题集

建议维护：

```text
tests/fixtures/rag_questions/copilot_current.json
tests/fixtures/rag_questions/copilot_historical.json
tests/fixtures/rag_questions/agent_profiles.json
tests/fixtures/rag_questions/execution_boundary.json
```

每条问题包含：

- question
- selected_date
- fund_code
- expected_intent
- must_include_source_kinds
- must_exclude_domains
- must_not_use_future_after
- expected_missing_data

## 17. 代码演进风险与修复策略

### 17.1 向量相似但事实错误

风险：

- 主题相似新闻命中错误基金。
- LLM 从文本摘要中推断数值事实。
- 低质量新闻压过结构化事实。

应对：

- hard filter 先于 vector search。
- 数值事实只走 `payload_json` 和结构化 adapter。
- source tier rerank 明确让 `structured_current/decision_trace` 高于新闻。
- answer prompt 要求引用证据编号，不允许无引用结论。

修复策略：

- 出现错配时，先检查 `fund_codes/entity_id/mapping_mode`，再调 rerank 权重。
- 对主题新闻增加 `mapping_mode=theme_match` 惩罚，不作为明确基金问题主证据。

### 17.2 日期穿越

风险：

- 未来生成的 long memory 描述过去事件，被历史回测误用。
- 新闻抓取只看 lookback 下界，未来发布时间混入。
- 文件 mtime 和业务日期不一致。

应对：

- 每条 doc 强制 `available_from`。
- historical/backtest profile 只看 `available_from <= query_date end_of_day`。
- 新闻 adapter 额外验证 `published_at <= query_date end_of_day`。
- trace 记录被过滤的未来候选样本。

修复策略：

- 一旦 eval 发现 future violation，RAG strict 模式直接 fail。
- 对缺失 timestamp 的历史 artifact 标 `available_from_inferred=true` 并降低置信。

### 17.3 记忆复活与记忆冲突

风险：

- archived/rejected 被普通问答召回。
- superseded 记忆与 current 记忆同时出现。
- 新 long memory 重复生成已有规则。

应对：

- `visibility=review_only` 默认排除。
- `superseded_by` 默认排除。
- memory profile 检索同域同实体已有记忆，写入前做 duplicate/contradiction check。

修复策略：

- 新增 `rag_memory_audit.py --entity-key ...` 查看同实体记忆生命周期。
- 发现冲突时不自动删除，写 candidate 并要求人工审批。

### 17.4 execution 数据污染

风险：

- actual trade 被用于判断系统建议是否正确。
- 支付宝截图/OCR 内容被普通 RAG 召回。
- 真实持仓隐私被 embedding 到外部 API。

应对：

- execution source 默认关闭。
- execution doc `learning_scope=execution_only`。
- execution profile 与 fund/market/decision profile 分离。
- 不 embedding 完整截图和账户流水，只 embedding 脱敏摘要或只走本地 FTS。

修复策略：

- 支持 `rag_maintenance.py --purge-domain execution`。
- eval 加 `must_exclude_domains=["execution"]` 问题集。

### 17.5 API embedding 成本与供应商兼容

风险：

- 当前 Responses 代理不支持 embeddings endpoint。
- 大量历史 artifact 首次重建成本高。
- embedding 失败导致 pipeline 卡死。

应对：

- embedding provider 可独立配置。
- checksum + cache。
- 分批 ingest，默认 daily incremental。
- embedding 失败只标 chunk pending/error，不阻断旧链路。

修复策略：

- `rag_embedding_client.py --probe` 检测 endpoint。
- `rag_ingest.py --limit N` 分批补索引。
- `rag.enabled=false` 一键关闭。

### 17.6 延迟和 token 膨胀

风险：

- Copilot 每问都检索太多证据。
- Agent profile 注入 RAG 后 prompt 变大。
- evidence pack 包含重复新闻。

应对：

- query embedding 缓存。
- evidence pack token budget。
- 新闻按 canonical URL/content hash 去重。
- 低 tier source 先摘要再入 pack。

修复策略：

- trace 记录每类 source token 占比。
- 超预算时按 source tier 降级，而不是截断结构化事实。

### 17.7 旧链路稳定性

风险：

- RAG 替换太早导致 daily advice 变化不可解释。
- agent reuse metadata 没包含 RAG manifest，复用旧输出。
- RAG reindex 中断导致索引半成品被使用。

应对：

- Phase 5 先 shadow，不注入 prompt。
- `workflow_meta` 记录 RAG manifest sha。
- reindex 使用临时 manifest，完成后原子切换 active。
- `evidence_index.py` 长期保留 fallback。

修复策略：

- 出现建议异常时，关闭 agent profile RAG，仅保留 Copilot RAG。
- 对比 `rag_eval` 与 legacy evidence 后再调权重。

### 17.8 编码、Windows 路径与本地文件问题

风险：

- 中文路径和 PowerShell 输出编码造成 mojibake。
- Windows 文件锁导致 sqlite 写入失败。
- 大 JSON artifact 读取慢。

应对：

- 所有新脚本显式 `encoding="utf-8"`。
- SQLite 写入设置合理 timeout，避免长事务。
- 大文件 adapter 流式/分段处理，不把无关 raw log 全读入。

修复策略：

- 测试中增加中文标题、中文路径、Windows 风格路径样例。
- trace 中记录 source_path，便于定位坏文件。

## 18. 推荐的第一批开发任务拆解

第一批建议以 10 个小 PR 或小任务落地，每个任务都可单独测试和回退。

### Task 1：RAG 配置和 SQLite store

改动：

- 新建 `config/rag.toml`。
- 新建 `scripts/rag_config.py`、`scripts/rag_models.py`、`scripts/rag_index_store.py`。
- 新建 `tests/test_rag_config.py`、`tests/test_rag_index_store.py`。

完成标准：

- 能初始化 `db/rag/rag.sqlite`。
- 默认不开启 RAG。
- dry-run 不需要 API key。

### Task 2：long_memory adapter

改动：

- `scripts/rag_sources.py` 实现 `iter_long_memory_documents()`。
- 从 `db/long_memory/memory.sqlite` 读取，不以 `exports/all_memory.json` 为主源。
- archived/rejected 标 `review_only`。

完成标准：

- permanent/strategic/candidate 默认可见。
- archived/rejected 普通 profile 不可见。
- valid_from/valid_until 生效。

### Task 3：portfolio 和 llm_context adapter

改动：

- 实现 `iter_portfolio_documents()`。
- 实现 `iter_llm_context_documents()` 和 `iter_evidence_item_documents()`。
- 保留 numeric payload。

完成标准：

- `db/portfolio_state/current.json` 生成组合和基金 docs。
- `db/llm_context/2026-05-20.json` 生成 evidence docs。
- 明确基金代码的 evidence docs 带 `fund_codes`。

### Task 4：validated/committee adapter

改动：

- 实现 `iter_validated_advice_documents()`。
- 实现 `iter_committee_bundle_documents()`。

完成标准：

- 每条 action 可引用。
- market view 和 cross fund observations 可引用。
- 缺文件时返回 missing，不抛出阻断错误。

### Task 5：rag_ingest CLI

改动：

- 新建 `scripts/rag_ingest.py`。
- 支持 `--dry-run`、`--write`、`--date`、`--domain`、`--all`。
- 写 `source_manifest`。

完成标准：

- 重复 ingest 幂等。
- 输出 doc/chunk/count/error summary。
- 不影响现有 pipeline。

### Task 6：hard filter retriever

改动：

- 新建 `scripts/rag_retriever.py`、`scripts/rag_rerank.py`、`scripts/rag_trace.py`。
- 先实现 SQLite/FTS/mock 检索，不强依赖真实向量。

完成标准：

- no-future、fund-match、memory-status 测试通过。
- trace 写入成功。
- 无命中时返回 missingData。

### Task 7：embedding client 和 cache

改动：

- 新建 `scripts/rag_embedding_client.py`。
- 接入 embeddings endpoint probe。
- cache by model + text hash。

完成标准：

- 无 API key 时 dry-run 通过。
- API 不支持时降级 mock。
- unchanged chunk 不重复请求。

### Task 8：Copilot RAG

改动：

- 新建 `app/rag_service.py`、`app/rag_answering.py`。
- 修改 `app/web_api.py`、`app/copilot_service.py`。
- 修改前端 types/api/panel。

完成标准：

- 返回 citations/traceId。
- RAG 失败可 fallback。
- 前端 build 通过。

### Task 9：daily shadow

改动：

- 修改 `scripts/run_daily_pipeline.py` 加可选 RAG ingest/eval。
- 修改 `scripts/agent_inputs.py` 写 shadow 字段。
- 新建 `scripts/rag_eval.py`。

完成标准：

- shadow 不改变最终建议。
- 每个 agent 有 trace。
- eval 输出 legacy/RAG 对比。

### Task 10：agent 默认接入和长期维护

改动：

- 将 agent profiles 写入 `config/rag.toml`。
- 修改 `agent_inputs.py` 默认使用 RAG，legacy fallback。
- 新建 `scripts/rag_maintenance.py`。

完成标准：

- mock daily pipeline 通过。
- 关闭 RAG 后旧链路正常。
- 系统页能查看 RAG 状态。

## 19. 产品结论

OKRA 的 RAG 不应被设计成“把所有文件向量化后让模型自由搜”。正确形态是：

```text
结构化事实源 + 长期记忆生命周期 + 日期/基金硬约束 + 向量召回 + 来源优先级 rerank + 可审计引用
```

右侧智能助手是第一个消费方，它负责把复杂证据链解释给用户。每日分析是第二个消费方，它负责把同一套证据检索能力嵌入多 Agent 决策流程。两者共享底层索引，但检索 profile 和回答/分析目标不同。

第一版应该直接按“统一底座”开发，而不是只在 Copilot 上做轻量补丁；但落地顺序要保持稳健：先索引和调试，再接 Copilot，最后 shadow 每日分析，避免一次性重写现有稳定链路。
