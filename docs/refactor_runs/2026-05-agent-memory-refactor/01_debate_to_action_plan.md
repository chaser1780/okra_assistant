# 01 Debate To Action Improvement Plan

Status: accepted direction, pending implementation design.

Baseline commit before this refactor: `7984fb1`.

## Goal

OKRA should move from a report-centered committee pipeline to an action-centered
debate pipeline.

The current failure pattern to remove is:

```text
many agents analyze -> manager summarizes -> risk vetoes -> validator filters
-> optimizer filters again -> most proposals become hold
```

The target pattern is:

```text
evidence generation -> action-centered debate -> action tickets -> hard
guardrails / soft repricing -> executable decisions -> outcome learning
```

The central artifact is no longer a prose analysis summary. The central artifact
is an `action_ticket`.

## Design Principle

Analyst agents produce evidence. Bull and bear agents debate action. The
strategy/trader layer owns action formation. Risk should not be the default
action-withdrawal layer. Risk should either hard-block truly unsafe actions or
soft-reprice the action by lowering amount, confidence, urgency, or adding
trigger conditions.

`hold` remains a valid action, but it must be an explicit action ticket with a
thesis, wait condition, and missed-opportunity risk. It must not be the silent
fallback when the system is uncertain.

## Role Model

### Analyst Agents

Analysts only produce evidence and signal interpretation. They do not decide
final action.

Expected output:

- facts
- signal cards
- conflict points
- missing data
- evidence references
- confidence and freshness

Examples:

- market evidence
- theme rotation evidence
- fund quality evidence
- news and event evidence
- sentiment and crowding evidence
- historical memory evidence

### Bull Agent

The bull side must argue for action, not simply write a positive view.

Required questions:

- Why should OKRA act today?
- What exact action should be taken?
- What size is justified?
- Why is acting now better than waiting?
- What would prove this action wrong?
- What is the opportunity cost of not acting?

### Bear Agent

The bear side must argue against or downsize action, not simply write a negative
view.

Required questions:

- Why should OKRA not act today?
- If action is still necessary, what smaller size or delayed trigger is safer?
- What evidence is weak, stale, or contradictory?
- What is the largest plausible downside?
- What is the benefit of waiting?

### Strategy / Trader Agent

The strategy/trader layer is the primary action-forming layer.

It reads analyst evidence and bull/bear debate, then creates one or more
structured action tickets.

Required responsibilities:

- choose action type
- choose size
- define timing and trigger
- define invalidation condition
- record which bull/bear points were accepted or rejected
- expose uncertainty instead of hiding it behind generic hold

### Risk Agent

Risk has two modes only.

Hard block:

- the action violates a non-negotiable execution or safety rule
- the action cannot be executed safely
- the action depends on missing or impossible data

Soft repricing:

- reduce amount
- reduce confidence
- change today action into conditional action
- add trigger or expiry
- add review condition

Risk should not silently rewrite a strategy decision into hold. Every adjustment
must be recorded on the action ticket.

### Portfolio Selector

The portfolio selector chooses among action tickets under budget and portfolio
constraints.

It can:

- sort competing tickets
- allocate limited cash
- avoid contradictory simultaneous actions
- trim amount if required
- leave an action as conditional or watch

It should not become another hidden strategy layer that reinterprets all action
tickets from scratch.

## Action Ticket Schema

Note: this section is the original Stage 1 sketch. The implementation contract
has since been refined in `06_execution_technical_plan.md` and the concrete
example is now `schema_examples/action_ticket.example.json`. Use
`action_verb: add | reduce | hold | scheduled_dca | switch_in | switch_out` and
`execution_mode: immediate | scheduled | conditional | watch` for coding.

Initial target shape:

```json
{
  "ticket_id": "2026-05-23:001475:add",
  "fund_code": "001475",
  "fund_name": "example fund",
  "proposed_action": "add",
  "action_verb": "add | reduce | hold | scheduled_dca | switch_in | switch_out",
  "execution_mode": "immediate | scheduled | conditional | watch",
  "size": {
    "amount": 200,
    "size_bucket": "small",
    "max_amount": 300,
    "min_effective_amount": 100
  },
  "timing": {
    "urgency": "today | this_week | wait",
    "trigger": "proxy remains strong and no negative event appears",
    "expiry": "2026-05-24"
  },
  "thesis": "why this action should be considered",
  "bull_case": ["supporting action point"],
  "bear_case": ["opposing or downsizing point"],
  "risk_adjustments": ["risk adjustment record"],
  "invalidation": {
    "condition": "what would prove the action wrong",
    "next_action": "hold | reduce | review"
  },
  "confidence": 0.68,
  "expected_edge": {
    "base": "short_term_rebound",
    "upside": "medium",
    "downside": "low_to_medium"
  },
  "evidence_refs": ["quote:xxx", "memory:yyy", "news:zzz"],
  "final_status": "proposed | adjusted | blocked | approved"
}
```

`hold` tickets must include:

- wait condition
- review trigger
- missed-opportunity risk
- reason the system is not acting today

## Action Classes

OKRA should produce three kinds of action output.

### Executable Action

An action that can be executed today after hard guardrails.

Examples:

- add 100
- reduce 200
- switch 300 from one fund to another

### Conditional Action

An action that is strategically valid but depends on an intraday, after-close,
or next-day condition.

Examples:

- add 100 if proxy remains above threshold near decision time
- reduce if official NAV confirms weakness
- switch only after sell confirmation or cash availability is clear

### Watch Action

A structured observation action, not a passive fallback.

Required fields:

- what to watch
- when to review
- what condition upgrades it into executable action
- what missed opportunity risk exists

## Constraint Model

### Hard Constraints

Hard constraints are preserved for now. Their exact boundary will be discussed
later.

Initial hard-constraint examples:

- real holding and fund identity safety
- cash and sellable amount safety
- minimum transaction size
- future-data prevention
- missing critical data
- non-tradable or execution-blocked instruments
- settlement or confirmation impossibility

### Soft Constraints

Soft constraints should not be a static, manually-maintained wall.

They should become an adaptive memory-backed layer that can form, change, and
improve through experience.

Soft constraints may come from:

- repeated successful or failed action tickets
- long-memory strategy rules
- fund-specific behavior patterns
- market-regime episodes
- user feedback
- execution outcomes
- replay experiments

Soft constraints should influence:

- action size
- urgency
- confidence
- trigger condition
- watch priority
- review cadence

They should not directly veto actions unless promoted into a hard constraint by
an explicit later design decision.

## Long-Memory Connection

Every action ticket produces auditable learning refs and outcome events. The
ticket itself must stay compact and must not become a second knowledge base.

Lifecycle:

```text
ticket proposed -> risk adjusted -> final decision -> execution result
-> T+1/T+5/T+20 outcome -> diagnosis -> memory update
```

The memory system should learn:

- which action patterns work
- which bear warnings were useful
- which risk adjustments saved losses
- which soft constraints wrongly killed opportunities
- which agent tends to be too conservative or too aggressive
- which triggers improved timing

This makes the debate layer and long-memory layer mutually reinforcing.

## Candidate Artifacts

Possible artifact layout:

- `db/action_debates/<date>.json`
- `db/action_tickets/<date>.json`
- `db/final_actions/<date>.json`
- `db/action_outcomes/<date>.json`

These names are provisional. The implementation phase should finalize paths and
compatibility with existing decision ledger and validated advice artifacts.

## Implementation Notes

This plan does not yet prescribe exact code changes.

Likely migration shape:

1. Add action-ticket schema in shadow mode.
2. Make bull/bear/trader produce action tickets alongside current outputs.
3. Convert risk output into hard block / soft repricing.
4. Keep existing validated advice as compatibility output.
5. Start outcome tracking for tickets.
6. Feed ticket outcomes into long-memory learning.

## Accepted User Adjustment

Soft constraints should be self-forming and tied to long memory. They should
grow automatically from evidence, outcomes, and strategy learning. Hard
constraints stay preserved for now and will be revisited separately.
