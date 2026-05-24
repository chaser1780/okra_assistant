# Phase 6 Checklist: Strategy Skill Curator

Status: template ready after Phase 0; active curation depends on Phase 5.

## Goal

Convert stable policy clusters and repeated successful procedures into
versioned strategy skills. Skill Curator works in the learning loop, not as an
intraday trade executor.

## Allowed Write Set

- `scripts/strategy_skill_models.py`
- `scripts/strategy_skill_store.py`
- `scripts/run_skill_curator.py`
- `tests/test_strategy_skills.py`
- `db/strategy_skills/registry.json`
- `db/strategy_skills/<skill_id>/skill.md`
- `db/strategy_skills/<skill_id>/events.jsonl`

## Forbidden Write Set

- hard constraints
- official advice
- portfolio state
- execution sync
- policy events except explicit references
- direct graph action outputs

## Inputs

- adaptive policies
- outcome events
- historical action tickets
- user feedback when available
- `schema_examples/strategy_skill.example.md`

## Lifecycle

```text
draft -> candidate -> active -> strengthened -> revised -> archived
```

## Skill Document Sections

Required sections:

- purpose
- when to apply
- required inputs
- procedure
- position sizing notes
- invalidation conditions
- anti-patterns
- evidence requirements
- known failure modes
- output contract

## Implementation Steps

1. Add registry and Markdown skill validation.
2. Add skill event log with append-only lifecycle events.
3. Add curator input pack builder from policies/outcomes/tickets.
4. Make curator output draft/candidate by default.
5. Require enough outcome support or explicit user approval for active status.
6. Keep automatic active promotion disabled in the first implementation.
7. Add skill pack builder for daily analysis consumption.
8. Record skill usage and outputs on action tickets.

## Required Tests

- skill Markdown frontmatter validates
- registry entry matches skill file
- draft/candidate skill can be created from policy cluster fixture
- active promotion requires support or approval
- auto-active promotion count is zero unless explicitly enabled later
- archived skill is excluded from default skill pack
- skill output cannot hard-block or force trade
- action ticket records skill refs and outputs

Suggested commands:

```powershell
python -B -X utf8 -m py_compile scripts\strategy_skill_models.py scripts\strategy_skill_store.py scripts\run_skill_curator.py
python -B -X utf8 -m unittest tests.test_strategy_skills
python -B -X utf8 -m unittest tests.test_adaptive_policies tests.test_action_tickets
```

## Manual Verification

- Open generated `skill.md` and verify it is readable without code context.
- Confirm source policy and outcome ids exist.
- Confirm lifecycle events explain why a skill changed status.
- Confirm active skill count is capped and reviewable.

## Rollback Notes

Archive bad skills through an event when they have been referenced. During early
development, generated draft skills can be deleted if no ticket references
them.

## Promotion Gate

Phase 7 can display skills only after:

- registry and skill file contracts are stable;
- lifecycle events are auditable;
- daily skill-pack selection is deterministic;
- Skill Curator cannot edit hard constraints or execute trades.
