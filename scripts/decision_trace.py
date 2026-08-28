from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from common import dump_json, llm_context_path, llm_raw_path, load_json, timestamp_now, validated_advice_path
from model_run_store import list_model_runs


SCHEMA_VERSION = "decision_trace.v1"


def decision_trace_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "decision_traces" / f"{report_date}.json"


def write_decision_trace(agent_home: Path, report_date: str, *, generated_at: str = "") -> Path:
    payload = build_decision_trace(agent_home, report_date, generated_at=generated_at)
    return dump_json(decision_trace_path(agent_home, report_date), payload)


def build_decision_trace(agent_home: Path, report_date: str, *, generated_at: str = "") -> dict[str, Any]:
    validated = _read(validated_advice_path(agent_home, report_date))
    llm_raw = _read(llm_raw_path(agent_home, report_date))
    context_path = llm_context_path(agent_home, report_date)
    context = _read(context_path)
    action_ticket_path = agent_home / "db" / "action_tickets" / f"{report_date}.json"
    retrieval_pack_path = agent_home / "db" / "retrieval_packs" / f"{report_date}.json"
    debate_path = agent_home / "db" / "action_debates" / f"{report_date}.json"
    runtime_path = agent_home / "db" / "daily_workspace" / report_date / "today_analysis_runtime.json"
    today_meta_path = agent_home / "db" / "daily_workspace" / report_date / "today_analysis_meta.json"
    runtime = _read(runtime_path)
    today_meta = _read(today_meta_path)
    generated_at = generated_at or str(validated.get("generated_at") or llm_raw.get("generated_at") or timestamp_now())
    decision_cutoff = str(
        validated.get("decision_cutoff")
        or llm_raw.get("decision_cutoff")
        or today_meta.get("decision_cutoff")
        or generated_at
    )
    run_id = str(
        runtime.get("resultRunId")
        or runtime.get("runId")
        or today_meta.get("analysis_run_id")
        or today_meta.get("runId")
        or ""
    )
    model_runs = list_model_runs(agent_home, report_date)
    decisions = []
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for index, item in enumerate(validated.get(section, []) or [], start=1):
            if not isinstance(item, dict):
                continue
            decisions.append(
                _decision_record(
                    item,
                    report_date=report_date,
                    section=section,
                    index=index,
                    run_id=run_id,
                    decision_cutoff=decision_cutoff,
                    model_runs=model_runs,
                )
            )
    source_artifacts = {
        "llmContext": _artifact_ref(agent_home, context_path),
        "validatedAdvice": _artifact_ref(agent_home, validated_advice_path(agent_home, report_date)),
        "actionTickets": _artifact_ref(agent_home, action_ticket_path),
        "retrievalPack": _artifact_ref(agent_home, retrieval_pack_path),
        "actionDebate": _artifact_ref(agent_home, debate_path),
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "traceId": f"decision_{report_date}_{_stable_hash(source_artifacts)[:12]}",
        "reportDate": report_date,
        "generatedAt": generated_at,
        "simulationOnly": True,
        "formalTrack": "user_simulation",
        "decisionMode": str(validated.get("decision_mode") or llm_raw.get("decision_mode") or "canonical"),
        "decisionSource": str(validated.get("decision_source") or llm_raw.get("decision_source") or ""),
        "runId": run_id,
        "decisionCutoff": decision_cutoff,
        "executionEligible": bool(validated.get("execution_eligible")),
        "sourceSnapshotHash": _stable_hash(source_artifacts),
        "sourceArtifacts": source_artifacts,
        "modelRuns": model_runs,
        "evidenceSnapshot": {
            "itemCount": len(context.get("evidence_items", []) or []),
            "payloadHash": _stable_hash(context),
        },
        "decisions": decisions,
    }


def _decision_record(
    item: dict[str, Any],
    *,
    report_date: str,
    section: str,
    index: int,
    run_id: str,
    decision_cutoff: str,
    model_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_id = str(item.get("suggestion_id") or item.get("decision_id") or "").strip()
    if not decision_id:
        seed = f"{report_date}|{item.get('fund_code', '')}|{item.get('validated_action', '')}|{index}"
        decision_id = f"decision_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"
    evidence = [str(value).strip() for value in item.get("evidence", []) or [] if str(value).strip()]
    risks = [str(value).strip() for value in item.get("risks", []) or [] if str(value).strip()]
    model_run, model_run_scope = _decision_model_run(item, model_runs)
    return {
        "decisionId": decision_id,
        "track": "user_simulation",
        "runId": run_id,
        "decisionCutoff": decision_cutoff,
        "experimental": False,
        "fundCode": str(item.get("fund_code") or ""),
        "fundName": str(item.get("fund_name") or ""),
        "section": section,
        "action": str(item.get("validated_action") or item.get("action") or "hold"),
        "amount": item.get("validated_amount") if item.get("validated_amount") is not None else item.get("amount"),
        "confidence": item.get("confidence"),
        "evidenceRefs": [{"kind": "decision_evidence", "text": value} for value in evidence],
        "supportingSignals": [str(value) for value in item.get("source_signal_ids", []) or []],
        "opposingSignals": [str(value) for value in item.get("opposing_signal_ids", []) or []],
        "policyHits": [str(value) for value in item.get("policy_rule_hits", []) or []],
        "constraintResults": [str(value) for value in item.get("constraint_hits", []) or []],
        "risks": risks,
        "executionState": "simulated_advice",
        "executionEligible": bool(item.get("execution_eligible", True)),
        "abstentionReason": str(item.get("abstain_reason") or ""),
        "modelRunId": str(model_run.get("modelRunId") or ""),
        "promptVersion": str(model_run.get("promptVersion") or ""),
        "modelRunScope": model_run_scope,
    }


def _decision_model_run(item: dict[str, Any], model_runs: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    explicit_id = str(item.get("model_run_id") or item.get("modelRunId") or "").strip()
    explicit_prompt = str(item.get("prompt_version") or item.get("promptVersion") or "").strip()
    if explicit_id or explicit_prompt:
        matched = next((run for run in model_runs if str(run.get("modelRunId") or "") == explicit_id), {})
        return {**matched, "modelRunId": explicit_id or matched.get("modelRunId", ""), "promptVersion": explicit_prompt or matched.get("promptVersion", "")}, "decision"
    for run in model_runs:
        request_name = str(run.get("requestName") or "")
        if request_name.startswith("action_debate_"):
            return run, "pipeline"
    return {}, "unavailable"


def _artifact_ref(agent_home: Path, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path.relative_to(agent_home)).replace("\\", "/"), "exists": False, "contentHash": ""}
    return {
        "path": str(path.relative_to(agent_home)).replace("\\", "/"),
        "exists": True,
        "contentHash": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
