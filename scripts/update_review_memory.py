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
    review_memory_path,
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
    lessons = []
    if summary.get("adverse", 0) > summary.get("supportive", 0):
        lessons.append({"type": "risk", "text": "近期主动加仓建议整体偏弱，明日应提高逆势抄底的谨慎度。", "confidence": 0.72, "applies_to": "all_tactical"})
    if summary.get("supportive", 0) > 0:
        lessons.append({"type": "edge", "text": "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。", "confidence": 0.68, "applies_to": "committee_process"})
    if not lessons:
        lessons.append({"type": "neutral", "text": "当前复盘结果中性，继续积累样本，不做激进风格迁移。", "confidence": 0.55, "applies_to": "all"})
    return lessons


def build_system_prompt() -> str:
    return (
        "你是 review_memory_agent，负责把夜间复盘结果转化为第二天可用的经验记忆。"
        "你不是简单统计器，而是研究系统的反思模块。"
        "请识别哪些建议是时点问题、哪些是信号失效、哪些是风格过于激进或过于保守。"
        "自然语言字段使用简体中文，返回严格 JSON。"
    )


def build_user_prompt(review_payload: dict, memory: dict, base_date: str, horizon: int) -> str:
    return (
        f"base_date={base_date}\n"
        f"horizon={horizon}\n"
        f"source={review_payload.get('source', 'advice')}\n"
        "请基于以下复盘结果和历史记忆，提炼 lessons、bias_adjustments 与 agent_feedback。\n"
        "要求：\n"
        "1. 不要把一次偶然涨跌直接上升为长期规律。\n"
        "2. 必须区分信号失效、执行时点不佳、数据陈旧、过度追涨、过早抄底。\n"
        "3. bias_adjustments 需要能被明天的多智能体直接使用。\n"
        "4. agent_feedback 要指出哪些 agent 近期可能偏乐观或偏保守。\n\n"
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


def dedupe_records(items: list[dict], key_builder) -> list[dict]:
    seen = set()
    deduped: list[dict] = []
    for item in reversed(items):
        key = key_builder(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.reverse()
    return deduped


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
        )["response_json"]
    except Exception:
        update = fallback_memory_update(review_payload)

    memory.setdefault("lessons", [])
    memory.setdefault("review_history", [])
    memory.setdefault("bias_adjustments", [])
    memory.setdefault("agent_feedback", [])

    for lesson in update.get("lessons", []):
        lesson_record = {"base_date": base_date, "horizon": args.horizon, **lesson}
        lesson_record["source"] = args.source
        memory["lessons"].append(lesson_record)
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
            "memory_summary": update.get("summary", ""),
            "watchouts": update.get("watchouts", []),
        }
    )
    memory["lessons"] = dedupe_records(
        memory["lessons"],
        lambda item: (item.get("base_date"), item.get("horizon"), item.get("source", "advice"), item.get("type"), item.get("text"), item.get("applies_to")),
    )
    memory["bias_adjustments"] = dedupe_records(
        memory["bias_adjustments"],
        lambda item: (item.get("base_date"), item.get("horizon"), item.get("source", "advice"), item.get("scope"), item.get("target"), item.get("adjustment")),
    )
    memory["agent_feedback"] = dedupe_records(
        memory["agent_feedback"],
        lambda item: (item.get("base_date"), item.get("horizon"), item.get("source", "advice"), item.get("agent_name"), item.get("bias"), item.get("reason")),
    )
    memory["review_history"] = dedupe_records(
        memory["review_history"],
        lambda item: (item.get("base_date"), item.get("horizon"), item.get("source", "advice"), json.dumps(item.get("summary", {}), ensure_ascii=False, sort_keys=True)),
    )
    memory["lessons"] = memory["lessons"][-80:]
    memory["review_history"] = memory["review_history"][-40:]
    memory["bias_adjustments"] = memory["bias_adjustments"][-80:]
    memory["agent_feedback"] = memory["agent_feedback"][-80:]
    memory["updated_at"] = timestamp_now()
    print(dump_json(review_memory_path(agent_home), memory))


if __name__ == "__main__":
    main()
