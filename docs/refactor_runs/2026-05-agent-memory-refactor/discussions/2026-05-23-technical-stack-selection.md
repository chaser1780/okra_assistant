# 2026-05-23 Technical Stack Selection

## Topic

Discuss the implementation technology direction for orchestration, memory,
retrieval, and skill infrastructure.

## User Direction

- Prefer advanced but stable technology.
- Do not overfit to the old OKRA architecture.
- Technical choices should support debate-to-action, layered memory, adaptive
  policies, and strategy skills.

## Discussion Status

- Initial technical direction accepted by user.
- Next discussion topic: LangGraph as the new orchestration layer in shadow
  mode.

## Accepted Initial Bias

- Use LangGraph for new orchestration in shadow mode rather than migrating the
  whole OKRA pipeline at once.
- Keep canonical facts local and structured.
- Keep event ledgers append-only and auditable.
- Use current RAG/retrieval stack first for similar memory; evaluate stronger
  vector/graph backends later.
- Treat Zep/Graphiti, Mem0, Letta, and CrewAI mostly as design references or
  optional future backends, not immediate mandatory dependencies.
- Store strategy skills locally as inspectable Markdown plus registry metadata.
