# 2026-05-23 External Reference Discussion Start

## User Direction

- Start from external references instead of jumping directly to a full OKRA
  redesign.
- Discuss step by step; avoid a broad, incomplete architecture proposal.
- Be aggressive and effective. Do not let the old architecture constrain the
  new architecture.
- TradingAgents is useful mainly if OKRA changes from layered action withdrawal
  to debate that produces action.
- FinRobot, FinGPT, FinMem, and other data/memory systems should inform a
  better financial data and layered memory design, not a simple RAG layer.
- Hermes Agent and OpenClaw are useful for closed-loop growth and reusable
  strategy skills.
- LangGraph, CrewAI, Mem0, Letta, and Zep are candidates for stable, modern
  technical choices.
- Other modules such as crawling, real-time PnL, and Copilot are not the main
  refactor target, but their connections should be considered.

## Current Discussion Scope

- First discussion topic: external reference patterns and what OKRA should
  borrow from them.
- Do not write the final system blueprint yet.

## Open Threads

- How to turn debate into action without unsafe execution.
- How to layer financial data and memory beyond simple RAG.
- Which technical memory/orchestration stack should become the implementation
  base.

## External References Checked

- TradingAgents: specialized analyst, researcher, trader, risk, and portfolio
  manager roles; recent release notes mention structured-output decision agents,
  LangGraph checkpoint resume, and persistent decision log.
- FinRobot: financial AI agent platform with Perception, Brain, and Action
  workflow; ecosystem separates financial agents, financial LLM algorithms,
  LLMOps/DataOps, and foundation model layers.
- FinGPT: finance is highly dynamic, so lightweight adaptation and data
  updating are emphasized over repeatedly retraining a monolithic model.
- FinMem: profiling, layered memory, and decision-making modules; memory should
  transform hierarchical financial data into decisions, not just retrieve text.
- Zep/Graphiti: temporal graph memory tracks when facts were true and combines
  semantic search, keyword matching, and graph traversal.
- CrewAI memory: composite scoring combines semantic similarity, recency, and
  importance; automatic fact extraction after tasks is relevant to OKRA's
  nightly learning loop.
- LangGraph memory: long-term memories are JSON documents organized by
  namespace/key; semantic, episodic, and procedural memory categories are a good
  low-level schema reference.
- Letta/MemGPT: core memory plus archival memory and self-editing memory tools
  are relevant to a strategy brain that can revise its own durable context.
- Mem0: useful reference for managed/vector/graph/reranked memory, but should be
  treated as an implementation option rather than the domain schema itself.
- Hermes Agent/OpenClaw: closed-loop growth and reusable skills are the main
  lessons; OKRA should distinguish memory of facts from reusable strategy
  procedures.

## First Discussion Bias

- Do not preserve the old fixed committee/validator shape by default.
- Preserve safety as hard guardrails, but move strategy authority toward the
  debate/action layer.
- Treat RAG as one retrieval mechanism inside a richer financial memory system,
  not as the memory system itself.
