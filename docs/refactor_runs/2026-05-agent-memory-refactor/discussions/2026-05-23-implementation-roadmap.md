# 2026-05-23 Implementation Roadmap

## Topic

Discuss how to implement the accepted architecture in stages without breaking
the current OKRA workbench.

## Current Accepted Stages

- Stage 1: Debate to action.
- Stage 2: Data and memory layering.
- Stage 3: Closed-loop strategy skills.
- Stage 4: LangGraph shadow orchestration.

## Discussion Status

- Accepted as staged implementation principle.
- Formal plan written to `05_implementation_roadmap_plan.md`.

## Accepted Summary

- Use new chain first, old chain preserved, shadow comparison, gradual takeover,
  then legacy reduction.
- Branch work by phase and artifact family.
- Write technical details and ambiguity handling before implementation.
- Superseding review refinement on 2026-05-24: start implementation from Phase
  0.5 Golden Vertical Slice after the planning checkpoint is safe.
- Broad Phase 1 Action Ticket Shadow Foundation starts only after the fixed
  vertical slice has golden output, replay, diff report, and boundary checks.
