from __future__ import annotations

from dataclasses import dataclass

from common import timestamp_now


@dataclass
class ProviderConfig:
    section: str
    name: str
    timeout_seconds: int | None
    raw: dict


def resolve_provider_config(settings: dict, section: str, override_name: str | None = None) -> ProviderConfig:
    raw = settings.get("providers", {}).get(section, {})
    timeout_value = raw.get("timeout_seconds")
    return ProviderConfig(
        section=section,
        name=override_name or raw.get("name", section),
        timeout_seconds=int(timeout_value) if timeout_value is not None else None,
        raw=raw,
    )


def build_provider_payload(report_date: str, provider_name: str, items_key: str, items, **extra) -> dict:
    payload = {
        "report_date": report_date,
        "provider": provider_name,
        "generated_at": timestamp_now(),
        items_key: items,
    }
    payload.update(extra)
    return payload


def stale_fallback_payload(existing_payload: dict, provider_name: str, items_key: str, reason: str, stale_field: str = "stale") -> dict:
    payload = dict(existing_payload)
    payload["provider"] = provider_name
    payload["generated_at"] = timestamp_now()
    updated_items = []
    for item in payload.get(items_key, []):
        updated = dict(item)
        updated[stale_field] = True
        updated["fallback_reason"] = reason
        updated_items.append(updated)
    payload[items_key] = updated_items
    return payload
