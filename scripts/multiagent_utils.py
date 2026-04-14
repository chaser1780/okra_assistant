from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from common import dump_json, load_llm_config, timestamp_now

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
) -> dict:
    config = load_llm_config(agent_home)
    provider = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config)
    payload = {
        "model": config["model"],
        "stream": True,
        "store": False,
        "reasoning": {"effort": reasoning_effort or config.get("model_reasoning_effort", "high")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "agent_output",
                "schema": schema or GENERIC_AGENT_SCHEMA,
                "strict": True,
            }
        },
    }
    if text_verbosity:
        payload["text"]["verbosity"] = text_verbosity
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
                    parsed_json = json.loads(text)
                except json.JSONDecodeError:
                    start = text.find("{")
                    end = text.rfind("}")
                    if start >= 0 and end > start:
                        parsed_json = json.loads(text[start : end + 1])
                    else:
                        raise
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
                    "response_json": parsed_json,
                    "events": events,
                    "transport_name": transport_name,
                }
            except Exception as exc:
                last_error = exc
                joined = "".join(delta_parts).strip()
                if joined:
                    try:
                        parsed_json = json.loads(joined)
                        return {
                            "request_payload": payload,
                            "response_text": joined,
                            "response_json": parsed_json,
                            "events": events,
                            "stream_incomplete": True,
                            "transport_name": transport_name,
                        }
                    except Exception:
                        start = joined.find("{")
                        end = joined.rfind("}")
                        if start >= 0 and end > start:
                            try:
                                parsed_json = json.loads(joined[start : end + 1])
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
                                    "response_json": parsed_json,
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
