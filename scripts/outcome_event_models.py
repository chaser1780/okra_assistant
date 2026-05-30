from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


SCHEMA_VERSION = "outcome_event.v1"
SCORING_STATUSES = {"pending", "blocked", "scored", "not_applicable"}
OUTCOME_LABELS = {"helped", "hurt", "neutral", "avoided_loss", "missed_opportunity", "not_scored"}
WRITE_SCOPES = {"learning_only"}


class OutcomeEventValidationError(ValueError):
    pass


def _require(value: str, field_name: str) -> str:
    if not str(value or "").strip():
        raise OutcomeEventValidationError(f"{field_name} is required")
    return str(value)


def _require_enum(value: str, allowed: set[str], field_name: str) -> str:
    value = _require(value, field_name)
    if value not in allowed:
        raise OutcomeEventValidationError(f"{field_name}={value!r} is not one of {sorted(allowed)}")
    return value


def _date(value: str, field_name: str) -> str:
    value = _require(value, field_name)
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise OutcomeEventValidationError(f"{field_name} must be YYYY-MM-DD") from exc
    return value


def _float_or_none(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise OutcomeEventValidationError(f"{field_name} must be numeric") from exc


def _dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OutcomeEventValidationError(f"{field_name} must be a dict")
    return dict(value)


def _list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OutcomeEventValidationError(f"{field_name} must be a list")
    return list(value)


@dataclass(slots=True)
class OutcomeEvent:
    outcome_id: str
    ticket_id: str
    base_date: str
    evaluation_date: str
    horizon: str
    fund_code: str
    fund_name: str
    action_verb: str
    execution_mode: str
    amount: float
    amount_currency: str
    scoring_status: str
    blocked_reason: str
    official_nav_start: dict[str, Any]
    official_nav_end: dict[str, Any]
    benchmark: dict[str, Any]
    actual_return_pct: float | None
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    no_action_baseline: dict[str, Any]
    outcome_label: str
    diagnostic_label: str
    confidence: float
    cashflow_checks: dict[str, Any]
    decision_context: dict[str, Any] = field(default_factory=dict)
    learning_implications: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.outcome_id = _require(self.outcome_id, "outcome_id")
        self.ticket_id = _require(self.ticket_id, "ticket_id")
        self.base_date = _date(self.base_date, "base_date")
        self.evaluation_date = _date(self.evaluation_date, "evaluation_date")
        self.horizon = _require(self.horizon, "horizon")
        self.fund_code = _require(self.fund_code, "fund_code")
        self.fund_name = _require(self.fund_name, "fund_name")
        self.action_verb = _require(self.action_verb, "action_verb")
        self.execution_mode = _require(self.execution_mode, "execution_mode")
        self.amount = float(_float_or_none(self.amount, "amount") or 0.0)
        self.amount_currency = _require(self.amount_currency, "amount_currency")
        self.scoring_status = _require_enum(self.scoring_status, SCORING_STATUSES, "scoring_status")
        self.blocked_reason = str(self.blocked_reason or "")
        self.official_nav_start = _dict(self.official_nav_start, "official_nav_start")
        self.official_nav_end = _dict(self.official_nav_end, "official_nav_end")
        self.benchmark = _dict(self.benchmark, "benchmark")
        self.actual_return_pct = _float_or_none(self.actual_return_pct, "actual_return_pct")
        self.benchmark_return_pct = _float_or_none(self.benchmark_return_pct, "benchmark_return_pct")
        self.excess_return_pct = _float_or_none(self.excess_return_pct, "excess_return_pct")
        self.no_action_baseline = _dict(self.no_action_baseline, "no_action_baseline")
        self.outcome_label = _require_enum(self.outcome_label, OUTCOME_LABELS, "outcome_label")
        self.diagnostic_label = _require(self.diagnostic_label, "diagnostic_label")
        self.confidence = float(_float_or_none(self.confidence, "confidence") or 0.0)
        if not 0.0 <= self.confidence <= 1.0:
            raise OutcomeEventValidationError("confidence must be between 0 and 1")
        self.cashflow_checks = _dict(self.cashflow_checks, "cashflow_checks")
        self.decision_context = _dict(self.decision_context, "decision_context")
        self.learning_implications = [dict(item) for item in _list(self.learning_implications, "learning_implications")]
        self.source_refs = [dict(item) for item in _list(self.source_refs, "source_refs")]
        self.audit = _dict(self.audit, "audit")
        if self.scoring_status == "scored":
            if not self.official_nav_start or not self.official_nav_end:
                raise OutcomeEventValidationError("scored outcomes require official_nav_start and official_nav_end")
            if self.actual_return_pct is None:
                raise OutcomeEventValidationError("scored outcomes require actual_return_pct")
        if self.scoring_status in {"pending", "blocked"} and not self.blocked_reason:
            raise OutcomeEventValidationError(f"{self.scoring_status} outcomes require blocked_reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeEvent":
        return cls(**{field_name: payload.get(field_name) for field_name in cls.__dataclass_fields__})


@dataclass(slots=True)
class OutcomeEventArtifact:
    schema_version: str
    artifact_id: str
    base_date: str
    evaluation_date: str
    horizon: str
    generated_at: str
    write_scope: str
    non_executable: bool
    source_artifacts: list[dict[str, Any]]
    events: list[OutcomeEvent]
    summary: dict[str, Any]
    target_date: str = ""
    evaluation_date_used: str = ""
    date_match_type: str = ""

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != SCHEMA_VERSION:
            raise OutcomeEventValidationError(f"schema_version must be {SCHEMA_VERSION}")
        self.artifact_id = _require(self.artifact_id, "artifact_id")
        self.base_date = _date(self.base_date, "base_date")
        self.evaluation_date = _date(self.evaluation_date, "evaluation_date")
        self.target_date = _date(self.target_date or self.evaluation_date, "target_date")
        self.evaluation_date_used = _date(self.evaluation_date_used or self.evaluation_date, "evaluation_date_used")
        self.date_match_type = str(self.date_match_type or "")
        self.horizon = _require(self.horizon, "horizon")
        self.generated_at = _require(self.generated_at, "generated_at")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.non_executable is not True:
            raise OutcomeEventValidationError("outcome events must be non_executable=true")
        self.source_artifacts = [dict(item) for item in _list(self.source_artifacts, "source_artifacts")]
        self.events = [item if isinstance(item, OutcomeEvent) else OutcomeEvent.from_dict(item) for item in _list(self.events, "events")]
        self.summary = _dict(self.summary, "summary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "base_date": self.base_date,
            "target_date": self.target_date,
            "evaluation_date": self.evaluation_date,
            "evaluation_date_used": self.evaluation_date_used,
            "date_match_type": self.date_match_type,
            "horizon": self.horizon,
            "generated_at": self.generated_at,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "source_artifacts": list(self.source_artifacts),
            "events": [item.to_dict() for item in self.events],
            "summary": dict(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeEventArtifact":
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            artifact_id=str(payload.get("artifact_id", "") or ""),
            base_date=str(payload.get("base_date", "") or ""),
            target_date=str(payload.get("target_date", "") or ""),
            evaluation_date=str(payload.get("evaluation_date", "") or ""),
            evaluation_date_used=str(payload.get("evaluation_date_used", "") or ""),
            date_match_type=str(payload.get("date_match_type", "") or ""),
            horizon=str(payload.get("horizon", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            source_artifacts=list(payload.get("source_artifacts", []) or []),
            events=list(payload.get("events", []) or []),
            summary=dict(payload.get("summary", {}) or {}),
        )
