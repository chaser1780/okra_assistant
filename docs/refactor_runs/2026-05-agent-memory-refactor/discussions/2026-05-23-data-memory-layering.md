# 2026-05-23 Data And Memory Layering

## Topic

Discuss the next stage after debate-to-action: financial data layering and
layered long-memory design.

## User Direction

- Continue step by step instead of jumping to the full architecture.
- Use FinRobot, FinGPT, FinMem, and other strong external data/memory designs as
  references.
- Do not treat memory as simple RAG.
- Different data types should have different lifecycle, storage, retrieval, and
  learning behavior.
- The design should support autonomous strategy growth.

## Discussion Status

- Accepted in full.
- Formal plan written to `02_data_memory_layering_plan.md`.

## Accepted Summary

- OKRA's memory should be a layered financial memory system, not a simple RAG
  library.
- Adopt the layers: raw observations, canonical facts, derived signals,
  decision events, outcome events, strategy memory, and strategy skills.
- Action tickets should consume layered retrieval packs.
- Soft constraints become adaptive policies connected to long memory.
- Hard constraints remain preserved for now and will be discussed separately.
