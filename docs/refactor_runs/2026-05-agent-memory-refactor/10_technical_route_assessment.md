# 10 Technical Route Assessment

Status: reviewed against current OKRA context and external reference projects.

This document evaluates whether the current OKRA agent/memory refactor plan is
reasonable, sufficiently advanced, and technically aligned with strong external
patterns.

## Executive Judgment

The current plan is reasonable and advanced for OKRA's product shape.

It is stronger than a simple multi-agent rewrite because it combines:

- action-ticket-centered decision artifacts
- debate before action formation
- layered data and memory
- deterministic official facts
- outcome-backed learning
- adaptive soft policies
- reusable strategy skills
- shadow orchestration before promotion
- read-only human review before legacy reduction

The most important design quality is that the plan does not treat LLM autonomy
as permission to mutate financial truth. LLM agents can reason, debate, propose,
reprice, and learn. Deterministic code still owns NAV, PnL, portfolio state,
execution sync, hard constraints, source visibility, and compatibility outputs.

## External Reference Check

The assessment below uses current public documentation and project pages checked
on 2026-05-24.

Refresh on 2026-05-24:

- LangGraph official docs still emphasize durable execution, persistence,
  checkpoints, thread ids, human-in-the-loop interruption, and deterministic
  replay around side effects.
- CrewAI official docs still distinguish high-level Crews and structured Flows;
  they remain useful as a role/workflow reference but not the selected low-level
  runtime.
- Mem0 public docs position memory as managed infrastructure with filtering,
  retrieval, graph features, and governance concepts.
- Zep/Graphiti public docs emphasize temporal knowledge graphs, episodes,
  hybrid search, provenance, custom entities, and point-in-time memory.
- TradingAgents current public project materials continue to show a financial
  multi-agent workflow with analyst, research/debate, trader, risk, and
  portfolio-manager style roles.
- FinRobot and FinGPT public project materials continue to support the data
  layer conclusion: financial agents need structured data, analytics, retrieval,
  and domain-specific financial workflows, not only generic prompts.
- FinMem remains the main layered-memory research reference for profiling,
  hierarchical memory processing, and decision-making in financial trading
  agents.

Reference URLs:

- `https://docs.langchain.com/oss/python/langgraph`
- `https://docs.langchain.com/oss/python/langgraph/durable-execution`
- `https://docs.langchain.com/oss/python/langgraph/persistence`
- `https://docs.crewai.com/en/introduction`
- `https://www.crewai.com/crewai-flows`
- `https://docs.crewai.com/en/concepts/flows`
- `https://docs.crewai.com/en/concepts/crews`
- `https://docs.mem0.ai/platform/features/platform-overview`
- `https://docs.mem0.ai/overview`
- `https://help.getzep.com/graph-overview`
- `https://help.getzep.com/graphiti/getting-started/welcome`
- `https://docs.letta.com/`
- `https://docs.letta.com/guides/core-concepts/stateful-agents/`
- `https://github.com/TauricResearch/TradingAgents`
- `https://tradingagents.co/`
- `https://github.com/AI4Finance-Foundation/FinRobot`
- `https://github.com/AI4Finance-Foundation/FinGPT`
- `https://fingpt.io/`
- `https://arxiv.org/abs/2311.13743`

### LangGraph

Reference:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

Relevant external pattern:

- LangGraph is positioned as a low-level orchestration runtime for long-running,
  stateful agents.
- Its core strengths include durable execution, persistence,
  human-in-the-loop, memory, streaming, and fault tolerance.
- Durable execution saves workflow progress and supports resume after
  interruption; the docs also emphasize deterministic/idempotent workflow design
  around side effects.

Fit for OKRA:

- Strong fit for Phase 3 debate-to-action shadow graph.
- Strong fit for Skill Curator and outcome-evaluation graphs.
- Especially appropriate because OKRA needs resumable, auditable workflows, not
  a single chat call.

Recommended OKRA use:

- Use LangGraph for orchestration state, node status, retry/resume, and
  human-review interruption points.
- Do not use LangGraph as the database for financial facts.
- Keep large facts and source-of-truth data outside graph state; store refs.
- Wrap external side effects and file writes carefully to preserve replay
  safety.

Assessment:

- Current OKRA plan matches the strong parts of LangGraph and avoids the main
  misuse risk.
- The plan should keep LangGraph adoption delayed until Phase 3 because Phase 1
  and Phase 2 artifact contracts should be stable first.

### CrewAI

Reference:

- [CrewAI Flows](https://docs.crewai.com/en/concepts/flows)
- [CrewAI Crews](https://docs.crewai.com/en/concepts/crews)

Relevant external pattern:

- CrewAI provides high-level agent/crew abstractions and Flows for structured,
  event-driven workflows with state, branching, and task coordination.

Fit for OKRA:

- Useful as a conceptual reference for teams, task coordination, and workflow
  ergonomics.
- Less ideal than LangGraph as the primary OKRA implementation layer because
  OKRA needs a low-level, local, artifact-first orchestration boundary with
  strict source-of-truth separation.

Recommended OKRA use:

- Borrow role clarity and workflow patterns.
- Do not replace the accepted LangGraph shadow orchestration plan with CrewAI
  unless implementation friction forces a later reassessment.

Assessment:

- Not the first-choice core runtime for this refactor.
- Good reference, not core dependency.

### TradingAgents

Reference:

- [TradingAgents project page](https://tradingagents.co/)
- [TradingAgents paper page](https://tradingagents-ai.github.io/)
- [TauricResearch/TradingAgents GitHub](https://github.com/TauricResearch/TradingAgents)

Relevant external pattern:

- Specialized financial roles: analysts, bull researcher, bear researcher,
  trader, risk manager, portfolio manager.
- Debate layer before final decision.
- Trader decides entry/exit, timing, and position sizing after synthesized
  research.
- Risk and portfolio layers evaluate exposure and final allocation.

Fit for OKRA:

- Very strong conceptual fit for the daily research/debate structure.
- OKRA's current plan improves the fit by focusing on action tickets rather
  than just a report or single buy/hold/sell output.

Recommended OKRA use:

- Borrow the role model:
  - analysts collect evidence
  - bull/bear debate challenges action candidates
  - strategy/trader forms action tickets
  - risk enforces hard guardrails and soft repricing
  - portfolio selector chooses a coherent set of tickets
- Avoid copying a hard risk-veto culture that silently collapses everything to
  hold.

Assessment:

- The current OKRA plan correctly adopts the best part of TradingAgents: debate
  and role separation.
- It also corrects a likely weakness for OKRA: decisions must be traceable,
  evaluable action tickets, not just committee prose.

### FinRobot / FinGPT

References:

- [FinRobot GitHub](https://github.com/AI4Finance-Foundation/FinRobot)
- [FinGPT GitHub](https://github.com/AI4Finance-Foundation/FinGPT)

Relevant external pattern:

- FinRobot frames financial agents as full-stack systems combining LLMs,
  quantitative analytics, and task automation.
- FinGPT emphasizes financial data sources, data engineering, temporal
  sensitivity, low signal-to-noise data, and domain-specific financial tasks.

Fit for OKRA:

- Strong fit for data-layer thinking.
- OKRA needs data engineering and source governance more than another generic
  prompt layer.

Recommended OKRA use:

- Borrow the data-source/data-engineering bias.
- Keep official NAV, position, cash, benchmark, execution, and source-health
  fields as structured facts.
- Use LLMs for interpretation and synthesis, not as the owner of current
  financial facts.

Assessment:

- The current layered-data plan aligns well with this family of financial AI
  systems.
- It is correct that OKRA should not turn everything into flat RAG text.

### Mem0

Reference:

- [Mem0 overview](https://docs.mem0.ai/platform/overview)

Relevant external pattern:

- Mem0 positions itself as a managed memory layer for AI agents.
- Its documented capabilities include persistent memories, vector store, graph
  services, rerankers, audit logs, and workspace governance.

Fit for OKRA:

- Useful reference for long-memory operations and governance.
- Direct managed-service adoption is not the first choice because OKRA is a
  local financial assistant with private portfolio/execution data.

Recommended OKRA use:

- Borrow the memory-as-infrastructure idea.
- Keep local storage and explicit lifecycle states.
- Add auditability, metadata filters, and memory evaluation concepts to local
  policy/skill stores.

Assessment:

- The current plan is compatible with Mem0-style memory concepts but chooses the
  safer local route for OKRA.

### Zep / Graphiti

References:

- [Graphiti overview](https://help.getzep.com/graphiti/getting-started/overview)
- [Zep graph overview](https://help.getzep.com/graph-overview)

Relevant external pattern:

- Zep/Graphiti emphasize temporal knowledge graphs that handle changing
  relationships and historical context.
- Graphiti uses episodic ingestion, provenance, temporal metadata, hybrid search,
  custom entity types, and point-in-time querying.

Fit for OKRA:

- Very strong conceptual fit for future strategy memory and fact lifecycles.
- Particularly relevant to:
  - as-of dates
  - valid-from/valid-until
  - contradicted facts
  - strategy lifecycle
  - historical outcome review

Recommended OKRA use:

- Borrow temporal modeling ideas.
- Do not add a graph database prematurely.
- First implement append-only events, stable ids, and explicit validity windows
  in local JSON/SQLite artifacts.
- Consider a graph layer later only if policy/skill/fact relationships become
  hard to query with local structured stores.

Assessment:

- The current plan is advanced because it already includes temporal and
  provenance fields such as `as_of_date`, `available_from`, `valid_from`, and
  event logs.
- The plan is appropriately conservative by not introducing graph storage before
  simpler local artifacts prove insufficient.

### Letta

Reference:

- [Letta Code overview](https://docs.letta.com/letta-code)

Relevant external pattern:

- Letta emphasizes stateful agents that remember, learn from experience, and
  improve with use.
- The feature set includes memory, skills, subagents, permissions, hooks, and
  schedules.

Fit for OKRA:

- Strong conceptual fit for the long-term strategy-skill direction.
- The Skill Curator idea aligns with learned skills and continual improvement.

Recommended OKRA use:

- Borrow the principle that memory and skills should become first-class agent
  infrastructure.
- Keep skills domain-specific, versioned, auditable, and outcome-backed.
- Avoid letting learned skills bypass hard constraints.

Assessment:

- The current Strategy Skill Curator plan is aligned with modern stateful-agent
  thinking.
- The main missing implementation anchor is a concrete strategy skill template
  and registry schema.

## Reasonableness Assessment

### Why Action Tickets Are Reasonable

Action tickets solve the current architecture problem:

```text
analysis prose -> committee summary -> validator shrinkage -> unclear action
```

They create a durable decision object with:

- target fund
- action verb
- timing
- amount
- confidence
- evidence
- risks
- hard guardrails
- soft policy adjustments
- invalidation conditions
- opportunity cost
- outcome links
- skill usage

This is the right center of gravity because future learning needs something
stable to evaluate.

Verdict:

- Strongly reasonable.
- Should be Phase 1's main artifact.

### Why Layered Data Is Reasonable

Financial systems fail when current facts, retrieved text, user screenshots,
opinions, historical cases, and memories are all treated as the same kind of
context.

The plan's separation into facts, signals, decisions, outcomes, policies, and
skills is correct because each layer has different:

- source of truth
- freshness rules
- visibility rules
- mutability
- retrieval method
- validation needs

Verdict:

- Strongly reasonable.
- Essential for preventing RAG hallucination from becoming state corruption.

### Why Shadow Mode Is Reasonable

OKRA already has useful daily analysis, execution sync, valuation, and workbench
flows. Replacing them in one pass would be high risk.

Shadow mode enables:

- old/new comparison
- artifact validation
- user review
- outcome evaluation
- rollback
- gradual takeover

Verdict:

- Necessary.
- The plan should not weaken this boundary.

### Why LangGraph Is Reasonable

The accepted graph is a long-running reasoning workflow with multiple agents,
failure states, and future human review. That is exactly where LangGraph fits.

However, LangGraph should not be introduced before:

- action-ticket schema is locked
- retrieval-pack schema is locked
- file artifact paths are stable

Verdict:

- Reasonable and modern.
- Correctly delayed to Phase 3.

### Why Strategy Skills Are Reasonable

Long-term growth should not be a bag of memories. A mature system should learn
reusable procedures:

- when a pattern applies
- what inputs are required
- what steps to run
- how to size
- what invalidates the thesis
- what failure modes are known

This is more useful than retrieving old text snippets.

Verdict:

- Advanced and directionally correct.
- Needs strict lifecycle and outcome-backed promotion.

## Advancedness Assessment

The plan is advanced because it combines several mature patterns instead of
choosing only one:

| Pattern | External reference | OKRA adaptation |
|---|---|---|
| Debate before action | TradingAgents | Bull/bear debate must produce action tickets, not just opinions |
| Stateful orchestration | LangGraph | Shadow graphs with refs, not financial fact storage |
| Financial data engineering | FinGPT/FinRobot | Structured facts first, RAG second |
| Temporal memory | Zep/Graphiti | dates, validity, event logs, outcome linkage |
| Agent memory and skills | Mem0/Letta | local adaptive policies and strategy skills |
| Human review before promotion | LangGraph/CrewAI patterns | read-only Workbench comparison before official takeover |

The plan is more advanced than:

- a prompt-only multi-agent committee
- flat vector RAG over all documents
- direct LLM trade execution
- unversioned long-memory notes
- hard-coded validator-only strategy

It is still intentionally conservative where it should be:

- local-first storage
- deterministic accounting
- official NAV/PnL boundary
- execution memory separation
- shadow-first rollout
- compatibility output retention

## Main Technical Risks

### Risk 1: Over-Documentation Without Schema Examples

The broad plan is strong, but implementation can drift without examples.

Required mitigation:

- create schema examples before coding Phase 1

### Risk 2: RAG Reappears As The Main Context Layer

The RAG document is extensive, so future work may overuse it.

Required mitigation:

- make the layered retrieval pack the only input contract for the action-debate
  graph
- put RAG hits inside the pack as evidence/case sections only

### Risk 3: Soft Policies Become Hidden Hard Rules

Adaptive policies can accidentally become another validator.

Required mitigation:

- enforce allowed soft effects:
  - confidence delta
  - size multiplier
  - wait trigger
  - warning note
- forbid soft-policy `block`

### Risk 4: Skill Curator Over-Learns From Too Few Outcomes

Autonomous growth can overfit if it promotes skills too quickly.

Required mitigation:

- default Skill Curator output to draft/candidate
- require multiple outcome supports or user approval for active
- track contradiction count and decay

### Risk 5: LangGraph Replay Duplicates Side Effects

Durable execution requires deterministic and idempotent side effects.

Required mitigation:

- keep file writes in explicit writer nodes/tasks
- use stable artifact ids
- verify existing outputs before writing
- avoid external irreversible side effects in graph nodes

### Risk 6: UI Turns Shadow Into Official Advice

Users may misread shadow tickets if UI labels are weak.

Required mitigation:

- first UI version read-only
- explicit `shadow_only`, `non_executable`, `not_official_advice`
- no execution buttons attached to shadow tickets

## Recommendation

Keep the current route.

Do not pivot to a different framework or simpler RAG-only architecture.

The next best work is not another high-level redesign. The next best work is to
make the current plan implementable:

1. add schema examples
2. add hard-constraint inventory
3. add phase checklists
4. update RAG implementation status
5. run Phase 0.5 as a golden vertical slice before broad Phase 1

## Final Assessment

| Dimension | Assessment |
|---|---|
| Product fit | Strong |
| Architecture coherence | Strong |
| Technical modernity | Strong |
| Local safety | Strong |
| Financial fact discipline | Strong |
| Implementation readiness | Medium-high |
| Missing before code | Schema examples, hard-constraint inventory, phase checklist |
| Biggest risk | Skipping Phase 0 details and letting later phases infer schemas |

Conclusion:

The plan is reasonable, advanced, and aligned with strong external agent and
financial-AI patterns. It should proceed, but implementation should start with
Phase 0 hardening and then Phase 0.5 replay evidence rather than jumping
directly into LangGraph, UI changes, or a broad action-ticket rollout.
