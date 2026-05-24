# 2026-05-23 LangGraph Shadow Orchestration

## Topic

Discuss whether and how OKRA should introduce LangGraph as the orchestration
layer for the new agent architecture.

## Starting Direction

- User agreed to discuss LangGraph as the next technical-stack topic.
- Do not migrate the whole OKRA pipeline at once.
- Use LangGraph where it improves stateful orchestration, checkpointing,
  human-in-the-loop, and traceability.

## Initial Proposal

- Keep current deterministic data pipeline in Python scripts.
- Add LangGraph in shadow mode for:
  - debate-to-action graph
  - skill-curator graph
  - outcome-evaluation graph
- Keep canonical facts, execution data, and durable artifacts outside LangGraph
  state.
- Treat LangGraph checkpoint state as orchestration state, not as the source of
  truth for financial data.

## Accepted Summary

- LangGraph is accepted as the shadow orchestration layer for new agent decision
  loops.
- It should be used for debate-to-action, Skill Curator, and outcome evaluation
  graphs.
- It should not replace deterministic data fetching, canonical facts, official
  NAV/PnL, portfolio reconciliation, or execution sync.
- LangGraph state should hold orchestration state and refs only.

## Still Open

- Exact dependency and backend choice.
- Exact graph node schemas.
- Checkpoint backend.
- Which graph runs first in implementation.
