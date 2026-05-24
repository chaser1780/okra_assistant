# 2026-05-23 Debate To Action

## Topic

Define what OKRA's debate-to-action mechanism should look like.

## User Direction

- Focus on the TradingAgents-inspired part first.
- The key change is not adding more roles, but ensuring debate produces action.
- Reduce excessive constraints and hard-coded rules.
- Avoid the current pattern where proposals are gradually withdrawn into hold.

## Initial Design Bias

- Keep analyst roles as evidence producers.
- Make bull/bear debate explicitly action-centered.
- Give the strategy/trader layer primary authority to form action proposals.
- Convert risk from a default veto layer into a hard-guardrail plus soft
  repricing layer.
- Preserve execution safety, but do not let validation become a second hidden
  decision maker.

## Details To Finalize Later

- Exact action proposal schema.
- Debate scoring method.
- Which constraints are hard guardrails versus soft preferences.
- How action outcomes feed long-memory strategy learning.

## Proposed Direction

- The central artifact should be an action ticket, not a prose committee
  summary.
- Bull and bear agents must debate action, size, timing, invalidation, and
  opportunity cost.
- Trader/strategy agent synthesizes debate into one or more action tickets.
- Risk returns hard blocks only for non-negotiable execution or safety
  violations; otherwise it reprices confidence, size, or trigger conditions.
- Portfolio selection chooses among action tickets; it should not silently
  remake the strategy into hold.
- Hold remains possible, but must be an explicit action ticket with a thesis,
  wait condition, and missed-opportunity risk.
- User accepted this architecture and added that soft constraints should be
  adaptive, self-forming, and connected to long memory. Hard constraints stay
  preserved for now and will be discussed later.

## Candidate Artifacts

- `db/action_debates/<date>.json`: structured debate transcript and scores.
- `db/action_tickets/<date>.json`: trader-generated action candidates.
- `db/final_actions/<date>.json`: hard-guardrail checked final actions.
- Long-memory input: ticket, risk adjustment, final result, and later outcome.
