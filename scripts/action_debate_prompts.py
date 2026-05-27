from __future__ import annotations

from typing import Any


ANALYST_EVIDENCE_VIEW_PROMPT = """Normalize the retrieval pack into a compact evidence view.
Keep only ids, counts, short summaries, missing-data states, and trace refs."""

BULL_CASE_PROMPT = """Argue the strongest actionable case from the compact evidence view.
Do not invent facts outside the retrieval pack references."""

BEAR_CASE_PROMPT = """Argue the strongest cautionary case from missing data, stale evidence,
anti-patterns, and hard guardrail context."""

DEBATE_REFEREE_PROMPT = """Compare bull and bear cases, then produce a shadow-only referee
verdict with uncertainty and blocking conditions made explicit."""

ACTION_FORMER_PROMPT = """Turn the referee verdict into a proposed action-ticket patch.
The output is non-executable and must not mutate official artifacts."""

HARD_GUARDRAIL_PROMPT = """Map existing ticket hard guardrails into pass/adjust/block
explanations. This is read-only and cannot create executable actions."""

SOFT_POLICY_REPRICE_PROMPT = """Apply adaptive policy and soft constraint context as
annotation or confidence repricing only. Soft policy must not hard block."""

TICKET_WRITER_PROMPT = """Prepare the final shadow debate record and proposed ticket patch.
Only shadow debate artifacts may be written."""


NODE_PROMPTS = {
    "analyst_evidence_view": ANALYST_EVIDENCE_VIEW_PROMPT,
    "bull_case": BULL_CASE_PROMPT,
    "bear_case": BEAR_CASE_PROMPT,
    "debate_referee": DEBATE_REFEREE_PROMPT,
    "action_former": ACTION_FORMER_PROMPT,
    "hard_guardrail_check": HARD_GUARDRAIL_PROMPT,
    "soft_policy_reprice": SOFT_POLICY_REPRICE_PROMPT,
    "ticket_writer": TICKET_WRITER_PROMPT,
}


def truncate_text(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def compact_item_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": str(item.get("item_id", "") or ""),
        "source_kind": str(item.get("source_kind", "") or ""),
        "source_path": str(item.get("source_path", "") or ""),
        "source_record_id": str(item.get("source_record_id", "") or ""),
        "as_of_date": str(item.get("as_of_date", "") or ""),
        "available_from": str(item.get("available_from", "") or ""),
        "status": str(item.get("status", "") or ""),
        "summary": truncate_text(item.get("summary", ""), 180),
    }


def compact_missing_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": str(item.get("field", "") or ""),
        "state": str(item.get("state", "") or ""),
        "impact": truncate_text(item.get("impact", ""), 140),
        "blocks_debate": bool(item.get("blocks_debate")),
    }
