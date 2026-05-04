from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from common import dump_json, load_llm_config, timestamp_now

SIGNAL_CARD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "signal_id": {"type": "string"},
        "agent_name": {"type": "string"},
        "signal_type": {"type": "string"},
        "fund_code": {"type": "string"},
        "direction": {"type": "string"},
        "horizon": {"type": "string"},
        "thesis": {"type": "string"},
        "catalysts": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "invalidation": {"type": "string"},
        "portfolio_impact": {"type": "string"},
        "action_bias": {"type": "string"},
        "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "opposing_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "sentiment_relevance": {"type": "number"},
        "novelty_relevance": {"type": "number"},
        "crowding_signal": {"type": "string"},
        "confidence": {"type": "number"},
        "comment": {"type": "string"},
        "abstain_reason": {"type": "string"},
    },
    "required": [
        "signal_id",
        "agent_name",
        "signal_type",
        "fund_code",
        "direction",
        "horizon",
        "thesis",
        "catalysts",
        "risks",
        "invalidation",
        "portfolio_impact",
        "action_bias",
        "supporting_evidence_ids",
        "opposing_evidence_ids",
        "sentiment_relevance",
        "novelty_relevance",
        "crowding_signal",
        "confidence",
        "comment",
        "abstain_reason",
    ],
}

DECISION_CARD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision_id": {"type": "string"},
        "agent_name": {"type": "string"},
        "fund_code": {"type": "string"},
        "proposed_action": {"type": "string"},
        "size_bucket": {"type": "string"},
        "supporting_signal_ids": {"type": "array", "items": {"type": "string"}},
        "opposing_signal_ids": {"type": "array", "items": {"type": "string"}},
        "why_now": {"type": "string"},
        "why_not_more": {"type": "string"},
        "invalidate_when": {"type": "string"},
        "risk_decision": {"type": "string"},
        "manager_notes": {"type": "string"},
        "confidence": {"type": "number"},
        "priority": {"type": "integer"},
    },
    "required": [
        "decision_id",
        "agent_name",
        "fund_code",
        "proposed_action",
        "size_bucket",
        "supporting_signal_ids",
        "opposing_signal_ids",
        "why_now",
        "why_not_more",
        "invalidate_when",
        "risk_decision",
        "manager_notes",
        "confidence",
        "priority",
    ],
}

GENERIC_AGENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "agent_name": {"type": "string"},
        "mode": {"type": "string"},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "evidence_strength": {"type": "string", "enum": ["low", "medium", "high"]},
        "data_freshness": {"type": "string", "enum": ["fresh", "mixed", "stale"]},
        "abstain": {"type": "boolean"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "portfolio_view": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "regime": {"type": "string"},
                "risk_bias": {"type": "string"},
                "key_drivers": {"type": "array", "items": {"type": "string"}},
                "portfolio_implications": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["regime", "risk_bias", "key_drivers", "portfolio_implications"],
        },
        "fund_views": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "fund_code": {"type": "string"},
                    "direction": {"type": "string"},
                    "horizon": {"type": "string"},
                    "thesis": {"type": "string"},
                    "catalysts": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "invalidation": {"type": "string"},
                    "portfolio_impact": {"type": "string"},
                    "action_bias": {"type": "string"},
                    "comment": {"type": "string"},
                },
                "required": [
                    "fund_code",
                    "direction",
                    "horizon",
                    "thesis",
                    "catalysts",
                    "risks",
                    "invalidation",
                    "portfolio_impact",
                    "action_bias",
                    "comment",
                ],
            },
        },
        "signal_cards": {"type": "array", "items": SIGNAL_CARD_SCHEMA},
        "decision_cards": {"type": "array", "items": DECISION_CARD_SCHEMA},
        "watchouts": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "agent_name",
        "mode",
        "summary",
        "confidence",
        "evidence_strength",
        "data_freshness",
        "abstain",
        "missing_info",
        "key_points",
        "portfolio_view",
        "fund_views",
        "watchouts",
    ],
}

ANALYST_SIGNAL_SCHEMA = GENERIC_AGENT_SCHEMA
RESEARCHER_DEBATE_SCHEMA = GENERIC_AGENT_SCHEMA
MANAGER_DECISION_SCHEMA = GENERIC_AGENT_SCHEMA


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
    raise RuntimeError(f"Missing API key. Checked api_key, api_key_file, and env var {api_key_env}.")


def parse_sse_body(body: str) -> dict:
    delta_parts: list[str] = []
    events: list[dict] = []
    completed_event: dict | None = None
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        data_text = "\n".join(data_lines).strip()
        if not data_text or data_text == "[DONE]":
            continue
        event_json = json.loads(data_text)
        events.append({"event": event_name, "data": event_json})
        if event_name == "response.output_text.delta":
            delta = event_json.get("delta", "")
            if delta:
                delta_parts.append(delta)
        elif event_name == "response.completed":
            completed_event = event_json
    return {"output_text": "".join(delta_parts), "events": events, "completed_event": completed_event}


def extract_response_output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    parts: list[str] = []
    for output_item in payload.get("output", []):
        for content_item in output_item.get("content", []):
            if content_item.get("type") in {"output_text", "text"} and content_item.get("text"):
                parts.append(content_item["text"])
    return "".join(parts).strip()


def consume_sse_response(response: requests.Response) -> dict:
    delta_parts: list[str] = []
    events: list[dict] = []
    completed_event: dict | None = None
    failed_event: dict | None = None
    error_event: dict | None = None
    event_name = ""
    data_lines: list[str] = []
    stream_error = None

    try:
        for raw_line in response.iter_lines(decode_unicode=False):
            if raw_line is None:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if line == "":
                if data_lines:
                    data_text = "\n".join(data_lines).strip()
                    if data_text and data_text != "[DONE]":
                        event_json = json.loads(data_text)
                        events.append({"event": event_name, "data": event_json})
                        if event_name == "response.output_text.delta":
                            delta = event_json.get("delta", "")
                            if delta:
                                delta_parts.append(delta)
                        elif event_name == "response.completed":
                            completed_event = event_json
                        elif event_name == "response.failed":
                            failed_event = event_json
                        elif event_name == "error":
                            error_event = event_json
                event_name = ""
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
    except Exception as exc:
        stream_error = str(exc)

    if data_lines:
        data_text = "\n".join(data_lines).strip()
        if data_text and data_text != "[DONE]":
            try:
                event_json = json.loads(data_text)
                events.append({"event": event_name, "data": event_json})
                if event_name == "response.output_text.delta":
                    delta = event_json.get("delta", "")
                    if delta:
                        delta_parts.append(delta)
                elif event_name == "response.completed":
                    completed_event = event_json
                elif event_name == "response.failed":
                    failed_event = event_json
                elif event_name == "error":
                    error_event = event_json
            except Exception:
                pass

    return {
        "output_text": "".join(delta_parts),
        "events": events,
        "completed_event": completed_event,
        "failed_event": failed_event,
        "error_event": error_event,
        "stream_error": stream_error,
    }


def write_agent_debug_log(agent_home: Path | str, request_name: str, payload: dict) -> None:
    path = Path(agent_home) / "logs" / "llm" / f"{timestamp_now().replace(':', '-').replace('+', '_')}_{request_name}.json"
    dump_json(path, payload)


def build_llm_session(use_env_proxy: bool) -> requests.Session:
    session = requests.Session()
    session.trust_env = use_env_proxy
    adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "close",
            "Accept-Encoding": "identity",
            "User-Agent": "fund-daily-brief/1.0",
        }
    )
    return session


def describe_api_failure(status_code: int, snippet: str, request_kind: str, transport_name: str) -> str:
    lowered = (snippet or "").lower()
    if status_code == 400 and ("not supported" in lowered or "chatgpt account" in lowered):
        return f"{request_kind} 模型兼容性错误（{transport_name}）：{snippet}"
    return f"HTTP {status_code} from {request_kind} API ({transport_name}): {snippet}"


def strip_json_fence(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def parse_json_text(value: str):
    cleaned = strip_json_fence(value)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _schema_default(schema: dict, path: tuple[str, ...] = ()):
    explicit_defaults = {
        ("evidence_strength",): "medium",
        ("data_freshness",): "mixed",
    }
    if path in explicit_defaults:
        return explicit_defaults[path]
    if "enum" in schema:
        return schema.get("enum", [""])[0]
    schema_type = schema.get("type", "")
    if schema_type == "string":
        return ""
    if schema_type == "number":
        return 0.0
    if schema_type == "integer":
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "array":
        return []
    if schema_type == "object":
        result = {}
        properties = schema.get("properties", {}) or {}
        for key in schema.get("required", []) or []:
            child = properties.get(key, {"type": "string"})
            result[key] = _schema_default(child, path + (key,))
        return result
    return None


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "ok"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    return bool(value)


def _coerce_float(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip().replace("%", "")
    try:
        return float(text)
    except Exception:
        return 0.0


def _normalize_enum(value, enum_values: list[str], path: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if not enum_values:
        return text
    for item in enum_values:
        if lowered == str(item).lower():
            return item
    alias_map = {
        ("evidence_strength",): {
            "weak": "low",
            "normal": "medium",
            "moderate": "medium",
            "strong": "high",
        },
        ("data_freshness",): {
            "latest": "fresh",
            "current": "fresh",
            "ok": "fresh",
            "partial": "mixed",
            "degraded": "mixed",
            "old": "stale",
            "unknown": "stale",
        },
    }
    mapped = alias_map.get(path, {}).get(lowered)
    if mapped in enum_values:
        return mapped
    return _schema_default({"enum": enum_values}, path)


def normalize_json_against_schema(value, schema: dict, *, defaults: dict | None = None, path: tuple[str, ...] = ()):
    schema_type = schema.get("type", "")
    if schema_type == "object":
        source = value if isinstance(value, dict) else {}
        result = {}
        properties = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])
        for key, child_schema in properties.items():
            child_path = path + (key,)
            if key in source:
                result[key] = normalize_json_against_schema(source[key], child_schema, path=child_path)
            elif not path and defaults and key in defaults:
                result[key] = normalize_json_against_schema(defaults[key], child_schema, path=child_path)
            elif key in required:
                result[key] = _schema_default(child_schema, child_path)
        return result

    if schema_type == "array":
        item_schema = schema.get("items", {"type": "string"})
        if isinstance(value, list):
            items = value
        elif value in (None, ""):
            items = []
        elif item_schema.get("type") == "string":
            items = [value]
        else:
            items = []
        return [normalize_json_against_schema(item, item_schema, path=path + ("*",)) for item in items]

    if schema_type == "string":
        if "enum" in schema:
            return _normalize_enum(value, list(schema.get("enum", []) or []), path)
        return str(value or "").strip()

    if schema_type == "number":
        return _coerce_float(value)

    if schema_type == "integer":
        return int(round(_coerce_float(value)))

    if schema_type == "boolean":
        return _coerce_bool(value)

    return value


def call_json_agent(
    agent_home,
    system_prompt: str,
    user_prompt: str,
    schema: dict | None = None,
    max_attempts: int = 3,
    reasoning_effort: str | None = None,
    request_name: str = "agent",
    text_verbosity: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    fallback_defaults: dict | None = None,
) -> dict:
    config = load_llm_config(agent_home)
    provider = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config)
    effective_schema = schema or GENERIC_AGENT_SCHEMA
    payload = {
        "model": config["model"],
        "stream": True,
        "store": False,
        "reasoning": {"effort": reasoning_effort or config.get("model_reasoning_effort", "high")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {},
    }
    payload["text"]["verbosity"] = text_verbosity or "low"
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    last_error = None
    transport_order = [("direct", False), ("env_proxy", True)]
    for attempt in range(1, max_attempts + 1):
        for transport_name, use_env_proxy in transport_order:
            delta_parts: list[str] = []
            events: list[dict] = []
            session = build_llm_session(use_env_proxy=use_env_proxy)
            try:
                with session.post(
                    provider["base_url"].rstrip("/") + "/responses",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(30, 240),
                    stream=True,
                ) as response:
                    if response.status_code >= 400:
                        snippet = response.text[:800]
                        raise RuntimeError(describe_api_failure(response.status_code, snippet, "agent", transport_name))
                    parsed = consume_sse_response(response)
                    events = parsed.get("events", [])
                    delta_parts = [parsed.get("output_text", "")]

                completed = parsed.get("completed_event") or {}
                failed_event = parsed.get("failed_event") or {}
                error_event = parsed.get("error_event") or {}
                if isinstance(completed, dict) and completed.get("response"):
                    text = extract_response_output_text(completed["response"]).strip()
                else:
                    text = extract_response_output_text(completed).strip()
                if not text:
                    text = parsed.get("output_text", "").strip()
                if not text:
                    failure_message = ""
                    if failed_event:
                        failure_message = json.dumps(failed_event, ensure_ascii=False)
                    elif error_event:
                        failure_message = json.dumps(error_event, ensure_ascii=False)
                    write_agent_debug_log(
                        agent_home,
                        f"{request_name}_{transport_name}_empty_text_attempt{attempt}",
                        {
                            "request_payload": payload,
                            "events_tail": events[-20:],
                            "completed_event": completed,
                            "failed_event": failed_event,
                            "error_event": error_event,
                            "parsed_output_text": parsed.get("output_text", ""),
                            "stream_error": parsed.get("stream_error"),
                            "transport_name": transport_name,
                            "use_env_proxy": use_env_proxy,
                        },
                    )
                    if failure_message:
                        raise RuntimeError(f"Agent response failed before output text ({transport_name}): {failure_message}")
                    raise RuntimeError(f"Agent response did not contain output text ({transport_name}).")
                try:
                    parsed_json = parse_json_text(text)
                except json.JSONDecodeError:
                    raise
                normalized_json = normalize_json_against_schema(parsed_json, effective_schema, defaults=fallback_defaults)
                if parsed.get("stream_error"):
                    write_agent_debug_log(
                        agent_home,
                        f"{request_name}_{transport_name}_stream_recovered_attempt{attempt}",
                        {
                            "request_payload": payload,
                            "events_tail": events[-20:],
                            "completed_event": completed,
                            "response_text_tail": text[-4000:],
                            "stream_error": parsed.get("stream_error"),
                            "transport_name": transport_name,
                            "use_env_proxy": use_env_proxy,
                        },
                    )
                return {
                    "request_payload": payload,
                    "response_text": text,
                    "response_json": normalized_json,
                    "events": events,
                    "transport_name": transport_name,
                }
            except Exception as exc:
                last_error = exc
                joined = "".join(delta_parts).strip()
                if joined:
                    try:
                        parsed_json = parse_json_text(joined)
                        normalized_json = normalize_json_against_schema(parsed_json, effective_schema, defaults=fallback_defaults)
                        return {
                            "request_payload": payload,
                            "response_text": joined,
                            "response_json": normalized_json,
                            "events": events,
                            "stream_incomplete": True,
                            "transport_name": transport_name,
                        }
                    except Exception:
                        start = joined.find("{")
                        end = joined.rfind("}")
                        if start >= 0 and end > start:
                            try:
                                parsed_json = parse_json_text(joined[start : end + 1])
                                normalized_json = normalize_json_against_schema(parsed_json, effective_schema, defaults=fallback_defaults)
                                write_agent_debug_log(
                                    agent_home,
                                    f"{request_name}_{transport_name}_partial_recovered_attempt{attempt}",
                                    {
                                        "request_payload": payload,
                                        "events_tail": events[-20:],
                                        "response_text_tail": joined[-4000:],
                                        "error": str(exc),
                                        "transport_name": transport_name,
                                        "use_env_proxy": use_env_proxy,
                                    },
                                )
                                return {
                                    "request_payload": payload,
                                    "response_text": joined,
                                    "response_json": normalized_json,
                                    "events": events,
                                    "stream_incomplete": True,
                                    "transport_name": transport_name,
                                }
                            except Exception:
                                pass
                write_agent_debug_log(
                    agent_home,
                    f"{request_name}_{transport_name}_failed_attempt{attempt}",
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
        time.sleep(2 * attempt)
    raise RuntimeError(f"Agent request failed after {max_attempts} attempts: {last_error}")
