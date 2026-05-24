from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ACTION_VERBS = {"add", "reduce", "hold", "scheduled_dca", "switch_in", "switch_out"}
EXECUTION_MODES = {"immediate", "scheduled", "conditional", "watch"}
TICKET_STATUSES = {"shadow_only", "proposed", "adjusted", "blocked", "degraded"}
GUARDRAIL_RESULTS = {"pass", "adjust", "block", "not_checked"}
WRITE_SCOPES = {"shadow_only", "learning_only", "review_only", "official"}


class ActionTicketValidationError(ValueError):
    pass


def _require(value: str, field_name: str) -> str:
    if not str(value or "").strip():
        raise ActionTicketValidationError(f"{field_name} is required")
    return str(value)


def _require_enum(value: str, allowed: set[str], field_name: str) -> str:
    value = _require(value, field_name)
    if value not in allowed:
        raise ActionTicketValidationError(f"{field_name}={value!r} is not one of {sorted(allowed)}")
    return value


def _as_float(value: float | int | str, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ActionTicketValidationError(f"{field_name} must be numeric") from exc


@dataclass(slots=True)
class EvidenceRef:
    ref_id: str
    source_kind: str
    source_path: str
    source_record_id: str = ""
    as_of_date: str = ""
    available_from: str = ""
    summary: str = ""

    def __post_init__(self) -> None:
        self.ref_id = _require(self.ref_id, "ref_id")
        self.source_kind = _require(self.source_kind, "source_kind")
        self.source_path = _require(self.source_path, "source_path")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRef":
        return cls(**{field_name: payload.get(field_name, "") for field_name in cls.__dataclass_fields__})


@dataclass(slots=True)
class GuardrailResult:
    rule_id: str
    result: str
    status_reason: str
    source_refs: list[EvidenceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rule_id = _require(self.rule_id, "rule_id")
        self.result = _require_enum(self.result, GUARDRAIL_RESULTS, "guardrail result")
        self.status_reason = _require(self.status_reason, "status_reason")
        self.source_refs = [item if isinstance(item, EvidenceRef) else EvidenceRef.from_dict(item) for item in self.source_refs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "result": self.result,
            "status_reason": self.status_reason,
            "source_refs": [item.to_dict() for item in self.source_refs],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GuardrailResult":
        return cls(
            rule_id=str(payload.get("rule_id", "") or ""),
            result=str(payload.get("result", "") or ""),
            status_reason=str(payload.get("status_reason", payload.get("reason", "")) or ""),
            source_refs=list(payload.get("source_refs", []) or []),
        )


@dataclass(slots=True)
class SoftPolicyAdjustment:
    policy_id: str
    effect_type: str
    effect_value: Any
    reason: str = ""

    def __post_init__(self) -> None:
        self.policy_id = _require(self.policy_id, "policy_id")
        self.effect_type = _require(self.effect_type, "effect_type")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SoftPolicyAdjustment":
        return cls(
            policy_id=str(payload.get("policy_id", "") or ""),
            effect_type=str(payload.get("effect_type", "") or ""),
            effect_value=payload.get("effect_value"),
            reason=str(payload.get("reason", "") or ""),
        )


@dataclass(slots=True)
class ActionTicket:
    ticket_id: str
    schema_version: str
    report_date: str
    generated_at: str
    fund_code: str
    fund_name: str
    action_verb: str
    execution_mode: str
    ticket_status: str
    non_executable: bool
    write_scope: str
    validated_amount: float
    confidence: float
    thesis: str
    hard_guardrail_results: list[GuardrailResult]
    source_artifacts: list[dict[str, Any]]
    legacy_mapping: dict[str, Any]
    role: str = ""
    category: str = ""
    portfolio_bucket: str = ""
    amount_currency: str = "CNY"
    requested_amount: float | None = None
    size_bucket: str = ""
    percent_of_position: float | None = None
    percent_of_portfolio: float | None = None
    supporting_evidence_refs: list[EvidenceRef] = field(default_factory=list)
    opposing_evidence_refs: list[EvidenceRef] = field(default_factory=list)
    soft_policy_adjustments: list[SoftPolicyAdjustment] = field(default_factory=list)
    skill_refs: list[str] = field(default_factory=list)
    skill_outputs: list[dict[str, Any]] = field(default_factory=list)
    opportunity_cost: dict[str, Any] = field(default_factory=dict)
    debate: dict[str, Any] = field(default_factory=dict)
    invalidation_conditions: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ticket_id = _require(self.ticket_id, "ticket_id")
        self.schema_version = _require(self.schema_version, "schema_version")
        self.report_date = _require(self.report_date, "report_date")
        self.generated_at = _require(self.generated_at, "generated_at")
        self.fund_code = _require(self.fund_code, "fund_code")
        self.fund_name = _require(self.fund_name, "fund_name")
        self.action_verb = _require_enum(self.action_verb, ACTION_VERBS, "action_verb")
        self.execution_mode = _require_enum(self.execution_mode, EXECUTION_MODES, "execution_mode")
        self.ticket_status = _require_enum(self.ticket_status, TICKET_STATUSES, "ticket_status")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.write_scope != "shadow_only":
            raise ActionTicketValidationError("Phase 1 action tickets must use write_scope=shadow_only")
        if self.non_executable is not True:
            raise ActionTicketValidationError("Phase 1 action tickets must be non_executable=true")
        self.validated_amount = _as_float(self.validated_amount, "validated_amount")
        self.confidence = _as_float(self.confidence, "confidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ActionTicketValidationError("confidence must be between 0 and 1")
        self.thesis = _require(self.thesis, "thesis")
        if not self.hard_guardrail_results:
            raise ActionTicketValidationError("hard_guardrail_results is required")
        if not self.source_artifacts:
            raise ActionTicketValidationError("source_artifacts is required")
        if not self.legacy_mapping:
            raise ActionTicketValidationError("legacy_mapping is required")
        self.hard_guardrail_results = [
            item if isinstance(item, GuardrailResult) else GuardrailResult.from_dict(item)
            for item in self.hard_guardrail_results
        ]
        self.supporting_evidence_refs = [
            item if isinstance(item, EvidenceRef) else EvidenceRef.from_dict(item)
            for item in self.supporting_evidence_refs
        ]
        self.opposing_evidence_refs = [
            item if isinstance(item, EvidenceRef) else EvidenceRef.from_dict(item)
            for item in self.opposing_evidence_refs
        ]
        self.soft_policy_adjustments = [
            item if isinstance(item, SoftPolicyAdjustment) else SoftPolicyAdjustment.from_dict(item)
            for item in self.soft_policy_adjustments
        ]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ticket_id": self.ticket_id,
            "schema_version": self.schema_version,
            "report_date": self.report_date,
            "generated_at": self.generated_at,
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "role": self.role,
            "category": self.category,
            "portfolio_bucket": self.portfolio_bucket,
            "action_verb": self.action_verb,
            "execution_mode": self.execution_mode,
            "ticket_status": self.ticket_status,
            "non_executable": self.non_executable,
            "write_scope": self.write_scope,
            "amount_currency": self.amount_currency,
            "requested_amount": self.requested_amount,
            "validated_amount": self.validated_amount,
            "size_bucket": self.size_bucket,
            "percent_of_position": self.percent_of_position,
            "percent_of_portfolio": self.percent_of_portfolio,
            "confidence": self.confidence,
            "thesis": self.thesis,
            "hard_guardrail_results": [item.to_dict() for item in self.hard_guardrail_results],
            "supporting_evidence_refs": [item.to_dict() for item in self.supporting_evidence_refs],
            "opposing_evidence_refs": [item.to_dict() for item in self.opposing_evidence_refs],
            "soft_policy_adjustments": [item.to_dict() for item in self.soft_policy_adjustments],
            "skill_refs": list(self.skill_refs),
            "skill_outputs": list(self.skill_outputs),
            "opportunity_cost": dict(self.opportunity_cost),
            "debate": dict(self.debate),
            "invalidation_conditions": list(self.invalidation_conditions),
            "missing_data": list(self.missing_data),
            "source_artifacts": list(self.source_artifacts),
            "legacy_mapping": dict(self.legacy_mapping),
        }
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionTicket":
        return cls(
            ticket_id=str(payload.get("ticket_id", "") or ""),
            schema_version=str(payload.get("schema_version", "") or ""),
            report_date=str(payload.get("report_date", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            fund_code=str(payload.get("fund_code", "") or ""),
            fund_name=str(payload.get("fund_name", "") or ""),
            role=str(payload.get("role", "") or ""),
            category=str(payload.get("category", "") or ""),
            portfolio_bucket=str(payload.get("portfolio_bucket", "") or ""),
            action_verb=str(payload.get("action_verb", "") or ""),
            execution_mode=str(payload.get("execution_mode", "") or ""),
            ticket_status=str(payload.get("ticket_status", "") or ""),
            non_executable=payload.get("non_executable"),
            write_scope=str(payload.get("write_scope", "") or ""),
            amount_currency=str(payload.get("amount_currency", "CNY") or "CNY"),
            requested_amount=payload.get("requested_amount"),
            validated_amount=payload.get("validated_amount", 0.0),
            size_bucket=str(payload.get("size_bucket", "") or ""),
            percent_of_position=payload.get("percent_of_position"),
            percent_of_portfolio=payload.get("percent_of_portfolio"),
            confidence=payload.get("confidence", 0.0),
            thesis=str(payload.get("thesis", "") or ""),
            hard_guardrail_results=list(payload.get("hard_guardrail_results", []) or []),
            supporting_evidence_refs=list(payload.get("supporting_evidence_refs", []) or []),
            opposing_evidence_refs=list(payload.get("opposing_evidence_refs", []) or []),
            soft_policy_adjustments=list(payload.get("soft_policy_adjustments", []) or []),
            skill_refs=list(payload.get("skill_refs", []) or []),
            skill_outputs=list(payload.get("skill_outputs", []) or []),
            opportunity_cost=dict(payload.get("opportunity_cost", {}) or {}),
            debate=dict(payload.get("debate", {}) or {}),
            invalidation_conditions=list(payload.get("invalidation_conditions", []) or []),
            missing_data=list(payload.get("missing_data", []) or []),
            source_artifacts=list(payload.get("source_artifacts", []) or []),
            legacy_mapping=dict(payload.get("legacy_mapping", {}) or {}),
        )


@dataclass(slots=True)
class ActionTicketArtifact:
    schema_version: str
    artifact_id: str
    artifact_kind: str
    report_date: str
    generated_at: str
    write_scope: str
    non_executable: bool
    source_artifacts: list[dict[str, Any]]
    summary: dict[str, Any]
    tickets: list[ActionTicket]

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        self.artifact_id = _require(self.artifact_id, "artifact_id")
        self.artifact_kind = _require(self.artifact_kind, "artifact_kind")
        self.report_date = _require(self.report_date, "report_date")
        self.generated_at = _require(self.generated_at, "generated_at")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.write_scope != "shadow_only":
            raise ActionTicketValidationError("Phase 1 artifact must use write_scope=shadow_only")
        if self.non_executable is not True:
            raise ActionTicketValidationError("Phase 1 artifact must be non_executable=true")
        if not self.source_artifacts:
            raise ActionTicketValidationError("source_artifacts is required")
        self.tickets = [item if isinstance(item, ActionTicket) else ActionTicket.from_dict(item) for item in self.tickets]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "report_date": self.report_date,
            "generated_at": self.generated_at,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "source_artifacts": list(self.source_artifacts),
            "summary": dict(self.summary),
            "tickets": [item.to_dict() for item in self.tickets],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionTicketArtifact":
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            artifact_id=str(payload.get("artifact_id", "") or ""),
            artifact_kind=str(payload.get("artifact_kind", "") or ""),
            report_date=str(payload.get("report_date", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            source_artifacts=list(payload.get("source_artifacts", []) or []),
            summary=dict(payload.get("summary", {}) or {}),
            tickets=list(payload.get("tickets", []) or []),
        )
