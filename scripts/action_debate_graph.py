from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from action_debate_prompts import NODE_PROMPTS, compact_item_ref, compact_missing_ref, truncate_text
from artifact_boundary import assert_refactor_write_allowed, relative_posix
from build_action_ticket_shadow import action_ticket_path
from build_layered_retrieval_pack import retrieval_pack_path
from common import dump_json, load_json, timestamp_now
from multiagent_utils import call_json_agent


SCHEMA_VERSION = "action_debate.v1"
STATE_SIZE_LIMIT_BYTES = 50000
LLM_NODE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticket_id": {"type": "string"},
                    "stance": {"type": "string"},
                    "strength": {"type": "string"},
                    "summary": {"type": "string"},
                    "verdict": {"type": "string"},
                    "uncertainty": {"type": "string"},
                    "target_status": {"type": "string"},
                    "confidence_delta": {"type": "number"},
                    "reason": {"type": "string"},
                    "non_executable": {"type": "boolean"},
                },
                "required": [
                    "ticket_id",
                    "stance",
                    "strength",
                    "summary",
                    "verdict",
                    "uncertainty",
                    "target_status",
                    "confidence_delta",
                    "reason",
                    "non_executable",
                ],
            },
        }
    },
    "required": ["items"],
}
NODE_SEQUENCE = (
    "load_retrieval_pack",
    "analyst_evidence_view",
    "bull_case",
    "bear_case",
    "debate_referee",
    "action_former",
    "hard_guardrail_check",
    "soft_policy_reprice",
    "ticket_writer",
)
FORBIDDEN_STATE_KEYS = {
    "raw_observation_refs",
    "canonical_facts",
    "derived_signals",
    "decision_history",
    "outcome_history",
    "similar_cases",
    "anti_patterns",
    "adaptive_policies",
    "strategy_skill_candidates",
    "long_text_evidence",
    "portfolio_state",
    "execution_sync",
    "official_nav",
}


class ActionDebateGraphError(ValueError):
    pass


@dataclass(slots=True)
class DebateNodeResult:
    node: str
    status: str
    summary: str
    refs: list[dict[str, Any]] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ActionDebateState:
    run_id: str
    report_date: str
    generated_at: str
    artifact_refs: dict[str, str]
    source_hashes: dict[str, str]
    node_status: dict[str, str] = field(default_factory=dict)
    node_summaries: dict[str, str] = field(default_factory=dict)
    node_refs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    compact_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    debate_refs: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    def mark(self, result: DebateNodeResult) -> None:
        self.node_status[result.node] = result.status
        self.node_summaries[result.node] = truncate_text(result.summary, 300)
        self.node_refs[result.node] = list(result.refs)
        self.compact_outputs[result.node] = dict(result.output)
        if result.error:
            self.failures.append({"node": result.node, "error": truncate_text(result.error, 300)})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def serialized_size_bytes(self) -> int:
        return len(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8"))

    def assert_compact(self) -> None:
        serialized = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
        for forbidden in FORBIDDEN_STATE_KEYS:
            if f'"{forbidden}"' in serialized:
                raise ActionDebateGraphError(f"graph state contains forbidden bulky key: {forbidden}")
        size = len(serialized.encode("utf-8"))
        if size > STATE_SIZE_LIMIT_BYTES:
            raise ActionDebateGraphError(f"graph state too large: {size} bytes")


def action_debate_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_debates" / f"{report_date}.json"


def action_debate_runtime_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "action_debates" / "runtime" / f"{report_date}.json"


def content_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_dict(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ActionDebateGraphError(f"expected JSON object at {path}")
    return payload


def degraded_contract_error(message: str) -> ActionDebateGraphError:
    return ActionDebateGraphError(message)


def source_artifacts(agent_home: Path, report_date: str) -> list[dict[str, Any]]:
    paths = [action_ticket_path(agent_home, report_date), retrieval_pack_path(agent_home, report_date)]
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        if path.exists():
            artifacts.append(
                {
                    "kind": "action_ticket" if "action_tickets" in path.parts else "retrieval_pack",
                    "path": relative_posix(path, agent_home),
                    "content_sha256": content_sha256(path),
                }
            )
    artifacts.append({"kind": "builder", "path": "scripts/action_debate_graph.py", "content_sha256": ""})
    return artifacts


def source_hashes_from_artifacts(artifacts: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item.get("path", "")): str(item.get("content_sha256", ""))
        for item in artifacts
        if item.get("content_sha256")
    }


def source_hash_for(artifact: dict[str, Any], path: str) -> str:
    for item in artifact.get("source_artifacts", []) or []:
        if item.get("path") == path:
            return str(item.get("content_sha256", "") or "")
    return ""


def validate_root_artifact_contract(artifact: dict[str, Any], *, report_date: str, schema_version: str, artifact_name: str) -> None:
    if artifact.get("schema_version") != schema_version:
        raise degraded_contract_error(f"{artifact_name} schema mismatch: {artifact.get('schema_version')!r}")
    if artifact.get("report_date") != report_date:
        raise degraded_contract_error(f"{artifact_name} report_date mismatch: {artifact.get('report_date')!r}")
    if artifact.get("write_scope") != "shadow_only":
        raise degraded_contract_error(f"{artifact_name} write_scope must be shadow_only")
    if artifact.get("non_executable") is not True:
        raise degraded_contract_error(f"{artifact_name} non_executable must be true")


def validate_child_artifact_contracts(ticket_artifact: dict[str, Any], pack_artifact: dict[str, Any], report_date: str) -> None:
    for ticket in ticket_artifact.get("tickets", []) or []:
        if ticket.get("schema_version") != "action_ticket.v1":
            raise degraded_contract_error(f"ticket schema mismatch: {ticket.get('ticket_id', '<missing-id>')}")
        if ticket.get("report_date") != report_date:
            raise degraded_contract_error(f"ticket report_date mismatch: {ticket.get('ticket_id', '<missing-id>')}")
        if ticket.get("write_scope") != "shadow_only":
            raise degraded_contract_error(f"ticket write_scope must be shadow_only: {ticket.get('ticket_id', '<missing-id>')}")
        if ticket.get("non_executable") is not True:
            raise degraded_contract_error(f"ticket non_executable must be true: {ticket.get('ticket_id', '<missing-id>')}")
    for pack in pack_artifact.get("packs", []) or []:
        if pack.get("schema_version") != "retrieval_pack.v1":
            raise degraded_contract_error(f"pack schema mismatch: {pack.get('pack_id', '<missing-id>')}")
        if pack.get("report_date") != report_date:
            raise degraded_contract_error(f"pack report_date mismatch: {pack.get('pack_id', '<missing-id>')}")
        if pack.get("write_scope") != "shadow_only":
            raise degraded_contract_error(f"pack write_scope must be shadow_only: {pack.get('pack_id', '<missing-id>')}")
        if pack.get("non_executable") is not True:
            raise degraded_contract_error(f"pack non_executable must be true: {pack.get('pack_id', '<missing-id>')}")


def validate_input_contracts(
    *,
    report_date: str,
    ticket_path: Path,
    pack_path: Path,
    ticket_artifact: dict[str, Any],
    pack_artifact: dict[str, Any],
    agent_home: Path,
) -> None:
    validate_root_artifact_contract(ticket_artifact, report_date=report_date, schema_version="action_ticket.v1", artifact_name="action_ticket")
    validate_root_artifact_contract(pack_artifact, report_date=report_date, schema_version="retrieval_pack.v1", artifact_name="retrieval_pack")
    validate_child_artifact_contracts(ticket_artifact, pack_artifact, report_date)
    expected_ticket_hash = content_sha256(ticket_path)
    expected_ticket_ref = relative_posix(ticket_path, agent_home)
    referenced_ticket_hash = source_hash_for(pack_artifact, expected_ticket_ref)
    if referenced_ticket_hash != expected_ticket_hash:
        raise degraded_contract_error(
            "retrieval_pack source action_ticket hash mismatch: "
            f"expected {expected_ticket_hash}, got {referenced_ticket_hash or '<missing>'}"
        )
    ticket_ids = {
        str(item.get("ticket_id", ""))
        for item in ticket_artifact.get("tickets", []) or []
        if isinstance(item, dict) and item.get("ticket_id")
    }
    pack_ticket_ids = {
        str((item.get("target", {}) or {}).get("ticket_id", ""))
        for item in pack_artifact.get("packs", []) or []
        if isinstance(item, dict) and (item.get("target", {}) or {}).get("ticket_id")
    }
    if ticket_ids != pack_ticket_ids:
        missing_in_pack = sorted(ticket_ids - pack_ticket_ids)
        missing_in_ticket = sorted(pack_ticket_ids - ticket_ids)
        raise degraded_contract_error(
            "retrieval_pack ticket ids do not match action_ticket ids: "
            f"missing_in_pack={missing_in_pack[:3]}, missing_in_ticket={missing_in_ticket[:3]}"
        )
    if not pack_ticket_ids:
        raise degraded_contract_error("retrieval_pack contains no ticket refs")
    if not pack_path.exists():
        raise degraded_contract_error("retrieval_pack file disappeared during contract validation")


def ticket_by_id(ticket_artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("ticket_id", "")): item
        for item in ticket_artifact.get("tickets", []) or []
        if isinstance(item, dict) and item.get("ticket_id")
    }


def pack_sort_key(pack: dict[str, Any]) -> tuple[str, str]:
    target = pack.get("target", {}) or {}
    return str(target.get("fund_code", "") or ""), str(target.get("action_verb", "") or "")


def compact_refs(items: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    return [compact_item_ref(item) for item in items[:limit]]


def compact_llm_items(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items[:limit]:
        target = item.get("target", {}) if isinstance(item.get("target"), dict) else {}
        ticket_id = str(item.get("ticket_id", "") or target.get("ticket_id", "") or "")
        compacted.append(
            {
                "ticket_id": ticket_id,
                "target": target,
                "ticket_status": str(item.get("ticket_status", "") or ""),
                "execution_mode": str(item.get("execution_mode", "") or ""),
                "validated_amount": item.get("validated_amount", 0.0),
                "confidence_label": str(item.get("confidence_label", "") or ""),
                "counts": item.get("counts", {}),
                "primary_support": truncate_text(item.get("primary_support", ""), 300),
                "primary_risk": truncate_text(item.get("primary_risk", ""), 300),
                "missing_data": list(item.get("missing_data", []) or [])[:6],
                "source_refs": list(item.get("source_refs", []) or [])[:6],
                "rag_trace_refs": list(item.get("rag_trace_refs", []) or [])[:3],
            }
        )
    return compacted


def llm_node_enabled(context: dict[str, Any]) -> bool:
    return str(context.get("debate_mode", "") or "deterministic") == "llm"


def call_debate_llm_node(
    state: ActionDebateState,
    context: dict[str, Any],
    node_name: str,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not llm_node_enabled(context) or not items:
        return {}
    system_prompt = (
        NODE_PROMPTS[node_name]
        + "\nReturn strict JSON only. Return exactly one output item for every input item, in the same order. "
        "Copy every ticket_id verbatim, including hold tickets; never filter, rank, merge, or omit an item. "
        "Do not invent facts. Every item must remain non_executable=true and must be a shadow-only proposal."
    )
    expected_by_id = {
        str(item.get("ticket_id", "") or (item.get("target", {}) or {}).get("ticket_id", "") or ""): item
        for item in items
        if item.get("ticket_id") or (item.get("target", {}) or {}).get("ticket_id")
    }
    output: dict[str, dict[str, Any]] = {}
    remaining_ids = list(expected_by_id)
    responses: list[dict[str, Any]] = []
    for request_index in range(2):
        requested_items = [expected_by_id[ticket_id] for ticket_id in remaining_ids]
        user_payload = {
            "report_date": state.report_date,
            "node": node_name,
            "write_scope": "shadow_only",
            "non_executable": True,
            "required_item_count": len(requested_items),
            "required_ticket_ids": remaining_ids,
            "items": compact_llm_items(requested_items, limit=20),
        }
        response = call_json_agent(
            context["agent_home"],
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
            schema=LLM_NODE_SCHEMA,
            max_attempts=1,
            reasoning_effort=context.get("llm_reasoning_effort") or None,
            request_name=f"action_debate_{node_name}" + ("_retry_missing" if request_index else ""),
            text_verbosity="low",
            max_output_tokens=max(3000, min(6000, len(requested_items) * 260)),
            temperature=0.0,
            timeout=(10, 120),
            report_date=state.report_date,
        )
        responses.append(response)
        response_items = {
            str(item.get("ticket_id", "") or ""): item
            for item in (response.get("response_json", {}) or {}).get("items", []) or []
            if isinstance(item, dict) and item.get("ticket_id")
        }
        extra = sorted(set(response_items) - set(remaining_ids))
        if extra:
            raise ActionDebateGraphError(f"llm node {node_name} returned unexpected ticket ids: extra={extra[:3]}")
        output.update(response_items)
        remaining_ids = [ticket_id for ticket_id in remaining_ids if ticket_id not in output]
        if not remaining_ids:
            break
    first_response_count = len((responses[0].get("response_json", {}) or {}).get("items", []) or [])
    context.setdefault("llm_node_meta", {})[node_name] = {
        "transport_name": str(responses[-1].get("transport_name", "") or ""),
        "stream_incomplete": any(bool(response.get("stream_incomplete", False)) for response in responses),
        "item_count": len(output),
        "request_count": len(responses),
        "recovered_item_count": max(0, len(output) - first_response_count),
    }
    if remaining_ids:
        response_counts = [len((response.get("response_json", {}) or {}).get("items", []) or []) for response in responses]
        raise ActionDebateGraphError(
            f"llm node {node_name} returned mismatched ticket ids after retry: "
            f"missing={sorted(remaining_ids)[:3]}, extra=[], response_counts={response_counts}"
        )
    if any(item.get("non_executable") is not True for item in output.values()):
        raise ActionDebateGraphError(f"llm node {node_name} returned executable item")
    return output


def first_summary(items: list[dict[str, Any]], fallback: str) -> str:
    for item in items:
        summary = truncate_text(item.get("summary", ""), 180)
        if summary:
            return summary
    return fallback


def confidence_label(confidence: Any) -> str:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 0.7:
        return "high"
    if value >= 0.4:
        return "medium"
    if value > 0:
        return "low"
    return "not_scored"


def risk_bias_from_ticket(ticket: dict[str, Any]) -> str:
    status = str(ticket.get("ticket_status", "") or "")
    action = str(ticket.get("action_verb", "") or "")
    if status == "blocked":
        return "blocked_by_existing_guardrail"
    if action in {"reduce", "switch_out"}:
        return "risk_reduction"
    if action in {"add", "scheduled_dca", "switch_in"}:
        return "risk_addition"
    return "watch"


def debate_id_for(report_date: str, fund_code: str, sequence: int) -> str:
    return f"debate:{report_date}:{fund_code}:{sequence:03d}"


def proposed_patch_for(ticket: dict[str, Any], status: str, confidence_delta: float = 0.0) -> dict[str, Any]:
    original_confidence = float(ticket.get("confidence", 0.0) or 0.0)
    proposed_confidence = min(1.0, max(0.0, round(original_confidence + confidence_delta, 4)))
    return {
        "ticket_id": str(ticket.get("ticket_id", "") or ""),
        "ticket_status": status,
        "non_executable": True,
        "write_scope": "shadow_only",
        "confidence": proposed_confidence,
        "debate_attached": True,
        "mutation_mode": "proposed_patch_only",
    }


def build_evidence_view(pack: dict[str, Any], ticket: dict[str, Any]) -> dict[str, Any]:
    target = pack.get("target", {}) or {}
    canonical = list(pack.get("canonical_facts", []) or [])
    all_signals = list(pack.get("derived_signals", []) or [])
    signals = [item for item in all_signals if str(item.get("status", "present") or "present") == "present"]
    stale_signals = [item for item in all_signals if item not in signals]
    raw_refs = list(pack.get("raw_observation_refs", []) or [])
    long_text = list(pack.get("long_text_evidence", []) or [])
    anti = list(pack.get("anti_patterns", []) or [])
    adaptive = list(pack.get("adaptive_policies", []) or [])
    missing = list(pack.get("missing_data", []) or [])
    missing.extend(
        {
            "field": f"derived_signal:{item.get('item_id', '')}",
            "state": str(item.get("status", "stale") or "stale"),
            "impact": "Excluded from directional support because the signal is not present/fresh.",
            "blocks_debate": False,
        }
        for item in stale_signals
    )
    return {
        "target": {
            "fund_code": str(target.get("fund_code", ticket.get("fund_code", "")) or ""),
            "fund_name": str(target.get("fund_name", ticket.get("fund_name", "")) or ""),
            "ticket_id": str(target.get("ticket_id", ticket.get("ticket_id", "")) or ""),
            "action_verb": str(target.get("action_verb", ticket.get("action_verb", "")) or ""),
        },
        "ticket_status": str(ticket.get("ticket_status", "") or ""),
        "execution_mode": str(ticket.get("execution_mode", "") or ""),
        "validated_amount": ticket.get("validated_amount", 0.0),
        "confidence_label": confidence_label(ticket.get("confidence")),
        "counts": {
            "canonical_fact_count": len(canonical),
            "derived_signal_count": len(signals),
            "raw_observation_ref_count": len(raw_refs),
            "long_text_evidence_count": len(long_text),
            "anti_pattern_count": len(anti),
            "adaptive_policy_count": len(adaptive),
            "missing_data_count": len(missing),
        },
        "primary_support": first_summary(signals + canonical + raw_refs + long_text, "No compact support summary available."),
        "primary_risk": first_summary(anti, "No anti-pattern evidence in retrieval pack."),
        "missing_data": [compact_missing_ref(item) for item in missing[:6]],
        "source_refs": compact_refs(canonical, 3) + compact_refs(signals, 2) + compact_refs(raw_refs, 2),
        "rag_trace_refs": [
            {
                "trace_id": str(ref.get("trace_id", "") or ""),
                "path": str(ref.get("path", "") or ""),
                "fallback_used": bool(ref.get("fallback_used")),
            }
            for ref in list(pack.get("rag_trace_refs", []) or [])[:3]
        ],
    }


def node_load_retrieval_pack(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    pack_artifact = context["pack_artifact"]
    packs = list(pack_artifact.get("packs", []) or [])
    state.debate_refs = [
        {
            "debate_id": debate_id_for(state.report_date, str((pack.get("target", {}) or {}).get("fund_code", "") or ""), index),
            "pack_id": str(pack.get("pack_id", "") or ""),
            "ticket_id": str((pack.get("target", {}) or {}).get("ticket_id", "") or ""),
        }
        for index, pack in enumerate(sorted(packs, key=pack_sort_key), start=1)
    ]
    return DebateNodeResult(
        node="load_retrieval_pack",
        status="ok",
        summary=f"Loaded {len(packs)} retrieval packs for {state.report_date}.",
        refs=[{"path": state.artifact_refs.get("retrieval_pack", ""), "kind": "retrieval_pack"}],
        output={"pack_count": len(packs), "debate_count": len(state.debate_refs)},
    )


def node_analyst_evidence_view(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    tickets = ticket_by_id(context["ticket_artifact"])
    views: list[dict[str, Any]] = []
    for pack in sorted(context["pack_artifact"].get("packs", []) or [], key=pack_sort_key):
        target = pack.get("target", {}) or {}
        ticket = tickets.get(str(target.get("ticket_id", "") or ""), {})
        view = build_evidence_view(pack, ticket)
        views.append(view)
    context["evidence_views"] = views
    return DebateNodeResult(
        node="analyst_evidence_view",
        status="ok",
        summary=f"Built {len(views)} compact evidence views.",
        refs=[{"prompt": "analyst_evidence_view", "mode": "deterministic"}],
        output={
            "view_count": len(views),
            "total_missing_data": sum(view["counts"]["missing_data_count"] for view in views),
            "prompt": NODE_PROMPTS["analyst_evidence_view"],
        },
    )


def node_bull_case(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    bull_cases: dict[str, dict[str, Any]] = {}
    llm_cases = call_debate_llm_node(state, context, "bull_case", context["evidence_views"])
    for view in context["evidence_views"]:
        target = view["target"]
        ticket_id = target["ticket_id"]
        action = target["action_verb"]
        amount = view["validated_amount"]
        support_strength = "moderate" if view["counts"]["derived_signal_count"] or view["counts"]["long_text_evidence_count"] else "thin"
        llm_case = llm_cases.get(ticket_id, {})
        bull_cases[ticket_id] = {
            "stance": "support_current_shadow_action",
            "support_strength": truncate_text(llm_case.get("strength") or support_strength, 80),
            "summary": truncate_text(llm_case.get("summary") or f"{action} amount {amount}: {view['primary_support']}", 240),
            "support_ref_count": len(view["source_refs"]),
            "reasoning_mode": "llm" if llm_case else "deterministic",
        }
    context["bull_cases"] = bull_cases
    meta = context.get("llm_node_meta", {}).get("bull_case", {})
    return DebateNodeResult(
        node="bull_case",
        status="ok",
        summary=f"Captured bull cases for {len(bull_cases)} tickets.",
        refs=[{"prompt": "bull_case", "mode": "llm" if llm_cases else "deterministic", **meta}],
        output={"case_count": len(bull_cases), "prompt": NODE_PROMPTS["bull_case"], "llm_item_count": len(llm_cases)},
    )


def node_bear_case(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    bear_cases: dict[str, dict[str, Any]] = {}
    llm_cases = call_debate_llm_node(state, context, "bear_case", context["evidence_views"])
    for view in context["evidence_views"]:
        target = view["target"]
        ticket_id = target["ticket_id"]
        missing_blockers = [item for item in view["missing_data"] if item.get("blocks_debate")]
        risk_strength = "high" if view["ticket_status"] == "blocked" or missing_blockers else "medium" if view["counts"]["anti_pattern_count"] else "low"
        llm_case = llm_cases.get(ticket_id, {})
        bear_cases[ticket_id] = {
            "stance": "challenge_or_limit_shadow_action",
            "risk_strength": truncate_text(llm_case.get("strength") or risk_strength, 80),
            "summary": truncate_text(llm_case.get("summary") or view["primary_risk"], 240),
            "missing_data_count": view["counts"]["missing_data_count"],
            "blocking_missing_fields": [item["field"] for item in missing_blockers],
            "reasoning_mode": "llm" if llm_case else "deterministic",
        }
    context["bear_cases"] = bear_cases
    meta = context.get("llm_node_meta", {}).get("bear_case", {})
    return DebateNodeResult(
        node="bear_case",
        status="ok",
        summary=f"Captured bear cases for {len(bear_cases)} tickets.",
        refs=[{"prompt": "bear_case", "mode": "llm" if llm_cases else "deterministic", **meta}],
        output={"case_count": len(bear_cases), "prompt": NODE_PROMPTS["bear_case"], "llm_item_count": len(llm_cases)},
    )


def referee_status(ticket_status: str, bear: dict[str, Any]) -> str:
    if ticket_status == "blocked":
        return "keep_blocked"
    if bear.get("risk_strength") == "high":
        return "degrade_to_watch"
    return "support_shadow_ticket"


def node_debate_referee(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    verdicts: dict[str, dict[str, Any]] = {}
    bull_cases = context["bull_cases"]
    bear_cases = context["bear_cases"]
    llm_verdicts = call_debate_llm_node(state, context, "debate_referee", context["evidence_views"])
    for view in context["evidence_views"]:
        ticket_id = view["target"]["ticket_id"]
        bear = bear_cases[ticket_id]
        verdict = referee_status(view["ticket_status"], bear)
        llm_verdict = llm_verdicts.get(ticket_id, {})
        verdicts[ticket_id] = {
            "verdict": truncate_text(llm_verdict.get("verdict") or verdict, 80),
            "uncertainty": truncate_text(
                llm_verdict.get("uncertainty") or ("high" if view["counts"]["missing_data_count"] > 2 else "medium" if bear["risk_strength"] != "low" else "low"),
                80,
            ),
            "summary": truncate_text(llm_verdict.get("summary") or f"Bull: {bull_cases[ticket_id]['summary']} Bear: {bear['summary']}", 280),
            "non_executable": True,
            "reasoning_mode": "llm" if llm_verdict else "deterministic",
        }
    context["referee_verdicts"] = verdicts
    meta = context.get("llm_node_meta", {}).get("debate_referee", {})
    return DebateNodeResult(
        node="debate_referee",
        status="ok",
        summary=f"Produced referee verdicts for {len(verdicts)} tickets.",
        refs=[{"prompt": "debate_referee", "mode": "llm" if llm_verdicts else "deterministic", **meta}],
        output={"verdict_count": len(verdicts), "prompt": NODE_PROMPTS["debate_referee"], "llm_item_count": len(llm_verdicts)},
    )


def action_status_from_verdict(ticket: dict[str, Any], verdict: dict[str, Any]) -> str:
    current = str(ticket.get("ticket_status", "") or "shadow_only")
    if verdict.get("verdict") == "keep_blocked":
        return "blocked"
    if verdict.get("verdict") == "degrade_to_watch":
        return "degraded"
    return current


def node_action_former(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    tickets = ticket_by_id(context["ticket_artifact"])
    drafts: dict[str, dict[str, Any]] = {}
    llm_drafts = call_debate_llm_node(state, context, "action_former", context["evidence_views"])
    for view in context["evidence_views"]:
        ticket_id = view["target"]["ticket_id"]
        ticket = tickets.get(ticket_id, {})
        verdict = context["referee_verdicts"][ticket_id]
        next_status = action_status_from_verdict(ticket, verdict)
        confidence_delta = -0.05 if verdict["uncertainty"] == "high" else 0.02 if verdict["verdict"] == "support_shadow_ticket" else 0.0
        llm_draft = llm_drafts.get(ticket_id, {})
        llm_status = str(llm_draft.get("target_status", "") or "").strip()
        if llm_status in {"shadow_only", "blocked", "degraded"} and next_status != "blocked":
            next_status = llm_status
        if llm_draft and next_status != "blocked":
            confidence_delta = float(llm_draft.get("confidence_delta", confidence_delta) or 0.0)
        drafts[ticket_id] = {
            "ticket_id": ticket_id,
            "target_status": next_status,
            "action_verb": str(ticket.get("action_verb", view["target"]["action_verb"]) or ""),
            "execution_mode": str(ticket.get("execution_mode", view["execution_mode"]) or ""),
            "validated_amount": ticket.get("validated_amount", view["validated_amount"]),
            "confidence_delta": confidence_delta,
            "reason": truncate_text(llm_draft.get("reason") or verdict["summary"], 240),
            "reasoning_mode": "llm" if llm_draft else "deterministic",
        }
    context["action_drafts"] = drafts
    meta = context.get("llm_node_meta", {}).get("action_former", {})
    return DebateNodeResult(
        node="action_former",
        status="ok",
        summary=f"Prepared proposed action patches for {len(drafts)} tickets.",
        refs=[{"prompt": "action_former", "mode": "llm" if llm_drafts else "deterministic", **meta}],
        output={"draft_count": len(drafts), "prompt": NODE_PROMPTS["action_former"], "llm_item_count": len(llm_drafts)},
    )


def node_hard_guardrail_check(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    tickets = ticket_by_id(context["ticket_artifact"])
    checks: dict[str, dict[str, Any]] = {}
    for ticket_id, draft in context["action_drafts"].items():
        ticket = tickets.get(ticket_id, {})
        guardrails = list(ticket.get("hard_guardrail_results", []) or [])
        block_count = sum(1 for item in guardrails if item.get("result") == "block")
        adjust_count = sum(1 for item in guardrails if item.get("result") == "adjust")
        if block_count:
            draft["target_status"] = "blocked"
        checks[ticket_id] = {
            "result": "block" if block_count else "adjust" if adjust_count else "pass",
            "block_count": block_count,
            "adjust_count": adjust_count,
            "guardrail_count": len(guardrails),
            "non_mutating": True,
        }
    context["hard_guardrail_checks"] = checks
    return DebateNodeResult(
        node="hard_guardrail_check",
        status="ok",
        summary=f"Mapped hard guardrails for {len(checks)} proposed patches.",
        refs=[{"prompt": "hard_guardrail_check", "mode": "read_only"}],
        output={"check_count": len(checks), "prompt": NODE_PROMPTS["hard_guardrail_check"]},
    )


def node_soft_policy_reprice(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    tickets = ticket_by_id(context["ticket_artifact"])
    repricing: dict[str, dict[str, Any]] = {}
    for ticket_id, draft in context["action_drafts"].items():
        ticket = tickets.get(ticket_id, {})
        adjustments = list(ticket.get("soft_policy_adjustments", []) or [])
        policy_delta = -0.02 * len(adjustments)
        draft["confidence_delta"] = round(float(draft.get("confidence_delta", 0.0) or 0.0) + policy_delta, 4)
        repricing[ticket_id] = {
            "soft_adjustment_count": len(adjustments),
            "confidence_delta": draft["confidence_delta"],
            "hard_blocked_by_soft_policy": False,
            "non_mutating": True,
        }
    context["soft_policy_repricing"] = repricing
    return DebateNodeResult(
        node="soft_policy_reprice",
        status="ok",
        summary=f"Annotated soft-policy repricing for {len(repricing)} proposed patches.",
        refs=[{"prompt": "soft_policy_reprice", "mode": "read_only"}],
        output={"repriced_count": len(repricing), "prompt": NODE_PROMPTS["soft_policy_reprice"]},
    )


def build_debate_record(
    *,
    state: ActionDebateState,
    sequence: int,
    pack: dict[str, Any],
    ticket: dict[str, Any],
    view: dict[str, Any],
    context: dict[str, Any],
    degraded_error: str = "",
) -> dict[str, Any]:
    target = view["target"] if view else (pack.get("target", {}) or ticket)
    fund_code = str(target.get("fund_code", ticket.get("fund_code", "")) or "")
    ticket_id = str(target.get("ticket_id", ticket.get("ticket_id", "")) or "")
    draft = context.get("action_drafts", {}).get(ticket_id, {})
    target_status = str(draft.get("target_status", ticket.get("ticket_status", "degraded")) or "degraded")
    confidence_delta = float(draft.get("confidence_delta", 0.0) or 0.0)
    if degraded_error:
        target_status = "degraded"
        confidence_delta = min(confidence_delta, -0.1)
    return {
        "debate_id": debate_id_for(state.report_date, fund_code, sequence),
        "schema_version": SCHEMA_VERSION,
        "report_date": state.report_date,
        "generated_at": state.generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "ticket_id": ticket_id,
        "pack_id": str(pack.get("pack_id", "") or ""),
        "target": {
            "fund_code": fund_code,
            "fund_name": str(target.get("fund_name", ticket.get("fund_name", "")) or ""),
            "action_verb": str(target.get("action_verb", ticket.get("action_verb", "")) or ""),
            "execution_mode": str(ticket.get("execution_mode", "") or ""),
            "risk_bias": risk_bias_from_ticket(ticket),
        },
        "node_outputs": {
            "analyst_evidence_view": view or {},
            "bull_case": context.get("bull_cases", {}).get(ticket_id, {}),
            "bear_case": context.get("bear_cases", {}).get(ticket_id, {}),
            "debate_referee": context.get("referee_verdicts", {}).get(ticket_id, {}),
            "action_former": draft,
            "hard_guardrail_check": context.get("hard_guardrail_checks", {}).get(ticket_id, {}),
            "soft_policy_reprice": context.get("soft_policy_repricing", {}).get(ticket_id, {}),
            "ticket_writer": {
                "proposed_ticket_patch": proposed_patch_for(ticket, target_status, confidence_delta),
                "writes_ticket_file": False,
                "mutation_mode": "debate_artifact_only",
            },
        },
        "ticket_status": target_status,
        "degraded": bool(degraded_error),
        "failure": {"error": truncate_text(degraded_error, 300)} if degraded_error else {},
    }


def node_ticket_writer(state: ActionDebateState, context: dict[str, Any]) -> DebateNodeResult:
    tickets = ticket_by_id(context["ticket_artifact"])
    views_by_ticket_id = {view["target"]["ticket_id"]: view for view in context.get("evidence_views", [])}
    debates: list[dict[str, Any]] = []
    for sequence, pack in enumerate(sorted(context["pack_artifact"].get("packs", []) or [], key=pack_sort_key), start=1):
        target = pack.get("target", {}) or {}
        ticket_id = str(target.get("ticket_id", "") or "")
        debates.append(
            build_debate_record(
                state=state,
                sequence=sequence,
                pack=pack,
                ticket=tickets.get(ticket_id, {}),
                view=views_by_ticket_id.get(ticket_id, {}),
                context=context,
            )
        )
    context["debates"] = debates
    return DebateNodeResult(
        node="ticket_writer",
        status="ok",
        summary=f"Prepared {len(debates)} debate records for artifact write.",
        refs=[{"path": state.artifact_refs.get("action_debate", ""), "kind": "action_debate"}],
        output={"debate_count": len(debates), "writes_ticket_file": False, "prompt": NODE_PROMPTS["ticket_writer"]},
    )


NODE_FUNCTIONS: dict[str, Callable[[ActionDebateState, dict[str, Any]], DebateNodeResult]] = {
    "load_retrieval_pack": node_load_retrieval_pack,
    "analyst_evidence_view": node_analyst_evidence_view,
    "bull_case": node_bull_case,
    "bear_case": node_bear_case,
    "debate_referee": node_debate_referee,
    "action_former": node_action_former,
    "hard_guardrail_check": node_hard_guardrail_check,
    "soft_policy_reprice": node_soft_policy_reprice,
    "ticket_writer": node_ticket_writer,
}


def degraded_debates(state: ActionDebateState, context: dict[str, Any], error: str) -> list[dict[str, Any]]:
    tickets = ticket_by_id(context.get("ticket_artifact", {}))
    debates: list[dict[str, Any]] = []
    packs = sorted(context.get("pack_artifact", {}).get("packs", []) or [], key=pack_sort_key)
    if packs:
        for sequence, pack in enumerate(packs, start=1):
            target = pack.get("target", {}) or {}
            ticket = tickets.get(str(target.get("ticket_id", "") or ""), {})
            try:
                view = build_evidence_view(pack, ticket) if ticket else {}
            except Exception:
                view = {}
            debates.append(
                build_debate_record(
                    state=state,
                    sequence=sequence,
                    pack=pack,
                    ticket=ticket,
                    view=view,
                    context=context,
                    degraded_error=error,
                )
            )
        return debates
    for sequence, ticket in enumerate(sorted(tickets.values(), key=lambda item: str(item.get("fund_code", ""))), start=1):
        pack = {
            "pack_id": "",
            "target": {
                "fund_code": ticket.get("fund_code", ""),
                "fund_name": ticket.get("fund_name", ""),
                "ticket_id": ticket.get("ticket_id", ""),
                "action_verb": ticket.get("action_verb", ""),
            },
        }
        debates.append(
            build_debate_record(
                state=state,
                sequence=sequence,
                pack=pack,
                ticket=ticket,
                view={},
                context=context,
                degraded_error=error,
            )
        )
    return debates


def build_artifact(state: ActionDebateState, context: dict[str, Any], debates: list[dict[str, Any]], status: str) -> dict[str, Any]:
    degraded_count = sum(1 for item in debates if item.get("degraded") or item.get("ticket_status") == "degraded")
    node_failure_count = len(state.failures)
    state_size = state.serialized_size_bytes()
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"action_debates:{state.report_date}",
        "artifact_kind": "action_debate_shadow",
        "report_date": state.report_date,
        "generated_at": state.generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "runtime": {
            "run_id": state.run_id,
            "graph_kind": "local_file_backed_shadow_graph",
            "debate_mode": str(context.get("debate_mode", "deterministic") or "deterministic"),
            "langgraph_dependency": "not_declared",
            "checkpoint_backend": "local_shadow_runtime_json",
            "runtime_state_path": state.artifact_refs.get("runtime", ""),
            "node_sequence": list(NODE_SEQUENCE),
            "node_status": dict(state.node_status),
            "state_size_bytes": state_size,
            "state_size_limit_bytes": STATE_SIZE_LIMIT_BYTES,
            "state_contains_refs_only": True,
        },
        "source_artifacts": list(context.get("source_artifacts", [])),
        "summary": {
            "status": status,
            "debate_count": len(debates),
            "degraded_count": degraded_count,
            "node_failure_count": node_failure_count,
            "state_size_bytes": state_size,
            "state_size_limit_bytes": STATE_SIZE_LIMIT_BYTES,
            "official_output_unchanged": True,
            "writes_ticket_file": False,
            "non_executable_violation_count": 0,
            "prompted_node_count": sum(1 for node in NODE_SEQUENCE if node in NODE_PROMPTS),
            "llm_node_count": len(context.get("llm_node_meta", {}) or {}),
        },
        "debates": debates,
    }


def write_runtime_state(agent_home: Path, state: ActionDebateState) -> Path:
    state.assert_compact()
    path = action_debate_runtime_path(agent_home, state.report_date)
    payload = {
        "schema_version": "action_debate_runtime.v1",
        "artifact_id": f"action_debate_runtime:{state.report_date}",
        "artifact_kind": "action_debate_runtime_shadow",
        "report_date": state.report_date,
        "generated_at": state.generated_at,
        "write_scope": "shadow_only",
        "non_executable": True,
        "state": state.to_dict(),
    }
    assert_refactor_write_allowed(path, payload, agent_home)
    dump_json(path, payload)
    return path


def write_action_debate_artifact(agent_home: Path, artifact: dict[str, Any]) -> Path:
    path = action_debate_path(agent_home, str(artifact.get("report_date", "") or ""))
    assert_refactor_write_allowed(path, artifact, agent_home)
    dump_json(path, artifact)
    return path


def missing_input_artifact(agent_home: Path, report_date: str, generated_at: str, missing: list[str]) -> tuple[ActionDebateState, dict[str, Any]]:
    source_refs = source_artifacts(agent_home, report_date)
    state = ActionDebateState(
        run_id=f"action_debate:{report_date}",
        report_date=report_date,
        generated_at=generated_at,
        artifact_refs={
            "action_ticket": relative_posix(action_ticket_path(agent_home, report_date), agent_home),
            "retrieval_pack": relative_posix(retrieval_pack_path(agent_home, report_date), agent_home),
            "action_debate": relative_posix(action_debate_path(agent_home, report_date), agent_home),
            "runtime": relative_posix(action_debate_runtime_path(agent_home, report_date), agent_home),
        },
        source_hashes=source_hashes_from_artifacts(source_refs),
    )
    state.mark(
        DebateNodeResult(
            "load_retrieval_pack",
            "degraded",
            "Required shadow inputs are missing.",
            refs=[{"missing": item} for item in missing],
            output={"missing_inputs": missing},
            error="missing required shadow inputs: " + ", ".join(missing),
        )
    )
    context = {"source_artifacts": source_refs, "ticket_artifact": {}, "pack_artifact": {}}
    return state, build_artifact(state, context, [], "missing_inputs")


def run_debate_graph(
    agent_home: Path,
    report_date: str,
    *,
    generated_at: str | None = None,
    fail_node: str = "",
    debate_mode: str = "deterministic",
    llm_reasoning_effort: str = "",
) -> tuple[Path, dict[str, Any]]:
    generated_at = generated_at or timestamp_now()
    if debate_mode not in {"deterministic", "llm"}:
        raise ActionDebateGraphError(f"unknown debate_mode: {debate_mode}")
    ticket_path = action_ticket_path(agent_home, report_date)
    pack_path = retrieval_pack_path(agent_home, report_date)
    debate_path = action_debate_path(agent_home, report_date)
    runtime_path = action_debate_runtime_path(agent_home, report_date)
    missing = [relative_posix(path, agent_home) for path in (ticket_path, pack_path) if not path.exists()]
    if missing:
        state, artifact = missing_input_artifact(agent_home, report_date, generated_at, missing)
        runtime_state_path = write_runtime_state(agent_home, state)
        artifact["runtime"]["runtime_state_path"] = relative_posix(runtime_state_path, agent_home)
        path = write_action_debate_artifact(agent_home, artifact)
        return path, artifact

    source_refs = source_artifacts(agent_home, report_date)
    state = ActionDebateState(
        run_id=f"action_debate:{report_date}",
        report_date=report_date,
        generated_at=generated_at,
        artifact_refs={
            "action_ticket": relative_posix(ticket_path, agent_home),
            "retrieval_pack": relative_posix(pack_path, agent_home),
            "action_debate": relative_posix(debate_path, agent_home),
            "runtime": relative_posix(runtime_path, agent_home),
        },
        source_hashes=source_hashes_from_artifacts(source_refs),
    )
    context: dict[str, Any] = {
        "agent_home": agent_home,
        "debate_mode": debate_mode,
        "llm_reasoning_effort": llm_reasoning_effort,
        "source_artifacts": source_refs,
        "ticket_artifact": load_json_dict(ticket_path),
        "pack_artifact": load_json_dict(pack_path),
    }
    status = "ok"
    debates: list[dict[str, Any]] = []
    current_node = "input_contract_check"
    try:
        validate_input_contracts(
            report_date=report_date,
            ticket_path=ticket_path,
            pack_path=pack_path,
            ticket_artifact=context["ticket_artifact"],
            pack_artifact=context["pack_artifact"],
            agent_home=agent_home,
        )
        for node_name in NODE_SEQUENCE:
            current_node = node_name
            if fail_node and node_name == fail_node:
                raise RuntimeError(f"injected failure at node {node_name}")
            result = NODE_FUNCTIONS[node_name](state, context)
            state.mark(result)
        debates = list(context.get("debates", []) or [])
    except Exception as exc:
        failed_node = fail_node or current_node
        status = "degraded"
        state.mark(
            DebateNodeResult(
                failed_node,
                "degraded",
                f"Node failed: {exc}",
                refs=[],
                output={"failure": truncate_text(str(exc), 300)},
                error=str(exc),
            )
        )
        debates = degraded_debates(state, context, str(exc))

    state.assert_compact()
    artifact = build_artifact(state, context, debates, status)
    runtime_state_path = write_runtime_state(agent_home, state)
    artifact["runtime"]["runtime_state_path"] = relative_posix(runtime_state_path, agent_home)
    path = write_action_debate_artifact(agent_home, artifact)
    return path, artifact
