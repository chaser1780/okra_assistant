from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


EVENT_SCHEMA_VERSION = "adaptive_policy_event.v1"
POLICY_SCHEMA_VERSION = "adaptive_policy.v1"
STORE_SCHEMA_VERSION = "adaptive_policy_store.v1"

WRITE_SCOPES = {"learning_only"}
POLICY_STATUSES = {"draft", "candidate", "active", "weakened", "revised", "archived"}
POLICY_EVENT_TYPES = {"support", "contradict", "weaken", "archive", "revise", "user_approve"}
ALLOWED_POLICY_EFFECTS = {"confidence_delta", "size_multiplier", "wait_trigger", "note"}
FORBIDDEN_POLICY_EFFECTS = {"block", "force_trade", "change_hard_constraint"}


class AdaptivePolicyValidationError(ValueError):
    pass


def _require(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AdaptivePolicyValidationError(f"{field_name} is required")
    return text


def _require_enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = _require(value, field_name)
    if text not in allowed:
        raise AdaptivePolicyValidationError(f"{field_name}={text!r} is not one of {sorted(allowed)}")
    return text


def _dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AdaptivePolicyValidationError(f"{field_name} must be a dict")
    return dict(value)


def _list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdaptivePolicyValidationError(f"{field_name} must be a list")
    return list(value)


def _int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AdaptivePolicyValidationError(f"{field_name} must be an integer") from exc
    if result < 0:
        raise AdaptivePolicyValidationError(f"{field_name} must be non-negative")
    return result


def _float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AdaptivePolicyValidationError(f"{field_name} must be numeric") from exc


def _timestamp(value: Any, field_name: str) -> str:
    text = _require(value, field_name)
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise AdaptivePolicyValidationError(f"{field_name} must be an ISO timestamp") from exc
    return text


def _date(value: Any, field_name: str) -> str:
    text = _require(value, field_name)
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise AdaptivePolicyValidationError(f"{field_name} must be YYYY-MM-DD") from exc
    return text


def _effect_type(value: Any, field_name: str = "effect_type") -> str:
    text = _require(value, field_name)
    if text in FORBIDDEN_POLICY_EFFECTS:
        raise AdaptivePolicyValidationError(f"{field_name}={text!r} is forbidden for adaptive soft policies")
    if text not in ALLOWED_POLICY_EFFECTS:
        raise AdaptivePolicyValidationError(f"{field_name}={text!r} is not one of {sorted(ALLOWED_POLICY_EFFECTS)}")
    return text


def _validate_effect_value(effect_type: str, effect_value: Any) -> Any:
    if effect_type == "confidence_delta":
        value = _float(effect_value, "effect_value")
        if not -0.2 <= value <= 0.2:
            raise AdaptivePolicyValidationError("confidence_delta effect_value must be between -0.2 and 0.2")
        return value
    if effect_type == "size_multiplier":
        value = _float(effect_value, "effect_value")
        if not 0.0 < value <= 1.5:
            raise AdaptivePolicyValidationError("size_multiplier effect_value must be > 0 and <= 1.5")
        return value
    if effect_type in {"wait_trigger", "note"}:
        return _require(effect_value, "effect_value")
    raise AdaptivePolicyValidationError(f"unsupported effect_type: {effect_type}")


@dataclass(slots=True)
class AdaptivePolicyEvent:
    event_id: str
    policy_id: str
    schema_version: str
    event_type: str
    event_time: str
    scope: str
    statement: str
    when_to_apply: dict[str, Any]
    effect_type: str
    effect_value: Any
    source_outcome_id: str = ""
    source_ticket_id: str = ""
    source_artifact: str = ""
    outcome_label: str = ""
    diagnostic_label: str = ""
    delta: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    write_scope: str = "learning_only"
    non_executable: bool = True
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.event_id = _require(self.event_id, "event_id")
        self.policy_id = _require(self.policy_id, "policy_id")
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise AdaptivePolicyValidationError(f"schema_version must be {EVENT_SCHEMA_VERSION}")
        self.event_type = _require_enum(self.event_type, POLICY_EVENT_TYPES, "event_type")
        self.event_time = _timestamp(self.event_time, "event_time")
        self.scope = _require(self.scope, "scope")
        self.statement = _require(self.statement, "statement")
        self.when_to_apply = _dict(self.when_to_apply, "when_to_apply")
        self.effect_type = _effect_type(self.effect_type)
        self.effect_value = _validate_effect_value(self.effect_type, self.effect_value)
        self.source_outcome_id = str(self.source_outcome_id or "")
        self.source_ticket_id = str(self.source_ticket_id or "")
        self.source_artifact = str(self.source_artifact or "")
        self.outcome_label = str(self.outcome_label or "")
        self.diagnostic_label = str(self.diagnostic_label or "")
        self.delta = _dict(self.delta, "delta")
        self.notes = str(self.notes or "")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.non_executable is not True:
            raise AdaptivePolicyValidationError("adaptive policy events must be non_executable=true")
        self.audit = _dict(self.audit, "audit")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AdaptivePolicyEvent":
        return cls(
            event_id=str(payload.get("event_id", "") or ""),
            policy_id=str(payload.get("policy_id", "") or ""),
            schema_version=str(payload.get("schema_version", "") or ""),
            event_type=str(payload.get("event_type", "") or ""),
            event_time=str(payload.get("event_time", "") or ""),
            scope=str(payload.get("scope", "") or ""),
            statement=str(payload.get("statement", "") or ""),
            when_to_apply=dict(payload.get("when_to_apply", {}) or {}),
            effect_type=str(payload.get("effect_type", "") or ""),
            effect_value=payload.get("effect_value"),
            source_outcome_id=str(payload.get("source_outcome_id", "") or ""),
            source_ticket_id=str(payload.get("source_ticket_id", "") or ""),
            source_artifact=str(payload.get("source_artifact", "") or ""),
            outcome_label=str(payload.get("outcome_label", "") or ""),
            diagnostic_label=str(payload.get("diagnostic_label", "") or ""),
            delta=dict(payload.get("delta", {}) or {}),
            notes=str(payload.get("notes", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            audit=dict(payload.get("audit", {}) or {}),
        )


@dataclass(slots=True)
class AdaptivePolicy:
    policy_id: str
    schema_version: str
    scope: str
    status: str
    statement: str
    when_to_apply: dict[str, Any]
    effect_type: str
    effect_value: Any
    effect_bounds: dict[str, Any]
    allowed_effects: list[str]
    forbidden_effects: list[str]
    support_count: int
    contradiction_count: int
    confidence: float
    source_outcome_ids: list[str] = field(default_factory=list)
    source_ticket_ids: list[str] = field(default_factory=list)
    last_supported_at: str = ""
    last_contradicted_at: str = ""
    last_reviewed_at: str = ""
    valid_from: str = ""
    valid_until: str = ""
    version: int = 1
    promotion_rule: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.policy_id = _require(self.policy_id, "policy_id")
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise AdaptivePolicyValidationError(f"schema_version must be {POLICY_SCHEMA_VERSION}")
        self.scope = _require(self.scope, "scope")
        self.status = _require_enum(self.status, POLICY_STATUSES, "status")
        self.statement = _require(self.statement, "statement")
        self.when_to_apply = _dict(self.when_to_apply, "when_to_apply")
        self.effect_type = _effect_type(self.effect_type)
        self.effect_value = _validate_effect_value(self.effect_type, self.effect_value)
        self.effect_bounds = _dict(self.effect_bounds, "effect_bounds")
        self.allowed_effects = [_effect_type(item, "allowed_effects[]") for item in _list(self.allowed_effects, "allowed_effects")]
        self.forbidden_effects = [str(item) for item in _list(self.forbidden_effects, "forbidden_effects")]
        forbidden = set(self.forbidden_effects)
        if not FORBIDDEN_POLICY_EFFECTS.issubset(forbidden):
            raise AdaptivePolicyValidationError("forbidden_effects must include block, force_trade, and change_hard_constraint")
        self.support_count = _int(self.support_count, "support_count")
        self.contradiction_count = _int(self.contradiction_count, "contradiction_count")
        self.confidence = _float(self.confidence, "confidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise AdaptivePolicyValidationError("confidence must be between 0 and 1")
        self.source_outcome_ids = [str(item) for item in _list(self.source_outcome_ids, "source_outcome_ids")]
        self.source_ticket_ids = [str(item) for item in _list(self.source_ticket_ids, "source_ticket_ids")]
        self.last_supported_at = str(self.last_supported_at or "")
        self.last_contradicted_at = str(self.last_contradicted_at or "")
        self.last_reviewed_at = _timestamp(self.last_reviewed_at, "last_reviewed_at")
        self.valid_from = _date(self.valid_from, "valid_from")
        self.valid_until = str(self.valid_until or "")
        if self.valid_until:
            self.valid_until = _date(self.valid_until, "valid_until")
        self.version = max(1, _int(self.version, "version"))
        self.promotion_rule = _dict(self.promotion_rule, "promotion_rule")
        self.audit = _dict(self.audit, "audit")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AdaptivePolicy":
        return cls(**{field_name: payload.get(field_name) for field_name in cls.__dataclass_fields__})


@dataclass(slots=True)
class AdaptivePolicyStore:
    schema_version: str
    generated_at: str
    materialized_from: str
    write_scope: str
    non_executable: bool
    hard_block_allowed: bool
    policies: list[AdaptivePolicy]
    recent_events: list[dict[str, Any]]
    caps: dict[str, Any]
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != STORE_SCHEMA_VERSION:
            raise AdaptivePolicyValidationError(f"schema_version must be {STORE_SCHEMA_VERSION}")
        self.generated_at = _timestamp(self.generated_at, "generated_at")
        self.materialized_from = _require(self.materialized_from, "materialized_from")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.non_executable is not True:
            raise AdaptivePolicyValidationError("adaptive policy store must be non_executable=true")
        if self.hard_block_allowed is not False:
            raise AdaptivePolicyValidationError("adaptive soft policies must have hard_block_allowed=false")
        self.policies = [item if isinstance(item, AdaptivePolicy) else AdaptivePolicy.from_dict(item) for item in _list(self.policies, "policies")]
        self.recent_events = [dict(item) for item in _list(self.recent_events, "recent_events")]
        self.caps = _dict(self.caps, "caps")
        self.summary = _dict(self.summary, "summary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "materialized_from": self.materialized_from,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "hard_block_allowed": self.hard_block_allowed,
            "policies": [item.to_dict() for item in self.policies],
            "recent_events": list(self.recent_events),
            "caps": dict(self.caps),
            "summary": dict(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AdaptivePolicyStore":
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            materialized_from=str(payload.get("materialized_from", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            hard_block_allowed=payload.get("hard_block_allowed"),
            policies=list(payload.get("policies", []) or []),
            recent_events=list(payload.get("recent_events", []) or []),
            caps=dict(payload.get("caps", {}) or {}),
            summary=dict(payload.get("summary", {}) or {}),
        )
