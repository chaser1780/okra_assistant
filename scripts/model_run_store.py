from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from common import dump_json, timestamp_now


SCHEMA_VERSION = "model_run.v1"


def model_run_dir(agent_home: Path, created_at: str = "") -> Path:
    date_text = str(created_at or timestamp_now())[:10]
    return agent_home / "db" / "model_runs" / date_text


def write_model_run(
    agent_home: Path | str,
    *,
    config: dict[str, Any],
    request_name: str,
    request_payload: dict[str, Any],
    status: str,
    transport_name: str = "",
    attempt_count: int = 0,
    latency_ms: int | None = None,
    output_text: str = "",
    error: str = "",
    stream_incomplete: bool = False,
    report_date: str = "",
) -> dict[str, Any]:
    home = Path(agent_home)
    created_at = timestamp_now()
    provider_name = str(config.get("model_provider") or "")
    provider = (config.get("model_providers") or {}).get(provider_name, {}) or {}
    model = str(request_payload.get("model") or config.get("model") or "")
    input_hash = stable_hash(_redacted_request_shape(request_payload))
    output_hash = stable_hash(output_text) if output_text else ""
    usage = _usage_from_events(request_payload)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "modelRunId": f"model_{uuid.uuid4().hex[:16]}",
        "createdAt": created_at,
        "requestName": request_name,
        "promptVersion": f"{request_name}.v1",
        "provider": provider_name,
        "wireApi": str(provider.get("wire_api") or "responses"),
        "model": model,
        "status": status,
        "inputSnapshotHash": input_hash,
        "inputTokenCount": usage.get("inputTokenCount"),
        "outputTokenCount": usage.get("outputTokenCount"),
        "latencyMs": latency_ms,
        "retryCount": max(0, int(attempt_count or 0) - 1),
        "transportName": transport_name,
        "streamIncomplete": bool(stream_incomplete),
        "fallbackReason": "" if status == "ok" else _safe_error(error),
        "finishReason": "completed" if status == "ok" else "failed",
        "outputHash": output_hash,
    }
    path = model_run_dir(home, report_date or created_at) / f"{payload['modelRunId']}.json"
    dump_json(path, payload)
    return {**payload, "path": str(path.relative_to(home)).replace("\\", "/")}


def list_model_runs(agent_home: Path | str, report_date: str, *, limit: int = 40) -> list[dict[str, Any]]:
    home = Path(agent_home)
    base = model_run_dir(home, report_date)
    if not base.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            rows.append({**payload, "path": str(path.relative_to(home)).replace("\\", "/")})
    return rows


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redacted_request_shape(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": payload.get("model"),
        "reasoning": payload.get("reasoning"),
        "text": payload.get("text"),
        "max_output_tokens": payload.get("max_output_tokens"),
        "input": payload.get("input"),
    }


def _usage_from_events(payload: dict[str, Any]) -> dict[str, int | None]:
    # Request payloads do not contain provider usage. Keep the contract stable
    # until a Responses provider returns normalized usage data.
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "inputTokenCount": _integer(usage.get("input_tokens") or usage.get("inputTokens")),
        "outputTokenCount": _integer(usage.get("output_tokens") or usage.get("outputTokens")),
    }


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_error(value: str) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:500]
