from __future__ import annotations

import argparse
import json
from datetime import timedelta

from common import (
    dump_json,
    ensure_layout,
    execution_review_result_path,
    load_review_memory,
    parse_date_text,
    resolve_agent_home,
    resolve_date,
    review_memory_candidate_path,
    review_memory_path,
    review_memory_permanent_path,
    review_memory_promotion_log_path,
    review_result_path,
    timestamp_now,
)
from multiagent_utils import call_json_agent

REVIEW_MEMORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "agent_name": {"type": "string"},
        "mode": {"type": "string"},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                    "applies_to": {"type": "string"},
                },
                "required": ["type", "text", "confidence", "applies_to"],
            },
        },
        "bias_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scope": {"type": "string"},
                    "target": {"type": "string"},
                    "adjustment": {"type": "string"},
                    "reason": {"type": "string"},
                    "ttl_days": {"type": "integer"},
                },
                "required": ["scope", "target", "adjustment", "reason", "ttl_days"],
            },
        },
        "agent_feedback": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "agent_name": {"type": "string"},
                    "bias": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["agent_name", "bias", "confidence", "reason"],
            },
        },
        "watchouts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["agent_name", "mode", "summary", "confidence", "lessons", "bias_adjustments", "agent_feedback", "watchouts"],
}


def derive_lessons(review: dict) -> list[dict]:
    summary = review.get("summary", {})
    diagnostics = review.get("diagnostic_summary", {}) or {}
    lessons = []
    if diagnostics.get("signal_failure", 0) > 0:
        lessons.append({"type": "signal", "text": "近期有信号失效样本，明日应优先检查基金本体与代理/估值映射是否一致。", "confidence": 0.76, "applies_to": "signal_validation"})
    if diagnostics.get("timing_drag", 0) > 0:
        lessons.append({"type": "timing", "text": "近期存在买入时点拖累，明日对缺少同步正向信号的加仓动作应更克制。", "confidence": 0.72, "applies_to": "tactical_entries"})
    if diagnostics.get("premature_de_risk", 0) > 0:
        lessons.append({"type": "sentiment_pattern", "text": "近期部分减仓更像过早去风险，需防止在强势主题上过早兑现。", "confidence": 0.71, "applies_to": "de_risk_timing"})
    if diagnostics.get("good_risk_reduction", 0) > 0:
        lessons.append({"type": "edge", "text": "弱势主题的风险收缩仍有验证，后续可优先处理已明确转弱的仓位。", "confidence": 0.69, "applies_to": "weak_theme_reduction"})
    if summary.get("adverse", 0) > summary.get("supportive", 0):
        lessons.append({"type": "risk", "text": "近期主动加仓建议整体偏弱，明日应提高逆势抄底的谨慎度。", "confidence": 0.72, "applies_to": "all_tactical"})
    if summary.get("supportive", 0) > 0:
        lessons.append({"type": "edge", "text": "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。", "confidence": 0.68, "applies_to": "committee_process"})
    if diagnostics.get("historical_event", 0) > 0:
        lessons.append({"type": "historical_event", "text": "近期出现具有跨周期影响的历史事件，应评估是否需要进入长期或永久记忆。", "confidence": 0.75, "applies_to": "historical_event"})
    if not lessons:
        lessons.append({"type": "neutral", "text": "当前复盘结果中性，继续积累样本，不做激进风格迁移。", "confidence": 0.55, "applies_to": "all"})
    return lessons


def build_system_prompt() -> str:
    return (
        "你是 review_memory_agent，负责把夜间复盘结果转化为第二天可用的经验记忆。"
        "请区分短期 lesson、可持续 bias adjustment、agent feedback、历史事件候选和永久记忆候选。"
        "不要把单日噪声直接升级为长期规律。返回严格 JSON。"
    )


def build_user_prompt(review_payload: dict, memory: dict, base_date: str, horizon: int) -> str:
    return (
        f"base_date={base_date}\n"
        f"horizon={horizon}\n"
        f"source={review_payload.get('source', 'advice')}\n"
        "请基于以下复盘结果和当前记忆，提炼 lesson、bias_adjustments、agent_feedback。\n\n"
        f"REVIEW_JSON\n{json.dumps(review_payload, ensure_ascii=False, indent=2)}\n\n"
        f"CURRENT_MEMORY\n{json.dumps(memory, ensure_ascii=False, indent=2)}"
    )


def fallback_memory_update(review_payload: dict) -> dict:
    return {
        "agent_name": "review_memory_agent",
        "mode": "nightly_review",
        "summary": "使用规则回退生成记忆更新。",
        "confidence": 55,
        "lessons": derive_lessons(review_payload),
        "bias_adjustments": [],
        "agent_feedback": [],
        "watchouts": ["LLM 复盘记忆智能体失败，已使用规则回退。"],
    }


def expires_on(base_date: str, ttl_days: int | None) -> str:
    base = parse_date_text(base_date)
    if base is None:
        return ""
    try:
        ttl = int(ttl_days or 0)
    except (TypeError, ValueError):
        ttl = 0
    if ttl <= 0:
        return ""
    return (base + timedelta(days=ttl)).isoformat()


def memory_id(prefix: str, base_date: str, text: str, source: str) -> str:
    import hashlib

    digest = hashlib.sha1(f"{prefix}|{base_date}|{source}|{text}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{base_date}:{digest}"


def lesson_to_record(base_date: str, horizon: int, source: str, lesson: dict) -> dict:
    lesson_type = str(lesson.get("type", "semantic") or "semantic")
    memory_type = lesson_type if lesson_type in {"historical_event", "sentiment_pattern"} else "semantic"
    scope = "review_memory"
    promotion_level = "normal"
    if lesson_type in {"historical_event", "sentiment_pattern"}:
        scope = "strategic_memory"
        promotion_level = "candidate"
    return {
        "memory_id": memory_id("lesson", base_date, lesson.get("text", ""), source),
        "memory_type": memory_type,
        "scope": scope,
        "entity_keys": [str(lesson.get("applies_to", "")).strip()] if lesson.get("applies_to") else [],
        "text": lesson.get("text", ""),
        "provenance": {"source": source, "kind": "lesson", "horizon": horizon},
        "base_date": base_date,
        "expires_on": "",
        "promotion_level": promotion_level,
        "approved_by": "",
        "confidence": float(lesson.get("confidence", 0.0) or 0.0),
        "status": "active",
        "applies_to": lesson.get("applies_to", ""),
        "source": source,
    }


def should_promote_permanent(record: dict, existing_permanent: list[dict]) -> tuple[bool, str]:
    if str(record.get("memory_type", "")) == "historical_event" and float(record.get("confidence", 0.0) or 0.0) >= 0.75:
        return True, "historical_event_high_confidence"
    text = str(record.get("text", "") or "")
    matches = [item for item in existing_permanent if str(item.get("text", "") or "") == text]
    if matches:
        return False, "already_permanent"
    return False, "needs_manual_or_repeated_validation"


def dedupe_by_id(items: list[dict]) -> list[dict]:
    seen = set()
    result: list[dict] = []
    for item in items:
        key = item.get("memory_id") or json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def dedupe_legacy(items: list[dict], key_builder) -> list[dict]:
    seen = set()
    result: list[dict] = []
    for item in items:
        key = key_builder(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Update persistent review memory from a review result.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--base-date", required=True)
    parser.add_argument("--horizon", type=int, default=0)
    parser.add_argument("--source", default="advice", choices=["advice", "execution"])
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    base_date = resolve_date(args.base_date)
    review = review_result_path(agent_home, base_date, args.horizon) if args.source == "advice" else execution_review_result_path(agent_home, base_date, args.horizon)
    review_payload = json.loads(review.read_text(encoding="utf-8"))
    memory = load_review_memory(agent_home)

    try:
        update = call_json_agent(
            agent_home,
            build_system_prompt(),
            build_user_prompt(review_payload, memory, base_date, args.horizon),
            schema=REVIEW_MEMORY_SCHEMA,
            max_attempts=1,
            reasoning_effort="medium",
            fallback_defaults={"agent_name": "review_memory_agent", "mode": "nightly_review"},
        )["response_json"]
    except Exception:
        update = fallback_memory_update(review_payload)

    records = [lesson_to_record(base_date, args.horizon, args.source, lesson) for lesson in update.get("lessons", [])]
    candidate_payload = {
        "base_date": base_date,
        "horizon": args.horizon,
        "source": args.source,
        "generated_at": timestamp_now(),
        "summary": update.get("summary", ""),
        "watchouts": update.get("watchouts", []),
        "records": records,
        "bias_adjustments": [
            {
                "memory_id": memory_id("bias", base_date, item.get("adjustment", ""), args.source),
                "memory_type": "caveat",
                "scope": "strategic_memory",
                "entity_keys": [str(item.get("scope", "")).strip(), str(item.get("target", "")).strip()],
                "text": item.get("adjustment", ""),
                "provenance": {"source": args.source, "kind": "bias_adjustment", "horizon": args.horizon},
                "base_date": base_date,
                "expires_on": expires_on(base_date, item.get("ttl_days")),
                "promotion_level": "candidate",
                "approved_by": "",
                "confidence": 0.72,
                "status": "active",
                "reason": item.get("reason", ""),
                "source": args.source,
            }
            for item in update.get("bias_adjustments", [])
        ],
        "agent_feedback": [
            {
                "memory_id": memory_id("agent_feedback", base_date, item.get("reason", ""), args.source),
                "memory_type": "procedural",
                "scope": "review_memory",
                "entity_keys": [str(item.get("agent_name", "")).strip()],
                "text": f"{item.get('agent_name', '')}: {item.get('bias', '')}",
                "provenance": {"source": args.source, "kind": "agent_feedback", "horizon": args.horizon},
                "base_date": base_date,
                "expires_on": "",
                "promotion_level": "normal",
                "approved_by": "",
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "status": "active",
                "reason": item.get("reason", ""),
                "source": args.source,
            }
            for item in update.get("agent_feedback", [])
        ],
    }
    dump_json(review_memory_candidate_path(agent_home, base_date, args.horizon, args.source), candidate_payload)

    memory.setdefault("lessons", [])
    memory.setdefault("review_history", [])
    memory.setdefault("bias_adjustments", [])
    memory.setdefault("agent_feedback", [])
    memory.setdefault("records", [])
    memory.setdefault("strategic_memory", [])
    memory.setdefault("permanent_memory", [])
    memory.setdefault("user_confirmed_memory", [])

    memory["records"] = dedupe_by_id(memory["records"] + candidate_payload["records"] + candidate_payload["agent_feedback"])
    memory["strategic_memory"] = dedupe_by_id(memory["strategic_memory"] + candidate_payload["bias_adjustments"] + [item for item in candidate_payload["records"] if item.get("scope") == "strategic_memory"])
    promotion_events = []
    for record in candidate_payload["records"] + candidate_payload["bias_adjustments"]:
        promote, reason = should_promote_permanent(record, memory["permanent_memory"])
        promotion_events.append({"memory_id": record.get("memory_id"), "promoted_to_permanent": promote, "reason": reason})
        if promote:
            promoted = dict(record)
            promoted["scope"] = "permanent_memory"
            promoted["promotion_level"] = "promoted"
            memory["permanent_memory"].append(promoted)
    memory["permanent_memory"] = dedupe_by_id(memory["permanent_memory"])

    for lesson in update.get("lessons", []):
        memory["lessons"].append({"base_date": base_date, "horizon": args.horizon, "source": args.source, **lesson})
    for item in update.get("bias_adjustments", []):
        memory["bias_adjustments"].append(
            {
                "base_date": base_date,
                "horizon": args.horizon,
                "source": args.source,
                "expires_on": expires_on(base_date, item.get("ttl_days")),
                **item,
            }
        )
    for item in update.get("agent_feedback", []):
        memory["agent_feedback"].append({"base_date": base_date, "horizon": args.horizon, "source": args.source, **item})

    memory["review_history"].append(
        {
            "base_date": base_date,
            "horizon": args.horizon,
            "source": args.source,
            "summary": review_payload.get("summary", {}),
            "diagnostic_summary": review_payload.get("diagnostic_summary", {}),
            "memory_summary": update.get("summary", ""),
            "watchouts": update.get("watchouts", []),
        }
    )

    memory["lessons"] = dedupe_legacy(
        memory["lessons"],
        lambda item: (
            item.get("base_date"),
            item.get("horizon"),
            item.get("source", "advice"),
            item.get("type"),
            item.get("text"),
            item.get("applies_to"),
        ),
    )[-120:]
    memory["review_history"] = dedupe_legacy(
        memory["review_history"],
        lambda item: (
            item.get("base_date"),
            item.get("horizon"),
            item.get("source", "advice"),
            json.dumps(item.get("summary", {}), ensure_ascii=False, sort_keys=True),
            json.dumps(item.get("diagnostic_summary", {}), ensure_ascii=False, sort_keys=True),
        ),
    )[-80:]
    memory["bias_adjustments"] = dedupe_legacy(
        memory["bias_adjustments"],
        lambda item: (
            item.get("base_date"),
            item.get("horizon"),
            item.get("source", "advice"),
            item.get("scope"),
            item.get("target"),
            item.get("adjustment"),
        ),
    )[-120:]
    memory["agent_feedback"] = dedupe_legacy(
        memory["agent_feedback"],
        lambda item: (
            item.get("base_date"),
            item.get("horizon"),
            item.get("source", "advice"),
            item.get("agent_name"),
            item.get("bias"),
            item.get("reason"),
        ),
    )[-120:]
    memory["records"] = dedupe_by_id(memory["records"])[-160:]
    memory["strategic_memory"] = dedupe_by_id(memory["strategic_memory"])[-160:]
    memory["permanent_memory"] = dedupe_by_id(memory["permanent_memory"])
    memory["updated_at"] = timestamp_now()

    dump_json(review_memory_permanent_path(agent_home), {"updated_at": memory["updated_at"], "items": memory["permanent_memory"]})
    dump_json(review_memory_promotion_log_path(agent_home, base_date, args.horizon, args.source), {"generated_at": timestamp_now(), "events": promotion_events})
    print(dump_json(review_memory_path(agent_home), memory))


if __name__ == "__main__":
    main()
