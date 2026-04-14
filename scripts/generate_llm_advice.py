from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from common import agent_output_dir, dump_json, ensure_layout, llm_advice_path, llm_context_path, llm_raw_path, load_json, load_llm_config, resolve_agent_home, resolve_date, timestamp_now
from models import FinalAdvice, LlmContext
from multiagent_utils import build_llm_session, consume_sse_response, describe_api_failure, extract_response_output_text

ADVICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "market_view": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "regime": {"type": "string"},
                "summary": {"type": "string"},
                "key_drivers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["regime", "summary", "key_drivers"],
        },
        "fund_decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fund_code": {"type": "string"},
                    "action": {"type": "string", "enum": ["scheduled_dca", "add", "reduce", "switch_out", "hold"]},
                    "suggest_amount": {"type": "number"},
                    "priority": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "thesis": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "agent_support": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["fund_code", "action", "suggest_amount", "priority", "confidence", "thesis", "evidence", "risks", "agent_support"],
            },
        },
        "cross_fund_observations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["market_view", "fund_decisions", "cross_fund_observations"],
}

ACTION_MAP = {
    "scheduled_dca": "scheduled_dca",
    "dca": "scheduled_dca",
    "add": "add",
    "add_small": "add",
    "add_medium": "add",
    "accumulate": "add",
    "selective_add": "add",
    "hold_or_small_add": "add",
    "reduce": "reduce",
    "trim": "reduce",
    "trim_candidate": "reduce",
    "switch_out": "switch_out",
    "switch_preferred": "switch_out",
    "avoid_chasing": "hold",
    "hold": "hold",
    "observe": "hold",
    "no_trade": "hold",
}

AMOUNT_BUCKETS = {
    "0": 0.0,
    "100": 100.0,
    "200": 200.0,
    "300": 300.0,
    "small": 100.0,
    "medium": 200.0,
    "large": 300.0,
    "small_add": 100.0,
    "medium_add": 200.0,
    "large_add": 300.0,
}


def strip_json_fence(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def build_system_prompt(personality: str) -> str:
    return (
        "你是基金组合投资委员会秘书，负责把委员会结论整理为最终建议。"
        f"你的语气风格应当是 {personality}。"
        "你必须强依赖 portfolio_trader、research_manager、risk_manager 的输出，"
        "原始组合 context 只作为核对材料，不能压过委员会共识。"
        "所有规则都视为硬约束，不得违反。"
        "不要输出收尾套话、重复总结或没有信息增量的空话。"
        "返回严格 JSON，不要 markdown，不要额外解释。"
    )


def normalize_confidence(value) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.55
    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.0, min(round(numeric, 4), 1.0))


def compact_context_for_final(context: LlmContext) -> dict:
    return {
        "analysis_date": context.get("analysis_date"),
        "mode": context.get("mode"),
        "portfolio_summary": context.get("portfolio_summary", {}),
        "constraints": context.get("constraints", {}),
        "memory_digest": context.get("memory_digest", {}),
        "funds": [
            {
                "fund_code": fund.get("fund_code"),
                "fund_name": fund.get("fund_name"),
                "role": fund.get("role"),
                "strategy_bucket": fund.get("strategy_bucket"),
                "style_group": fund.get("style_group"),
                "current_value": fund.get("current_value"),
                "holding_return_pct": fund.get("holding_return_pct"),
                "cap_value": fund.get("cap_value"),
                "quote": {
                    "day_change_pct": fund.get("quote", {}).get("day_change_pct"),
                    "week_change_pct": fund.get("quote", {}).get("week_change_pct"),
                    "month_change_pct": fund.get("quote", {}).get("month_change_pct"),
                },
                "intraday_proxy": {
                    "change_pct": fund.get("intraday_proxy", {}).get("change_pct"),
                    "stale": fund.get("intraday_proxy", {}).get("stale"),
                },
                "estimated_nav": {
                    "estimate_change_pct": fund.get("estimated_nav", {}).get("estimate_change_pct"),
                    "confidence": fund.get("estimated_nav", {}).get("confidence"),
                    "stale": fund.get("estimated_nav", {}).get("stale"),
                },
            }
            for fund in context.get("funds", [])
        ],
    }


def get_output(agent_bundle: dict, name: str) -> dict:
    return agent_bundle.get("agents", {}).get(name, {}).get("output", {})


def compact_output_for_final(output: dict) -> dict:
    return {
        "agent_name": output.get("agent_name"),
        "summary": output.get("summary"),
        "confidence": output.get("confidence"),
        "evidence_strength": output.get("evidence_strength"),
        "data_freshness": output.get("data_freshness"),
        "key_points": (output.get("key_points") or [])[:4],
        "watchouts": (output.get("watchouts") or [])[:3],
        "portfolio_view": {
            "regime": output.get("portfolio_view", {}).get("regime"),
            "risk_bias": output.get("portfolio_view", {}).get("risk_bias"),
            "key_drivers": (output.get("portfolio_view", {}).get("key_drivers") or [])[:3],
            "portfolio_implications": (output.get("portfolio_view", {}).get("portfolio_implications") or [])[:3],
        },
        "fund_views": [
            {
                "fund_code": item.get("fund_code"),
                "action_bias": item.get("action_bias"),
                "thesis": item.get("thesis"),
                "comment": item.get("comment"),
                "risks": (item.get("risks") or [])[:2],
            }
            for item in (output.get("fund_views") or [])[:4]
        ],
    }


def build_committee_bundle(agent_bundle: dict) -> dict:
    return {
        "research_manager": compact_output_for_final(get_output(agent_bundle, "research_manager")),
        "risk_manager": compact_output_for_final(get_output(agent_bundle, "risk_manager")),
        "portfolio_trader": compact_output_for_final(get_output(agent_bundle, "portfolio_trader")),
        "bull_researcher": compact_output_for_final(get_output(agent_bundle, "bull_researcher")),
        "bear_researcher": compact_output_for_final(get_output(agent_bundle, "bear_researcher")),
    }


def committee_core_agents_available(agent_bundle: dict | None) -> bool:
    if not agent_bundle:
        return False
    agents = agent_bundle.get("agents", {})
    return all(agents.get(name, {}).get("status") == "ok" for name in ("research_manager", "risk_manager", "portfolio_trader"))


def build_user_prompt(context: LlmContext, agent_bundle: dict) -> str:
    committee_bundle = build_committee_bundle(agent_bundle)
    return (
        "请基于委员会 bundle 与原始 context，输出最终组合建议。\n"
        "规则：\n"
        "1. 你必须优先依赖 portfolio_trader、research_manager、risk_manager。\n"
        "2. 如果 research_manager 和 risk_manager 冲突，默认采用更保守方案。\n"
        "3. 如果 portfolio_trader 已经给出明确 preferred_action / preferred_size_bucket，除非存在硬约束冲突，不要随意改写方向。\n"
        "4. S&P500 与纳指100核心基金只能 scheduled_dca。\n"
        "5. 固定持有债基不可交易。\n"
        "6. 现金仓基金不直接给买卖建议。\n"
        "7. tactical 基金只允许 add / reduce / switch_out / hold。\n"
        "8. suggest_amount 必须是人民币金额。\n"
        "9. 每个 tactical 决策的 agent_support 必须列 2-4 个真实影响判断的智能体。\n"
        "10. 若 allocation_drift_pct 显示短期战术仓或高波动暴露已超目标带宽，不要继续轻易新增主题仓。\n"
        "11. 长期核心仓与防守仓优先遵守结构目标，不要被单日噪音覆盖。\n"
        "12. 用少量高质量动作回答问题，不要平均分配动作给所有基金。\n"
        "13. 返回严格 JSON。\n\n"
        + "COMMITTEE_BUNDLE\n"
        + json.dumps(committee_bundle, ensure_ascii=False, indent=2)
        + "\n\nRAW_CONTEXT\n"
        + json.dumps(compact_context_for_final(context), ensure_ascii=False, indent=2)
    )


def compact_raw_payload(payload: dict) -> dict:
    def compact_event(item: dict) -> dict:
        event = dict(item or {})
        data = dict(event.get("data", {}) or {})
        if isinstance(data.get("text"), str) and len(data["text"]) > 600:
            data["text"] = data["text"][:600] + "..."
        event["data"] = data
        return event

    compact = {
        "mode": payload.get("mode"),
        "generated_at": payload.get("generated_at"),
        "transport_name": payload.get("transport_name", ""),
        "stream_incomplete": bool(payload.get("stream_incomplete", False)),
        "aggregate_all_agents_ok": bool(payload.get("aggregate_all_agents_ok", False)),
        "aggregate_degraded_ok": bool(payload.get("aggregate_degraded_ok", False)),
        "failed_agents": payload.get("failed_agents", []),
    }
    if payload.get("error"):
        compact["error"] = payload.get("error")
    if payload.get("request_payload"):
        request_payload = payload.get("request_payload", {})
        compact["request_meta"] = {
            "model": request_payload.get("model", ""),
            "max_output_tokens": request_payload.get("max_output_tokens"),
            "verbosity": request_payload.get("text", {}).get("verbosity", ""),
        }
    if payload.get("output_text"):
        output_text = str(payload.get("output_text", ""))
        compact["output_preview"] = output_text[:1200]
        compact["output_char_count"] = len(output_text)
    if payload.get("events"):
        compact["events_tail"] = [compact_event(item) for item in payload.get("events", [])[-8:]]
        compact["event_count"] = len(payload.get("events", []))
    if payload.get("advice"):
        compact["advice"] = payload.get("advice")
    return compact


def build_mock_advice(context: LlmContext, agent_bundle: dict | None = None) -> FinalAdvice:
    tactical = [fund for fund in context["funds"] if fund["role"] == "tactical"]
    ranked = sorted(tactical, key=lambda item: float(item.get("intraday_proxy", {}).get("change_pct", 0.0)), reverse=True)
    decisions = []
    top_codes = {item["fund_code"] for item in ranked[:2]}
    default_support = ["theme_analyst", "research_manager", "risk_manager", "portfolio_trader"]
    for priority, fund in enumerate(context["funds"], start=1):
        role = fund["role"]
        if role == "core_dca":
            action = "scheduled_dca"
            amount = float(fund.get("fixed_daily_buy_amount", 0.0))
            thesis = "执行既定定投计划。"
        elif role in {"fixed_hold", "cash_hub"}:
            action = "hold"
            amount = 0.0
            thesis = "维持当前角色定位，不做战术动作。"
        elif fund["fund_code"] in top_codes and float(fund.get("current_value", 0.0)) < float(fund.get("cap_value", 1000.0)):
            action = "add"
            amount = 200.0
            thesis = "盘中代理相对更强，且仓位仍低于上限。"
        else:
            action = "hold"
            amount = 0.0
            thesis = "今天没有足够强的新证据支持动作。"
        decisions.append(
            {
                "fund_code": fund["fund_code"],
                "action": action,
                "suggest_amount": amount,
                "priority": priority,
                "confidence": 0.65,
                "thesis": thesis,
                "evidence": [
                    f"1周涨跌 {fund.get('quote', {}).get('week_change_pct', 0.0)}%",
                    f"盘中代理 {fund.get('intraday_proxy', {}).get('change_pct', 0.0)}%",
                ],
                "risks": ["仅用于链路验证的 mock 输出。"],
                "agent_support": default_support[:4],
            }
        )
    return {
        "market_view": {
            "regime": "mixed",
            "summary": "市场分化仍大，适合小步、分批、受约束地行动。",
            "key_drivers": ["主题轮动", "组合收益分化", "现金仓提供缓冲"],
        },
        "fund_decisions": decisions,
        "cross_fund_observations": ["组合仍偏主题化，日内动作数量不宜过多。"],
    }


def fund_view_index(output: dict) -> dict[str, dict]:
    return {item.get("fund_code", ""): item for item in output.get("fund_views", []) if item.get("fund_code")}


def first_nonempty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list) and value:
            return value
        if value not in (None, "", []):
            return value
    return ""


def map_action(text: str, role: str) -> str:
    lowered = (text or "").strip().lower()
    if role == "core_dca":
        return "scheduled_dca"
    if role in {"fixed_hold", "cash_hub"}:
        return "hold"
    if lowered in ACTION_MAP:
        return ACTION_MAP[lowered]
    if "switch" in lowered:
        return "switch_out"
    if "reduce" in lowered or "trim" in lowered:
        return "reduce"
    if "add" in lowered or "accumulate" in lowered:
        return "add"
    return "hold"


def map_amount(bucket: str, current_value: float, cap_value: float) -> float:
    lowered = (bucket or "").strip().lower()
    if lowered == "full_exit_candidate":
        return round(current_value, 2)
    if lowered in AMOUNT_BUCKETS:
        return AMOUNT_BUCKETS[lowered]
    if lowered.isdigit():
        return float(lowered)
    if "300" in lowered:
        return 300.0
    if "200" in lowered:
        return 200.0
    if "100" in lowered:
        return 100.0
    if "full" in lowered:
        return round(current_value, 2)
    room = max(0.0, cap_value - current_value)
    return 0.0 if room < 100 else min(200.0, room)


def legacy_stance(view: dict) -> str:
    return first_nonempty(view.get("stance"), view.get("preferred_action"), view.get("action_bias"), "hold")


def build_fallback_advice_from_agents(context: LlmContext, agent_bundle: dict) -> FinalAdvice:
    trader = get_output(agent_bundle, "portfolio_trader")
    manager = get_output(agent_bundle, "research_manager")
    risk = get_output(agent_bundle, "risk_manager")
    trader_views = fund_view_index(trader)
    manager_views = fund_view_index(manager)
    risk_views = fund_view_index(risk)

    def choose_action(fund: dict) -> tuple[str, float, str, list[str], list[str]]:
        role = fund["role"]
        current_value = float(fund.get("current_value", 0.0))
        cap_value = float(fund.get("cap_value", 1000.0))
        if role == "core_dca":
            return "scheduled_dca", float(fund.get("fixed_daily_buy_amount", 0.0)), "执行既定定投计划。", ["定投规则"], []
        if role in {"fixed_hold", "cash_hub"}:
            return "hold", 0.0, "维持当前角色定位，不做战术动作。", ["角色约束"], []

        trader_view = trader_views.get(fund["fund_code"], {})
        manager_view = manager_views.get(fund["fund_code"], {})
        risk_view = risk_views.get(fund["fund_code"], {})

        primary_action_text = first_nonempty(
            trader_view.get("preferred_action"),
            trader_view.get("action_bias"),
            manager_view.get("preferred_action"),
            manager_view.get("committee_preference"),
            legacy_stance(manager_view),
        )
        action = map_action(primary_action_text, role)

        risk_decision = (risk_view.get("risk_decision") or "").lower()
        if risk_decision == "reject":
            action = map_action(first_nonempty(risk_view.get("alternative_action"), "hold"), role)
        elif risk_decision == "modify" and action == "add":
            action = "hold"

        amount = 0.0
        if action in {"add", "reduce", "switch_out"}:
            amount = map_amount(
                first_nonempty(
                    trader_view.get("preferred_size_bucket"),
                    manager_view.get("preferred_size_bucket"),
                    "200",
                ),
                current_value,
                cap_value,
            )
        thesis = first_nonempty(
            trader_view.get("thesis"),
            manager_view.get("thesis"),
            risk_view.get("thesis"),
            trader_view.get("comment"),
            manager_view.get("comment"),
            risk_view.get("comment"),
            "委员会当前没有形成足够强的新动作共识，先保持耐心。",
        )
        evidence = [
            item
            for item in [
                f"trader action: {first_nonempty(trader_view.get('preferred_action'), trader_view.get('action_bias'), 'n/a')}",
                f"manager action: {first_nonempty(manager_view.get('preferred_action'), manager_view.get('committee_preference'), legacy_stance(manager_view), 'n/a')}",
                f"risk decision: {first_nonempty(risk_view.get('risk_decision'), legacy_stance(risk_view), 'n/a')}",
                f"1周涨跌 {fund.get('quote', {}).get('week_change_pct', 0.0)}%",
                f"估值变化 {fund.get('estimated_nav', {}).get('estimate_change_pct')}",
            ]
            if item
        ]
        risks = []
        risks.extend(risk_view.get("risks", []))
        risks.extend(risk_view.get("what_can_go_wrong", []))
        risks.extend(trader_view.get("risks", []))
        if not risks:
            risks.append("最终汇总模型失败，当前结果由委员会 fallback 合成。")
        support = [name for name in ["portfolio_trader", "research_manager", "risk_manager"] if get_output(agent_bundle, name)]
        return action, amount, thesis, evidence, risks[:5]

    decisions = []
    for priority, fund in enumerate(context.get("funds", []), start=1):
        action, amount, thesis, evidence, risks = choose_action(fund)
        decisions.append(
            {
                "fund_code": fund["fund_code"],
                "action": action,
                "suggest_amount": amount,
                "priority": priority,
                "confidence": round(
                    max(
                        normalize_confidence(trader.get("confidence")),
                        normalize_confidence(manager.get("confidence")),
                        normalize_confidence(risk.get("confidence")) * 0.95,
                    ),
                    4,
                ),
                "thesis": thesis,
                "evidence": evidence,
                "risks": risks,
                "agent_support": [name for name in ["portfolio_trader", "research_manager", "risk_manager"] if get_output(agent_bundle, name)],
            }
        )

    market_view = trader.get("portfolio_view") or manager.get("portfolio_view") or risk.get("portfolio_view") or {}
    key_drivers = []
    key_drivers.extend(trader.get("key_points", [])[:3])
    key_drivers.extend(manager.get("key_points", [])[:3])
    key_drivers.extend(risk.get("key_points", [])[:2])
    if not key_drivers:
        key_drivers = ["最终汇总模型失败，已使用委员会 fallback 结果。"]
    observations = []
    observations.extend(trader.get("watchouts", [])[:2])
    observations.extend(risk.get("watchouts", [])[:2])
    observations.extend(manager.get("watchouts", [])[:2])
    if not observations:
        observations = ["当前建议由 portfolio_trader / research_manager / risk_manager 合成。"]
    return {
        "market_view": {
            "regime": market_view.get("regime", "mixed"),
            "summary": first_nonempty(trader.get("summary"), manager.get("summary"), risk.get("summary"), "委员会认为当前更适合以约束内的小步动作应对市场分化。"),
            "key_drivers": key_drivers[:6],
        },
        "fund_decisions": decisions,
        "cross_fund_observations": observations[:6],
    }


def resolve_api_key(config: dict) -> str:
    direct = config.get("api_key", "").strip()
    if direct:
        return direct
    api_key_file = config.get("api_key_file", "").strip()
    if api_key_file:
        path = Path(api_key_file)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    api_key_env = config.get("api_key_env", f"{config['model_provider'].upper()}_API_KEY")
    env_value = os.getenv(api_key_env, "").strip()
    if env_value:
        return env_value
    raise SystemExit(f"Missing API key. Checked api_key, api_key_file, and env var {api_key_env}.")


def write_final_debug_log(agent_home: Path | str, request_name: str, payload: dict) -> None:
    path = Path(agent_home) / "logs" / "llm" / f"{timestamp_now().replace(':', '-').replace('+', '_')}_{request_name}.json"
    dump_json(path, payload)


def call_responses_api(config: dict, system_prompt: str, user_prompt: str, max_attempts: int = 3, agent_home: Path | str | None = None) -> dict:
    provider_key = config["model_provider"]
    provider = config["model_providers"][provider_key]
    api_key = resolve_api_key(config)
    endpoint = provider["base_url"].rstrip("/") + "/responses"
    payload = {
        "model": config["model"],
        "stream": True,
        "store": not bool(config.get("disable_response_storage", False)),
        "reasoning": {"effort": config.get("model_reasoning_effort", "high")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "fund_portfolio_advice",
                "schema": ADVICE_SCHEMA,
                "strict": True,
            }
        },
    }
    payload["text"]["verbosity"] = "low"
    payload["max_output_tokens"] = 3200

    last_error = None
    transport_order = [("direct", False), ("env_proxy", True)]
    for attempt in range(1, max_attempts + 1):
        for transport_name, use_env_proxy in transport_order:
            delta_parts = []
            events = []
            session = build_llm_session(use_env_proxy=use_env_proxy)
            try:
                with session.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=(30, 300),
                    stream=True,
                ) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(describe_api_failure(response.status_code, response.text[:800], "final advice", transport_name))
                    parsed = consume_sse_response(response)
                    events = parsed.get("events", [])
                    delta_parts = [parsed.get("output_text", "")]

                completed = parsed.get("completed_event") or {}
                if isinstance(completed, dict) and completed.get("response"):
                    output_text = extract_response_output_text(completed["response"]).strip()
                else:
                    output_text = extract_response_output_text(completed).strip()
                if not output_text:
                    output_text = parsed.get("output_text", "").strip()
                if output_text:
                    return {
                        "request_payload": payload,
                        "output_text": output_text,
                        "events": events,
                        "stream_incomplete": bool(parsed.get("stream_error")),
                        "transport_name": transport_name,
                    }
                failed_event = parsed.get("failed_event") or {}
                error_event = parsed.get("error_event") or {}
                if failed_event:
                    if agent_home:
                        write_final_debug_log(
                            agent_home,
                            f"final_{transport_name}_failed_attempt{attempt}",
                            {
                                "request_payload": payload,
                                "events_tail": events[-20:],
                                "failed_event": failed_event,
                                "error_event": error_event,
                                "transport_name": transport_name,
                                "use_env_proxy": use_env_proxy,
                            },
                        )
                    raise RuntimeError(f"Final advice failed before output text ({transport_name}): {json.dumps(failed_event, ensure_ascii=False)}")
                if error_event:
                    if agent_home:
                        write_final_debug_log(
                            agent_home,
                            f"final_{transport_name}_error_attempt{attempt}",
                            {
                                "request_payload": payload,
                                "events_tail": events[-20:],
                                "failed_event": failed_event,
                                "error_event": error_event,
                                "transport_name": transport_name,
                                "use_env_proxy": use_env_proxy,
                            },
                        )
                    raise RuntimeError(f"Final advice error event ({transport_name}): {json.dumps(error_event, ensure_ascii=False)}")
                if agent_home:
                    write_final_debug_log(
                        agent_home,
                        f"final_{transport_name}_empty_attempt{attempt}",
                        {
                            "request_payload": payload,
                            "events_tail": events[-20:],
                            "completed_event": parsed.get("completed_event"),
                            "failed_event": failed_event,
                            "error_event": error_event,
                            "parsed_output_text": parsed.get("output_text", ""),
                            "stream_error": parsed.get("stream_error"),
                            "transport_name": transport_name,
                            "use_env_proxy": use_env_proxy,
                        },
                    )
                raise RuntimeError(f"LLM stream did not contain output_text deltas ({transport_name}).")
            except Exception as exc:
                last_error = exc
                joined = "".join(delta_parts).strip()
                if joined:
                    try:
                        json.loads(strip_json_fence(joined))
                        return {
                            "request_payload": payload,
                            "output_text": joined,
                            "events": events,
                            "stream_incomplete": True,
                            "transport_name": transport_name,
                        }
                    except Exception:
                        pass
                if agent_home:
                    write_final_debug_log(
                        agent_home,
                        f"final_{transport_name}_exception_attempt{attempt}",
                        {
                            "request_payload": payload,
                            "events_tail": events[-20:],
                            "response_text_tail": joined[-4000:] if joined else "",
                            "error": str(exc),
                            "transport_name": transport_name,
                            "use_env_proxy": use_env_proxy,
                        },
                    )
            finally:
                session.close()
        if attempt == max_attempts:
            break
        import time
        time.sleep(2 * attempt)

    raise RuntimeError(f"Final advice request failed after {max_attempts} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the configured LLM to generate portfolio advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--mock", action="store_true", help="Generate deterministic mock advice without calling the API.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    context = load_json(llm_context_path(agent_home, report_date))
    agent_bundle_path = agent_output_dir(agent_home, report_date) / "aggregate.json"
    agent_bundle = load_json(agent_bundle_path) if agent_bundle_path.exists() else None
    config = load_llm_config(agent_home)

    if not args.mock:
        if not agent_bundle:
            raise SystemExit("缺少多智能体聚合结果，无法生成最终建议。")
        if not committee_core_agents_available(agent_bundle):
            failed = ", ".join(item["agent_name"] for item in agent_bundle.get("failed_agents", []))
            raise SystemExit(f"委员会核心角色未完整成功，无法生成最终建议。失败智能体：{failed}")
        if agent_bundle.get("failed_agents") and not agent_bundle.get("degraded_ok", False):
            failed = ", ".join(item["agent_name"] for item in agent_bundle.get("failed_agents", []))
            raise SystemExit(f"多智能体存在未允许降级的失败角色。失败智能体：{failed}")

    if args.mock:
        advice = build_mock_advice(context, agent_bundle)
        raw_payload = {
            "mode": "mock",
            "generated_at": timestamp_now(),
            "advice": advice,
            "aggregate_all_agents_ok": bool(agent_bundle.get("all_agents_ok", False)) if agent_bundle else True,
            "aggregate_degraded_ok": bool(agent_bundle.get("degraded_ok", False)) if agent_bundle else False,
            "failed_agents": agent_bundle.get("failed_agents", []) if agent_bundle else [],
        }
    else:
        try:
            raw_payload = call_responses_api(
                config,
                build_system_prompt(config.get("personality", "friendly")),
                build_user_prompt(context, agent_bundle),
                agent_home=agent_home,
            )
            output_text = raw_payload.get("output_text", "")
            if not output_text:
                raise SystemExit("LLM stream did not contain output_text deltas.")
            advice = json.loads(strip_json_fence(output_text))
            raw_payload.update(
                {
                    "mode": "responses_api",
                    "generated_at": timestamp_now(),
                    "aggregate_all_agents_ok": bool(agent_bundle.get("all_agents_ok", False)),
                    "aggregate_degraded_ok": bool(agent_bundle.get("degraded_ok", False)),
                    "failed_agents": agent_bundle.get("failed_agents", []),
                }
            )
        except Exception as exc:
            advice = build_fallback_advice_from_agents(context, agent_bundle)
            raw_payload = {
                "mode": "committee_fallback",
                "generated_at": timestamp_now(),
                "error": str(exc),
                "advice": advice,
                "aggregate_all_agents_ok": bool(agent_bundle.get("all_agents_ok", False)),
                "aggregate_degraded_ok": bool(agent_bundle.get("degraded_ok", False)),
                "failed_agents": agent_bundle.get("failed_agents", []),
            }

    dump_json(llm_raw_path(agent_home, report_date), compact_raw_payload(raw_payload))
    output_path = dump_json(llm_advice_path(agent_home, report_date), advice)
    print(output_path)


if __name__ == "__main__":
    main()
