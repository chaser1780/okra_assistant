from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import load_json, timestamp_now


@dataclass
class ProviderConfig:
    section: str
    name: str
    timeout_seconds: int | None
    raw: dict[str, Any]
    primary: str = ""
    fallbacks: list[str] = field(default_factory=list)
    allow_stale_fallback: bool = True
    health_threshold: str = "warning"
    source_role: str = ""

    @property
    def provider_chain(self) -> list[str]:
        values = [self.primary or self.name, *self.fallbacks]
        return [value for value in values if value]


def _normalized_provider_block(settings: dict, section: str) -> dict[str, Any]:
    raw = dict(settings.get("providers", {}).get(section, {}) or {})
    if not raw:
        return {}
    if "primary" not in raw and raw.get("name"):
        raw["primary"] = raw.get("name")
    fallbacks = raw.get("fallbacks", [])
    if isinstance(fallbacks, str):
        fallbacks = [item.strip() for item in fallbacks.split(",") if item.strip()]
    raw["fallbacks"] = list(fallbacks or [])
    raw.setdefault("allow_stale_fallback", True)
    raw.setdefault("health_threshold", "warning")
    raw.setdefault("source_role", section)
    return raw


def resolve_provider_config(settings: dict, section: str, override_name: str | None = None) -> ProviderConfig:
    raw = _normalized_provider_block(settings, section)
    timeout_value = raw.get("timeout_seconds")
    chosen_name = override_name or raw.get("primary") or raw.get("name", section)
    fallbacks = [item for item in raw.get("fallbacks", []) if item and item != chosen_name]
    return ProviderConfig(
        section=section,
        name=chosen_name,
        timeout_seconds=int(timeout_value) if timeout_value is not None else None,
        raw=raw,
        primary=raw.get("primary", chosen_name),
        fallbacks=fallbacks,
        allow_stale_fallback=bool(raw.get("allow_stale_fallback", True)),
        health_threshold=str(raw.get("health_threshold", "warning") or "warning"),
        source_role=str(raw.get("source_role", section) or section),
    )


def resolve_provider_chain(settings: dict, section: str, override_name: str | None = None) -> list[str]:
    config = resolve_provider_config(settings, section, override_name)
    return config.provider_chain or [config.name]


def build_provider_payload(report_date: str, provider_name: str, items_key: str, items, **extra) -> dict:
    payload = {
        "report_date": report_date,
        "provider": provider_name,
        "generated_at": timestamp_now(),
        items_key: items,
    }
    payload.update(extra)
    return payload


def _confidence_label(status: str, fallback_kind: str = "") -> str:
    lowered = str(status or "").lower()
    if lowered == "fresh" and not fallback_kind:
        return "high"
    if lowered in {"stale", "fallback"} or fallback_kind:
        return "medium"
    return "low"


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


def build_provider_attempt(
    provider_name: str,
    status: str,
    *,
    detail: str = "",
    item_count: int | None = None,
    ok_count: int | None = None,
    filled_count: int | None = None,
    selected: bool = False,
    fallback_kind: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = {
        "provider": provider_name,
        "status": status,
        "selected": bool(selected),
        "attempted_at": timestamp_now(),
    }
    if detail:
        attempt["detail"] = detail
    if item_count is not None:
        attempt["item_count"] = int(item_count)
    if ok_count is not None:
        attempt["ok_count"] = int(ok_count)
    if filled_count is not None:
        attempt["filled_count"] = int(filled_count)
    if fallback_kind:
        attempt["fallback_kind"] = fallback_kind
    if extra:
        attempt.update(extra)
    return attempt


def attach_provider_metadata(
    payload: dict[str, Any],
    *,
    selected_provider: str,
    provider_chain: list[str],
    provider_attempts: list[dict[str, Any]],
    fallback_kind: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["selected_provider"] = selected_provider
    enriched["provider_chain"] = list(provider_chain)
    enriched["provider_attempts"] = list(provider_attempts)
    if fallback_kind:
        enriched["fallback_kind"] = fallback_kind
    freshness_status = "fresh"
    if enriched.get("error"):
        freshness_status = "missing"
    if fallback_kind or str(selected_provider).startswith("stale_snapshot") or enriched.get("fallback_reason"):
        freshness_status = "fallback" if fallback_kind or enriched.get("fallback_reason") else "stale"
    selected_attempt = next((item for item in provider_attempts if item.get("selected")), {})
    enriched["provider_metadata"] = {
        "schema_version": 1,
        "provider_name": selected_provider,
        "provider_chain": list(provider_chain),
        "provider_attempts": list(provider_attempts),
        "as_of_date": str(enriched.get("report_date", "") or ""),
        "fetched_at": str(enriched.get("generated_at", "") or timestamp_now()),
        "freshness_status": freshness_status,
        "confidence": _confidence_label(freshness_status, fallback_kind),
        "fallback_reason": str(enriched.get("fallback_reason", "") or selected_attempt.get("detail", "") if freshness_status in {"fallback", "stale", "missing"} else ""),
        "raw_snapshot_path": str(enriched.get("fallback_source_path", "") or ""),
        "normalized_schema_version": 1,
    }
    if extra:
        enriched.update(extra)
    return enriched


def build_provider_result(
    payload: dict[str, Any],
    *,
    provider_name: str | None = None,
    provider_chain: list[str] | None = None,
    provider_attempts: list[dict[str, Any]] | None = None,
    freshness_status: str = "fresh",
    confidence: str | None = None,
    fallback_reason: str = "",
    raw_snapshot_path: str = "",
) -> dict[str, Any]:
    selected_provider = provider_name or str(payload.get("provider", "") or "unknown")
    chain = list(provider_chain or [selected_provider])
    attempts = list(provider_attempts or [build_provider_attempt(selected_provider, "ok", selected=True)])
    enriched = dict(payload)
    enriched["selected_provider"] = selected_provider
    enriched["provider_chain"] = chain
    enriched["provider_attempts"] = attempts
    enriched["provider_metadata"] = {
        "schema_version": 1,
        "provider_name": selected_provider,
        "provider_chain": chain,
        "provider_attempts": attempts,
        "as_of_date": str(enriched.get("report_date", enriched.get("last_date", "")) or ""),
        "fetched_at": str(enriched.get("generated_at", "") or timestamp_now()),
        "freshness_status": freshness_status,
        "confidence": confidence or _confidence_label(freshness_status, fallback_reason),
        "fallback_reason": fallback_reason,
        "raw_snapshot_path": raw_snapshot_path,
        "normalized_schema_version": 1,
    }
    return enriched


def mark_fresh(payload: dict[str, Any], provider_name: str | None = None) -> dict[str, Any]:
    return build_provider_result(payload, provider_name=provider_name, freshness_status="fresh", confidence="high")


def mark_stale_fallback(payload: dict[str, Any], reason: str, provider_name: str | None = None, raw_snapshot_path: str = "") -> dict[str, Any]:
    return build_provider_result(
        payload,
        provider_name=provider_name,
        freshness_status="fallback",
        confidence="medium",
        fallback_reason=reason,
        raw_snapshot_path=raw_snapshot_path,
    )


def summarize_provider_attempts(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("provider_metadata", {}) or {}
    attempts = metadata.get("provider_attempts") or payload.get("provider_attempts") or []
    return {
        "provider_name": metadata.get("provider_name", payload.get("selected_provider", payload.get("provider", ""))),
        "freshness_status": metadata.get("freshness_status", "unknown"),
        "confidence": metadata.get("confidence", "low"),
        "attempt_count": len(attempts),
        "fallback_reason": metadata.get("fallback_reason", ""),
    }


def latest_dated_payload(target_path: Path, report_date: str) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[Path] = []
    if target_path.exists():
        candidates.append(target_path)
    for path in sorted(target_path.parent.glob("*.json"), reverse=True):
        stem = path.stem[:10]
        if len(stem) != 10 or stem.count("-") != 2:
            continue
        if stem > report_date:
            continue
        if path not in candidates:
            candidates.append(path)
    for path in candidates:
        try:
            payload = load_json(path)
        except Exception:
            continue
        if isinstance(payload, dict):
            return path, payload
    return None


def stale_fallback_from_recent_snapshot(
    target_path: Path,
    report_date: str,
    provider_name: str,
    items_key: str,
    reason: str,
    *,
    stale_field: str = "stale",
) -> dict[str, Any] | None:
    snapshot = latest_dated_payload(target_path, report_date)
    if snapshot is None:
        return None
    source_path, existing_payload = snapshot
    payload = stale_fallback_payload(existing_payload, provider_name, items_key, reason, stale_field=stale_field)
    payload["report_date"] = report_date
    payload["source_report_date"] = str(existing_payload.get("report_date", source_path.stem[:10]) or source_path.stem[:10])
    payload["fallback_source_date"] = source_path.stem[:10]
    payload["fallback_source_path"] = str(source_path)
    payload["fallback_reason"] = reason
    return payload


def ok_item_count(items: list[dict[str, Any]] | None = None, *, status_key: str = "status", ok_values: set[str] | None = None) -> int:
    ok_values = ok_values or {"ok"}
    count = 0
    for item in items or []:
        status = str(item.get(status_key, "ok") or "ok").lower()
        if status in ok_values:
            count += 1
    return count


def normalize_provider_item(
    item: dict[str, Any],
    *,
    provider_name: str,
    entity_id: str,
    entity_type: str,
    source_url: str = "",
    source_title: str = "",
    as_of: str = "",
    retrieved_at: str | None = None,
    freshness_status: str = "fresh",
    stale: bool = False,
    confidence: float = 0.7,
    source_role: str = "",
    source_tier: str = "",
    mapping_mode: str = "",
    evidence_type: str = "",
) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("provider", provider_name)
    normalized.setdefault("entity_id", entity_id)
    normalized.setdefault("entity_type", entity_type)
    normalized.setdefault("source_url", source_url or normalized.get("url", ""))
    normalized.setdefault("source_title", source_title or normalized.get("title", ""))
    normalized.setdefault("as_of", as_of or normalized.get("published_at", ""))
    normalized.setdefault("retrieved_at", retrieved_at or timestamp_now())
    normalized.setdefault("freshness_status", freshness_status)
    normalized.setdefault("stale", bool(stale))
    normalized.setdefault("confidence", float(confidence))
    if source_role:
        normalized.setdefault("source_role", source_role)
    if source_tier:
        normalized.setdefault("source_tier", source_tier)
    if mapping_mode:
        normalized.setdefault("mapping_mode", mapping_mode)
    if evidence_type:
        normalized.setdefault("evidence_type", evidence_type)
    return normalized


def build_source_health_item(
    *,
    source_key: str,
    source_role: str,
    provider: str,
    items: list[dict[str, Any]] | None = None,
    configured: bool = True,
    status: str = "ok",
    notes: list[str] | None = None,
    error_count: int = 0,
    warning_count: int = 0,
) -> dict[str, Any]:
    items = items or []
    stale_count = sum(1 for item in items if bool(item.get("stale", False)))
    latest_as_of = max((str(item.get("as_of", "") or item.get("published_at", "")) for item in items), default="")
    latest_retrieved_at = max((str(item.get("retrieved_at", "")) for item in items), default="")
    return {
        "source_key": source_key,
        "source_role": source_role,
        "provider": provider,
        "configured": bool(configured),
        "status": status,
        "item_count": len(items),
        "stale_count": stale_count,
        "error_count": int(error_count),
        "warning_count": int(warning_count),
        "latest_as_of": latest_as_of,
        "latest_retrieved_at": latest_retrieved_at,
        "notes": list(notes or []),
    }


def aggregate_source_health(items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items or []:
        key = (str(item.get("source_role", "") or "unknown"), str(item.get("provider", "") or "unknown"))
        grouped.setdefault(key, []).append(item)
    results = []
    for (source_role, provider), payloads in sorted(grouped.items()):
        source_key = f"{source_role}:{provider}"
        results.append(
            build_source_health_item(
                source_key=source_key,
                source_role=source_role,
                provider=provider,
                items=payloads,
                configured=True,
                status="warning" if any(item.get("stale") for item in payloads) else "ok",
            )
        )
    return results
