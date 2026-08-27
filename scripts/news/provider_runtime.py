from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from common import dump_json, timestamp_now


RUNTIME_SCHEMA_VERSION = "news_provider_runtime.v1"
DEFAULT_MIN_INTERVAL_SECONDS = 2
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 900


def runtime_path(agent_home: Path) -> Path:
    return agent_home / "db" / "source_health" / "news_provider_runtime.json"


class NewsProviderRuntime:
    """Persistent local source guards. They are operational metadata, never research evidence."""

    def __init__(self, agent_home: Path):
        self.agent_home = agent_home
        self.path = runtime_path(agent_home)
        self.payload = _read(self.path)
        self.providers = self.payload.setdefault("providers", {})

    def allow(self, source_key: str) -> tuple[bool, str]:
        entry = self.providers.get(source_key, {}) if isinstance(self.providers.get(source_key), dict) else {}
        now = _now()
        cooldown_until = _parse(entry.get("circuitOpenUntil"))
        if cooldown_until and now < cooldown_until:
            return False, f"circuit_open_until={cooldown_until.isoformat(timespec='seconds')}"
        last_attempt = _parse(entry.get("lastAttemptAt"))
        if last_attempt and (now - last_attempt).total_seconds() < DEFAULT_MIN_INTERVAL_SECONDS:
            return False, f"rate_limited_min_interval={DEFAULT_MIN_INTERVAL_SECONDS}s"
        return True, ""

    def record(self, health: dict[str, Any]) -> dict[str, Any]:
        source_key = str(health.get("source_key") or "")
        if not source_key:
            return health
        entry = self.providers.get(source_key, {}) if isinstance(self.providers.get(source_key), dict) else {}
        error_count = int(health.get("error_count", 0) or 0)
        status = str(health.get("status") or "unknown")
        failed = error_count > 0 or status == "error"
        failures = int(entry.get("consecutiveFailures", 0) or 0) + 1 if failed else 0
        now = timestamp_now()
        cooldown = ""
        if failures >= DEFAULT_FAILURE_THRESHOLD:
            cooldown = (_now() + timedelta(seconds=DEFAULT_COOLDOWN_SECONDS)).isoformat(timespec="seconds")
        updated = {
            "sourceKey": source_key,
            "provider": str(health.get("provider") or ""),
            "sourceRole": str(health.get("source_role") or ""),
            "consecutiveFailures": failures,
            "lastAttemptAt": now,
            "lastStatus": status,
            "lastErrorCount": error_count,
            "circuitOpenUntil": cooldown,
            "updatedAt": now,
        }
        self.providers[source_key] = updated
        enriched = dict(health)
        enriched["runtime"] = {
            "consecutive_failures": failures,
            "circuit_open": bool(cooldown),
            "circuit_open_until": cooldown,
            "min_interval_seconds": DEFAULT_MIN_INTERVAL_SECONDS,
        }
        if cooldown:
            enriched["status"] = "warning"
            enriched["warning_count"] = max(1, int(enriched.get("warning_count", 0) or 0))
            enriched["notes"] = [*list(enriched.get("notes", []) or []), f"circuit_open_until={cooldown}"]
        return enriched

    def skipped_health(self, *, source_key: str, source_role: str, provider: str, reason: str) -> dict[str, Any]:
        entry = self.providers.get(source_key, {}) if isinstance(self.providers.get(source_key), dict) else {}
        return {
            "source_key": source_key,
            "source_role": source_role,
            "provider": provider,
            "configured": True,
            "status": "warning",
            "item_count": 0,
            "stale_count": 0,
            "error_count": 0,
            "warning_count": 1,
            "latest_as_of": "",
            "latest_retrieved_at": "",
            "notes": [f"provider request skipped: {reason}"],
            "metrics": {"request_skipped": 1, "skip_reason": reason},
            "runtime": {
                "consecutive_failures": int(entry.get("consecutiveFailures", 0) or 0),
                "circuit_open": reason.startswith("circuit_open"),
                "circuit_open_until": str(entry.get("circuitOpenUntil") or ""),
                "min_interval_seconds": DEFAULT_MIN_INTERVAL_SECONDS,
            },
        }

    def save(self) -> None:
        dump_json(
            self.path,
            {
                "schemaVersion": RUNTIME_SCHEMA_VERSION,
                "updatedAt": timestamp_now(),
                "providers": self.providers,
            },
        )


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": RUNTIME_SCHEMA_VERSION, "providers": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": RUNTIME_SCHEMA_VERSION, "providers": {}}
    return payload if isinstance(payload, dict) else {"schemaVersion": RUNTIME_SCHEMA_VERSION, "providers": {}}


def _now() -> datetime:
    return datetime.fromisoformat(timestamp_now())


def _parse(value: Any) -> datetime | None:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
