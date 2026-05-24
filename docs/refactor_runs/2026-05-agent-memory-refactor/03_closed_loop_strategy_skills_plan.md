# 03 Closed Loop Strategy Skills Plan

Status: accepted direction, pending implementation design.

Baseline commit before this refactor: `7984fb1`.

## Goal

OKRA should evolve from a system that records past experience into a system that
autonomously forms, uses, validates, and revises reusable investment strategy
skills.

The target growth loop is:

```text
action ticket -> execution / observation -> outcome evaluation -> diagnosis
-> memory update -> adaptive policy update -> skill candidate
-> skill review / promotion -> active strategy skill -> next daily analysis
```

Long memory should support growth, not only retrieval.

## External Reference Bias

This plan adopts the user-approved direction based on Hermes Agent, OpenClaw,
and autonomous agent memory/skill systems.

Useful reference ideas:

- Skills are procedural memory: they capture how to do a recurring task.
- Skills should be selected and executed when their trigger conditions match.
- Skills should be revisable and self-improving, not static text snippets.
- Memory should feed skill formation, and skill outcomes should feed memory.

## Core Principle

OKRA should distinguish three concepts:

```text
memory = what happened
policy = what rule seems to work
skill = how to act in a recurring situation
```

The system should grow by promoting durable experience through these stages:

```text
episode memory -> adaptive policy -> strategy skill
```

## Why Strategy Skills Are Needed

A memory might say:

```text
QDII realtime estimate looked strong, but official NAV later confirmed a weaker
move.
```

A policy might say:

```text
When QDII official NAV is not confirmed, reduce add size.
```

A skill should say:

```text
QDII daily timing procedure:
1. Check official NAV delay.
2. Compare proxy and estimated NAV.
3. Check overseas market and FX.
4. If official NAV is unconfirmed, only allow conditional small add.
5. If recent estimate error is high, lower timing confidence.
```

The skill is directly usable by the strategy/trader layer during action-ticket
generation.

## Strategy Skill Format

Initial skills should be structured Markdown with JSON-like metadata. This keeps
them inspectable, editable, and easy to call from agents before building more
complex tooling.

Required fields:

- skill id
- name
- status
- scope
- version
- confidence
- trigger conditions
- required data
- procedure
- output contract
- failure modes
- related policies
- evidence refs
- success metrics

Example:

```markdown
# QDII Daily Timing Skill

status: active
scope: fund_group:qdii
version: 1
confidence: 0.74

## Trigger

Use this skill when the target fund is QDII or proxy/official NAV timing is
delayed.

## Required Data

- official_nav_date
- estimated_nav
- proxy_change_pct
- overseas_market_return
- fx_change
- holding_units
- recent action outcomes

## Procedure

1. Check whether official NAV is delayed.
2. Compare proxy movement with estimated NAV.
3. Check overseas market and FX direction.
4. If official NAV is not confirmed, cap action at conditional small add.
5. If recent estimate error is high, reduce signal confidence.

## Output

- timing_confidence
- max_size_bucket
- allowed_action_type
- required_trigger
- warning_notes

## Failure Modes

- Proxy mismatch.
- FX move dominates proxy.
- Official NAV confirms opposite move.
- Recent realtime estimate error is high.

## Evidence

- outcome:2026-05-xx
- policy:soft:qdii_delay_reduce_size
```

## Skill Lifecycle

Skills should have explicit lifecycle states.

```text
draft -> candidate -> active -> strengthened -> revised -> archived
```

### Draft

Automatically proposed by the learning system or Skill Curator Agent.

Draft skills are not used in daily analysis by default.

### Candidate

Supported by initial evidence but not trusted enough to influence action size
strongly.

Candidate skills may appear in retrieval packs as weak context.

### Active

Eligible for daily analysis. The strategy/trader agent may call the skill and
must record skill outputs in the action ticket.

### Strengthened

Repeated outcome support raises confidence or priority.

### Revised

Contradictory evidence suggests that part of the procedure should change.

### Archived

The skill is invalid, superseded, or no longer useful.

## Skill Curator Agent

This plan fully adopts a new `Skill Curator Agent`.

The Skill Curator Agent is not part of intraday action generation. It works in
the learning loop after outcomes are available.

### Inputs

- action tickets
- final actions
- risk adjustments
- execution results
- official PnL and NAV confirmation
- T+1 / T+5 / T+20 outcomes
- adaptive policies
- anti-patterns
- user feedback
- existing strategy skills
- retrieval packs used by prior decisions

### Outputs

- new skill draft
- skill candidate promotion
- skill revision proposal
- skill confidence update
- skill archive recommendation
- related policy updates
- evidence refs
- unresolved questions

### Responsibilities

- detect recurring decision procedures
- group related adaptive policies into a skill
- identify when a skill failed
- propose revisions when evidence is mixed
- keep skill procedures concise and executable
- avoid writing facts that belong in canonical facts
- avoid changing hard constraints

## Skill Participation In Daily Analysis

Before action-ticket generation, OKRA should build a `skill_pack`.

Target shape:

```json
{
  "active_skills": [
    {
      "skill_id": "skill:qdii_daily_timing",
      "reason_selected": "fund is QDII and official NAV is delayed",
      "procedure_summary": "check NAV delay, proxy, overseas market, FX, and recent estimate error",
      "required_checks": [],
      "output_contract": {}
    }
  ],
  "candidate_skills": [],
  "disabled_skills": []
}
```

The strategy/trader agent must record usage in the action ticket:

```json
{
  "skills_used": ["skill:qdii_daily_timing"],
  "skill_outputs": {
    "skill:qdii_daily_timing": {
      "timing_confidence": 0.62,
      "max_size_bucket": "small",
      "required_trigger": "official_nav_confirmed"
    }
  }
}
```

This makes skills operational rather than decorative.

## Strategy Skills Versus Adaptive Policies

Adaptive policy:

```text
QDII official NAV unconfirmed -> reduce add size.
```

Strategy skill:

```text
QDII daily timing procedure.
```

Difference:

```text
policy = one reusable rule
skill = multiple rules + data checks + procedure + output contract + failure modes
```

A skill may call or reference multiple policies.

## Skill Safety Boundaries

Automatic growth must have boundaries.

Rules:

- New skills start as draft or candidate.
- Active skills may influence action tickets, but must expose source,
  confidence, and outputs.
- Skills cannot modify hard constraints.
- Skills cannot execute trades.
- Skills cannot overwrite canonical facts.
- Skills can alter soft constraints only through adaptive policy updates.
- User can manually promote, demote, revise, or archive skills.
- Skills with direct trade-size influence require outcome support.

## Skill Outcome Evaluation

Every skill used in an action ticket should receive feedback.

Track:

- used skill id
- ticket id
- skill output
- final action
- risk adjustment
- outcome horizon
- result classification
- whether the skill helped or hurt
- contradiction evidence

Example classifications:

- helped_timing
- helped_size_control
- avoided_loss
- caused_missed_opportunity
- overfit_to_stale_signal
- irrelevant
- contradicted

## Candidate Storage Domains

Names are provisional.

- `db/strategy_skills/skills/<skill_id>.md`
- `db/strategy_skills/index.json`
- `db/strategy_skills/skill_events.jsonl`
- `db/strategy_skills/reviews/<date>.json`
- `db/strategy_skills/usage/<date>.json`

These should be tied to action tickets, outcome events, adaptive policies, and
long-memory records.

## Implementation Notes

Likely migration sequence:

1. Define strategy skill metadata and Markdown structure.
2. Add skill registry in local storage.
3. Add skill-pack builder for action-ticket generation.
4. Add `Skill Curator Agent` in nightly or after-close learning.
5. Record skill usage on action tickets.
6. Evaluate skill outcome after T+1 / T+5 / T+20.
7. Add user review controls for promote, demote, revise, and archive.

## Accepted User Decision

This plan is accepted in full as the third formal refactor direction.

The user explicitly approved the closed-loop strategy skill direction and fully
adopted the new Skill Curator Agent.
