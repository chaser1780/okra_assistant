from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from common import (
    committee_advice_path,
    dump_json,
    ensure_layout,
    llm_context_path,
    llm_raw_path,
    long_memory_runtime_path,
    load_json,
    load_llm_config,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from long_memory_store import list_memory_records, stable_memory_id, upsert_memory_record, write_domain_mirrors, write_long_memory_cycle
from multiagent_utils import call_json_agent
from rag_profile_evidence import build_memory_evidence_pack


MEMORY_AGENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "agent_name": {"type": "string"},
        "summary": {"type": "string"},
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "domain": {"type": "string"},
                    "entity_key": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "horizon_bucket": {"type": "string", "enum": ["5d", "10d", "30d", "90d", "long_term"]},
                    "memory_type": {"type": "string"},
                    "status": {"type": "string", "enum": ["candidate", "strategic", "permanent"]},
                    "confidence": {"type": "number"},
                    "valid_days": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "domain",
                    "entity_key",
                    "title",
                    "text",
                    "horizon_bucket",
                    "memory_type",
                    "status",
                    "confidence",
                    "valid_days",
                    "tags",
                    "evidence_refs",
                ],
            },
        },
    },
    "required": ["agent_name", "summary", "records"],
}

MEMORY_MANAGER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "agent_name": {"type": "string"},
        "summary": {"type": "string"},
        "records": {"type": "array", "items": MEMORY_AGENT_SCHEMA["properties"]["records"]["items"]},
    },
    "required": ["agent_name", "summary", "records"],
}

MEMORY_AGENT_PROMPTS = {
    "short_term_memory_analyst": "你负责从当天完整今日分析中提炼 5d/10d 的短期行情与风格记忆。只输出短期可失效的市场/风格/组合阶段规律，不要输出基金长期画像或执行纪律。",
    "mid_term_regime_memory_analyst": "你负责从当天完整今日分析中提炼 30d/90d 的中期市场阶段、风格轮动和组合层规律。不要输出单基金长期画像。",
    "fund_profile_memory_analyst": "你负责提炼长期基金画像，聚焦单基金慢变量、建议成功/失败模式、适配环境。输出 long_term。",
    "execution_memory_analyst": "你负责提炼长期执行纪律和操作偏差记忆，聚焦确认日、费率、转换、滑点、执行约束。输出 long_term。",
    "memory_manager": "你负责汇总多路记忆候选，去重、定级、补齐证据引用，输出最终写入长期记忆的 records。",
}


def _write_runtime(agent_home: Path, report_date: str, payload: dict) -> None:
    dump_json(long_memory_runtime_path(agent_home, report_date), payload)


def _workspace_meta(agent_home: Path, report_date: str) -> dict:
    path = agent_home / "db" / "daily_workspace" / report_date / "today_analysis_meta.json"
    return load_json(path) if path.exists() else {}


def _cycle_payload_path(agent_home: Path, report_date: str) -> Path:
    return agent_home / "db" / "daily_workspace" / report_date / "memory_cycle.json"


def _build_input_bundle(agent_home: Path, report_date: str) -> dict:
    context = load_json(llm_context_path(agent_home, report_date)) if llm_context_path(agent_home, report_date).exists() else {}
    committee = load_json(committee_advice_path(agent_home, report_date)) if committee_advice_path(agent_home, report_date).exists() else {}
    validated = load_json(agent_home / "db" / "validated_advice" / f"{report_date}.json") if (agent_home / "db" / "validated_advice" / f"{report_date}.json").exists() else {}
    aggregate = load_json(agent_home / "db" / "agent_outputs" / report_date / "aggregate.json") if (agent_home / "db" / "agent_outputs" / report_date / "aggregate.json").exists() else {}
    llm_raw = load_json(llm_raw_path(agent_home, report_date)) if llm_raw_path(agent_home, report_date).exists() else {}
    decisions = load_json(agent_home / "db" / "decisions" / f"{report_date}.json") if (agent_home / "db" / "decisions" / f"{report_date}.json").exists() else {}
    report_text = (agent_home / "reports" / "daily" / f"{report_date}.md").read_text(encoding="utf-8") if (agent_home / "reports" / "daily" / f"{report_date}.md").exists() else ""
    return {
        "report_date": report_date,
        "context": {
            "analysis_date": context.get("analysis_date", ""),
            "portfolio_summary": context.get("portfolio_summary", {}),
            "constraints": context.get("constraints", {}),
            "memory_digest": context.get("memory_digest", {}),
            "funds": [
                {
                    "fund_code": fund.get("fund_code", ""),
                    "fund_name": fund.get("fund_name", ""),
                    "role": fund.get("role", ""),
                    "style_group": fund.get("style_group", ""),
                    "quote": fund.get("quote", {}),
                    "intraday_proxy": fund.get("intraday_proxy", {}),
                    "estimated_nav": fund.get("estimated_nav", {}),
                }
                for fund in context.get("funds", []) or []
            ],
        },
        "committee": committee,
        "validated": validated,
        "aggregate": {
            "committee": aggregate.get("committee", {}),
            "failed_agents": aggregate.get("failed_agents", []),
            "degraded_ok": aggregate.get("degraded_ok", False),
        },
        "llm_raw": {
            "mode": llm_raw.get("mode", ""),
            "decision_source": llm_raw.get("decision_source", ""),
            "narrative_mode": llm_raw.get("narrative_mode", ""),
        },
        "decisions": decisions,
        "report_excerpt": report_text[:4000],
        "existing_long_memory": list_memory_records(agent_home, limit=120),
    }


def _mock_agent_output(agent_name: str, bundle: dict) -> dict:
    report_date = bundle["report_date"]
    default_map = {
        "short_term_memory_analyst": [
            {
                "domain": "market",
                "entity_key": "short_term_regime",
                "title": "Recent short-term market regime",
                "text": "Recent 5-10 day signals favor cautious, confirmation-based positioning.",
                "horizon_bucket": "5d",
                "memory_type": "market_regime_memory",
                "status": "strategic",
                "confidence": 0.66,
                "valid_days": 5,
                "tags": ["short_term", "market"],
                "evidence_refs": [f"committee:{report_date}", f"validated:{report_date}"],
            }
        ],
        "mid_term_regime_memory_analyst": [
            {
                "domain": "market",
                "entity_key": "mid_term_regime",
                "title": "Mid-term regime checkpoint",
                "text": "Recent 30-90 day structure suggests style rotation should be treated as staged rather than permanent.",
                "horizon_bucket": "30d",
                "memory_type": "market_regime_memory",
                "status": "strategic",
                "confidence": 0.7,
                "valid_days": 30,
                "tags": ["mid_term", "market"],
                "evidence_refs": [f"committee:{report_date}", f"report:{report_date}"],
            }
        ],
        "fund_profile_memory_analyst": [
            {
                "domain": "fund",
                "entity_key": "mock_fund_profile",
                "title": "Fund profile pattern",
                "text": "Fund-level behavior should be treated as long-term profile memory, not short-term market noise.",
                "horizon_bucket": "long_term",
                "memory_type": "fund_profile_memory",
                "status": "strategic",
                "confidence": 0.68,
                "valid_days": 365,
                "tags": ["fund_profile", "long_term"],
                "evidence_refs": [f"validated:{report_date}", f"decision:{report_date}"],
            }
        ],
        "execution_memory_analyst": [
            {
                "domain": "execution",
                "entity_key": "execution_discipline",
                "title": "Execution discipline",
                "text": "Execution drift should remain isolated from advice-accuracy learning and tracked as long-term execution memory.",
                "horizon_bucket": "long_term",
                "memory_type": "execution_memory",
                "status": "strategic",
                "confidence": 0.74,
                "valid_days": 365,
                "tags": ["execution", "discipline"],
                "evidence_refs": [f"decision:{report_date}", f"aggregate:{report_date}"],
            }
        ],
    }
    records = default_map.get(agent_name, [])
    if agent_name == "memory_manager":
        combined = []
        for key in ("short_term_memory_analyst", "mid_term_regime_memory_analyst", "fund_profile_memory_analyst", "execution_memory_analyst"):
            combined.extend(bundle.get("agent_outputs", {}).get(key, {}).get("records", []))
        records = combined
    return {"agent_name": agent_name, "summary": f"{agent_name} mock summary", "records": records}


def _call_memory_agent(agent_home: Path, agent_name: str, bundle: dict, *, mock: bool) -> dict:
    if mock:
        return _mock_agent_output(agent_name, bundle)
    prompt = MEMORY_AGENT_PROMPTS[agent_name]
    result = call_json_agent(
        agent_home,
        prompt,
        json.dumps(bundle, ensure_ascii=False, indent=2),
        schema=MEMORY_MANAGER_SCHEMA if agent_name == "memory_manager" else MEMORY_AGENT_SCHEMA,
        max_attempts=1,
        request_name=agent_name,
        reasoning_effort=load_llm_config(agent_home).get("model_reasoning_effort", "high"),
        max_output_tokens=2200 if agent_name == "memory_manager" else 1800,
        fallback_defaults={"agent_name": agent_name, "summary": "", "records": []},
        timeout=(10, 45),
    )
    return result["response_json"]


def _date_plus_days(report_date: str, valid_days: int) -> str:
    from datetime import datetime

    base = datetime.strptime(report_date, "%Y-%m-%d").date()
    return (base + timedelta(days=max(0, int(valid_days)))).isoformat()


def _normalize_record(report_date: str, run_meta: dict, agent_name: str, item: dict[str, Any]) -> dict[str, Any]:
    horizon_bucket = str(item.get("horizon_bucket", "long_term") or "long_term")
    valid_days = int(item.get("valid_days", 0) or 0)
    domain = str(item.get("domain", "") or "")
    metadata = {
        "tags": list(item.get("tags", []) or []),
        "valid_days": valid_days,
        "report_date": report_date,
    }
    if domain == "execution" or agent_name == "execution_memory_analyst":
        metadata["learning_scope"] = "execution_only"
        metadata["visibility"] = "execution_only"
    return {
        "memory_id": stable_memory_id(str(item.get("domain", "")), str(item.get("entity_key", "")), str(item.get("title", "")), str(item.get("memory_type", ""))),
        "memory_type": str(item.get("memory_type", "semantic") or "semantic"),
        "domain": domain,
        "horizon_bucket": horizon_bucket,
        "entity_key": str(item.get("entity_key", "") or ""),
        "title": str(item.get("title", "") or ""),
        "text": str(item.get("text", "") or ""),
        "status": str(item.get("status", "strategic") or "strategic"),
        "priority": "core" if horizon_bucket == "long_term" and str(item.get("domain", "")) in {"execution", "portfolio"} else "",
        "confidence": float(item.get("confidence", 0.0) or 0.0),
        "support_count": 0,
        "contradiction_count": 0,
        "last_supported_at": report_date,
        "last_contradicted_at": "",
        "source": "llm_long_memory_analysis",
        "valid_from": report_date,
        "valid_until": _date_plus_days(report_date, valid_days) if valid_days > 0 and horizon_bucket != "long_term" else "",
        "source_analysis_run_id": str(run_meta.get("analysis_run_id", "") or ""),
        "source_analysis_quality": str(run_meta.get("analysis_quality", "") or ""),
        "source_agent": agent_name,
        "metadata": metadata,
        "evidence_refs": [{"kind": "memory_agent", "ref": str(ref), "date": report_date} for ref in (item.get("evidence_refs", []) or [])],
    }


def _attach_memory_rag_check(agent_home: Path, report_date: str, record: dict[str, Any]) -> dict[str, Any]:
    try:
        pack = build_memory_evidence_pack(
            agent_home,
            report_date,
            domain=str(record.get("domain", "") or ""),
            entity_key=str(record.get("entity_key", "") or ""),
            title=str(record.get("title", "") or ""),
            text=str(record.get("text", "") or ""),
        )
    except Exception as exc:
        pack = {"enabled": True, "profile": "memory", "status": "failed", "fallback_reason": str(exc)}
    if not pack.get("enabled", True):
        return record
    metadata = dict(record.get("metadata", {}) or {})
    metadata["rag_memory_check"] = {
        "enabled": pack.get("enabled", True),
        "traceId": pack.get("traceId", ""),
        "hitCount": len(pack.get("hits", []) or []),
        "memoryCheck": pack.get("memoryCheck", {}),
        "fallback_reason": pack.get("fallback_reason", ""),
    }
    record["metadata"] = metadata
    if (pack.get("memoryCheck", {}) or {}).get("skipWriteRecommended"):
        record["status"] = "candidate"
        record["priority"] = "duplicate_review"
    return record


def run_memory_cycle(agent_home: Path, report_date: str, *, mock: bool = False) -> dict:
    ensure_layout(agent_home)
    run_meta = _workspace_meta(agent_home, report_date)
    if not run_meta:
        raise RuntimeError(f"Missing today analysis metadata for {report_date}.")
    if not bool(run_meta.get("memory_eligible", False)):
        raise RuntimeError(f"Today analysis for {report_date} is not memory-eligible.")

    runtime = {
        "status": "running",
        "phase": "memory_agents",
        "runId": run_meta.get("analysis_run_id", ""),
        "reportDate": report_date,
        "startedAt": timestamp_now(),
        "elapsedSeconds": 0,
        "currentStep": "short_term_memory_analyst",
        "currentAgent": "short_term_memory_analyst",
        "currentAgentStage": "memory_agents",
        "runningAgents": [],
        "failedAgents": [],
        "degradedAgents": [],
        "lastError": "",
    }
    _write_runtime(agent_home, report_date, runtime)

    bundle = _build_input_bundle(agent_home, report_date)
    agent_outputs: dict[str, dict] = {}
    for agent_name in (
        "short_term_memory_analyst",
        "mid_term_regime_memory_analyst",
        "fund_profile_memory_analyst",
        "execution_memory_analyst",
    ):
        runtime.update({"currentStep": agent_name, "currentAgent": agent_name})
        _write_runtime(agent_home, report_date, runtime)
        agent_outputs[agent_name] = _call_memory_agent(agent_home, agent_name, bundle, mock=mock)
    manager_bundle = {**bundle, "agent_outputs": agent_outputs}
    runtime.update({"currentStep": "memory_manager", "currentAgent": "memory_manager"})
    _write_runtime(agent_home, report_date, runtime)
    manager_output = _call_memory_agent(agent_home, "memory_manager", manager_bundle, mock=mock)

    written = []
    rag_memory_checks = []
    for item in manager_output.get("records", []) or []:
        record = _normalize_record(report_date, run_meta, str(manager_output.get("agent_name", "memory_manager") or "memory_manager"), item)
        record = _attach_memory_rag_check(agent_home, report_date, record)
        rag_memory_checks.append(record.get("metadata", {}).get("rag_memory_check", {}))
        written.append(upsert_memory_record(agent_home, record))
    write_domain_mirrors(agent_home)

    payload = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "status": "ok",
        "analysis_run_id": run_meta.get("analysis_run_id", ""),
        "analysis_quality": run_meta.get("analysis_quality", ""),
        "memory_eligible": True,
        "mode": "mock" if mock else "llm",
        "agent_outputs": agent_outputs,
        "manager_output": manager_output,
        "rag_memory_checks": rag_memory_checks,
        "written_count": len(written),
        "written_records": written[:40],
    }
    runtime.update(
        {
            "status": "ok",
            "phase": "completed",
            "currentStep": "",
            "currentAgent": "",
            "elapsedSeconds": 0,
        }
    )
    _write_runtime(agent_home, report_date, runtime)
    write_long_memory_cycle(agent_home, report_date, payload, status="completed")
    dump_json(_cycle_payload_path(agent_home, report_date), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-backed long-memory analysis for a completed today-analysis.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    try:
        payload = run_memory_cycle(agent_home, report_date, mock=args.mock)
        print(json.dumps({"report_date": report_date, "status": payload["status"], "written_count": payload["written_count"]}, ensure_ascii=False))
    except Exception as exc:
        failed = {
            "report_date": report_date,
            "generated_at": timestamp_now(),
            "status": "failed_retryable",
            "error": str(exc),
        }
        _write_runtime(
            agent_home,
            report_date,
            {
                "status": "failed",
                "phase": "failed",
                "runId": "",
                "reportDate": report_date,
                "startedAt": timestamp_now(),
                "elapsedSeconds": 0,
                "currentStep": "",
                "currentAgent": "",
                "currentAgentStage": "memory_agents",
                "runningAgents": [],
                "failedAgents": [],
                "degradedAgents": [],
                "lastError": str(exc),
            },
        )
        write_long_memory_cycle(agent_home, report_date, failed, status="failed")
        dump_json(_cycle_payload_path(agent_home, report_date), failed)
        raise


if __name__ == "__main__":
    main()
