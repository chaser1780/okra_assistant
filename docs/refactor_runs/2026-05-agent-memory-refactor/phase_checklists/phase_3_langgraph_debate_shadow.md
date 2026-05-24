# Phase 3 Checklist: LangGraph Debate Shadow

Status: depends on Phase 1 action tickets and Phase 2 retrieval packs.

## Goal

Introduce a new debate-to-action graph in shadow mode. The graph may reason,
debate, and rewrite shadow tickets, but it must not mutate official advice,
portfolio state, execution sync, or long memory.

## Allowed Write Set

- `scripts/action_debate_graph.py`
- `scripts/action_debate_prompts.py`
- `scripts/run_action_debate_shadow.py`
- `tests/test_action_debate_graph.py`
- `db/action_debates/<report_date>.json`
- `db/action_tickets/<report_date>.json` only in the shadow namespace/format
- graph runtime/checkpoint metadata under an explicit shadow path

## Forbidden Write Set

- `db/validated_advice/*`
- `db/portfolio_state/*`
- `db/execution_sync/*`
- `db/long_memory/*`
- adaptive policies
- strategy skills
- direct execution APIs

## Inputs

- Phase 1 action tickets
- Phase 2 retrieval packs
- existing LLM transport helper in `scripts/multiagent_utils.py`
- LangGraph dependency/version decision
- checkpoint backend decision

## Graph Shape

```text
load_retrieval_pack
-> analyst_evidence_view
-> bull_case
-> bear_case
-> debate_referee
-> action_former
-> hard_guardrail_check
-> soft_policy_reprice
-> ticket_writer
```

## State Boundary

Graph state may store:

- ids
- node status
- compact summaries
- artifact refs
- trace ids
- failure metadata

Graph state must not store:

- full portfolio state
- full raw news/log files
- official NAV source of truth
- execution sync source of truth
- raw API secrets

Node design rule:

- Nodes should be thin. A node represents a meaningful reasoning, routing, or
  IO boundary.
- Data transformation that belongs in dataclass builders should not be hidden in
  LangGraph state.

## Implementation Steps

1. Add minimal graph state dataclass or TypedDict.
2. Add node functions with deterministic input/output contracts.
3. Start with local file-backed runtime metadata if checkpoint backend is not
   settled.
4. Keep all file writes in explicit writer node(s).
5. Make reruns idempotent by stable ids and existing-file checks.
6. Mark failed nodes as degraded in shadow artifacts.
7. Do not call official validator as a mutating step; call guardrail mapping as
   read-only explanation.

## Required Tests

- graph can run from a fixture retrieval pack
- bull/bear/referee/action-former outputs are captured
- node failure produces degraded artifact, not official mutation
- rerun is idempotent for same report date and same inputs
- graph state contains refs, not large facts
- graph state serialized size remains within a small configured threshold
- shadow run does not write official artifacts

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\action_debate_graph.py scripts\action_debate_prompts.py scripts\run_action_debate_shadow.py
python -B -X utf8 -m unittest tests.test_action_debate_graph
python -B -X utf8 -m unittest tests.test_multiagent_and_review tests.test_validation_and_trade
```

## Manual Verification

- Review one graph trace and confirm each node has status.
- Confirm failure/retry behavior is visible.
- Confirm shadow tickets are clearly marked non-executable.
- Confirm official daily result is unchanged.

## Rollback Notes

Remove generated graph runtime files and shadow debate/ticket files. Disable or
remove the standalone shadow script. No official chain rollback should be
required.

## Promotion Gate

Phase 7 can expose shadow review only after:

- graph artifacts are stable enough to normalize;
- partial/degraded statuses are explicit;
- non-executable markers are present;
- missing retrieval packs produce a clear not-run/missing state.
