from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from typing import Any


ITEM_STATES = {"present", "missing", "stale", "conflicted", "pending", "blocked", "not_applicable"}
WRITE_SCOPES = {"shadow_only", "learning_only", "review_only", "official"}
SCHEMA_VERSION = "retrieval_pack.v1"


class LayeredContextValidationError(ValueError):
    pass


def _require(value: str, field_name: str) -> str:
    if not str(value or "").strip():
        raise LayeredContextValidationError(f"{field_name} is required")
    return str(value)


def _require_enum(value: str, allowed: set[str], field_name: str) -> str:
    value = _require(value, field_name)
    if value not in allowed:
        raise LayeredContextValidationError(f"{field_name}={value!r} is not one of {sorted(allowed)}")
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    text = _require(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LayeredContextValidationError(f"{field_name} must be an ISO timestamp") from exc
    return parsed


def _parse_cutoff(value: str) -> datetime:
    text = _require(value, "decision_cutoff")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.combine(datetime.strptime(text[:10], "%Y-%m-%d").date(), time(23, 59, 59))
    return parsed


def _same_time_basis(left: datetime, right: datetime) -> tuple[datetime, datetime]:
    if left.tzinfo and not right.tzinfo:
        right = right.replace(tzinfo=left.tzinfo)
    elif right.tzinfo and not left.tzinfo:
        left = left.replace(tzinfo=right.tzinfo)
    return left, right


def is_available_by_cutoff(available_from: str, decision_cutoff: str, *, field_name: str = "available_from") -> bool:
    available = _parse_timestamp(available_from, field_name)
    cutoff = _parse_cutoff(decision_cutoff)
    available, cutoff = _same_time_basis(available, cutoff)
    return available <= cutoff


def _coerce_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LayeredContextValidationError(f"{field_name} must be a dict")
    return dict(value)


def _coerce_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LayeredContextValidationError(f"{field_name} must be a list")
    return list(value)


@dataclass(slots=True)
class Visibility:
    include_execution: bool
    include_private_position_details: bool
    reason: str

    def __post_init__(self) -> None:
        if self.include_execution is not False:
            raise LayeredContextValidationError("Phase 2 retrieval packs must default to include_execution=false")
        self.reason = _require(self.reason, "visibility.reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Visibility":
        return cls(
            include_execution=payload.get("include_execution"),
            include_private_position_details=bool(payload.get("include_private_position_details")),
            reason=str(payload.get("reason", "") or ""),
        )


@dataclass(slots=True)
class LayeredContextItem:
    item_id: str
    layer: str
    source_kind: str
    source_path: str
    source_record_id: str
    as_of_date: str
    available_from: str
    status: str
    summary: str
    domain: str = ""
    fund_code: str = ""
    value: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    def __post_init__(self) -> None:
        self.item_id = _require(self.item_id, "item_id")
        self.layer = _require(self.layer, "layer")
        self.source_kind = _require(self.source_kind, "source_kind")
        self.source_path = _require(self.source_path, "source_path")
        self.source_record_id = _require(self.source_record_id, "source_record_id")
        self.as_of_date = _require(self.as_of_date, "as_of_date")
        self.available_from = _require(self.available_from, "available_from")
        self.status = _require_enum(self.status, ITEM_STATES, "status")
        self.summary = _require(self.summary, "summary")
        self.value = _coerce_dict(self.value, "value")
        self.metadata = _coerce_dict(self.metadata, "metadata")
        if self.score is not None:
            self.score = float(self.score)

    def assert_not_future(self, decision_cutoff: str) -> None:
        if not is_available_by_cutoff(self.available_from, decision_cutoff, field_name=f"{self.item_id}.available_from"):
            raise LayeredContextValidationError(
                f"{self.item_id} available_from={self.available_from} is later than decision_cutoff={decision_cutoff}"
            )

    def trace_complete(self) -> bool:
        return bool(self.source_path and self.source_record_id and self.as_of_date and self.available_from)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LayeredContextItem":
        return cls(
            item_id=str(payload.get("item_id", "") or payload.get("fact_id", "") or payload.get("signal_id", "") or payload.get("case_id", "") or ""),
            layer=str(payload.get("layer", "") or ""),
            source_kind=str(payload.get("source_kind", "") or ""),
            source_path=str(payload.get("source_path", "") or ""),
            source_record_id=str(payload.get("source_record_id", "") or ""),
            as_of_date=str(payload.get("as_of_date", "") or ""),
            available_from=str(payload.get("available_from", "") or ""),
            status=str(payload.get("status", "present") or "present"),
            summary=str(payload.get("summary", "") or ""),
            domain=str(payload.get("domain", "") or ""),
            fund_code=str(payload.get("fund_code", "") or ""),
            value=dict(payload.get("value", {}) or {}),
            metadata=dict(payload.get("metadata", {}) or {}),
            score=payload.get("score"),
        )


@dataclass(slots=True)
class MissingDataItem:
    field: str
    state: str
    reason: str
    impact: str
    blocks_debate: bool = False
    source_refs: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.field = _require(self.field, "missing_data.field")
        self.state = _require_enum(self.state, ITEM_STATES, "missing_data.state")
        self.reason = _require(self.reason, "missing_data.reason")
        self.impact = _require(self.impact, "missing_data.impact")
        self.source_refs = _coerce_list(self.source_refs, "source_refs")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MissingDataItem":
        return cls(
            field=str(payload.get("field", "") or ""),
            state=str(payload.get("state", "") or ""),
            reason=str(payload.get("reason", "") or ""),
            impact=str(payload.get("impact", "") or ""),
            blocks_debate=bool(payload.get("blocks_debate")),
            source_refs=list(payload.get("source_refs", []) or []),
        )


@dataclass(slots=True)
class RagTraceRef:
    trace_id: str
    path: str
    profile: str
    fallback_used: bool = False
    fallback_reason: str = ""

    def __post_init__(self) -> None:
        self.trace_id = _require(self.trace_id, "trace_id")
        self.profile = _require(self.profile, "profile")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RagTraceRef":
        return cls(
            trace_id=str(payload.get("trace_id", "") or ""),
            path=str(payload.get("path", "") or ""),
            profile=str(payload.get("profile", "") or ""),
            fallback_used=bool(payload.get("fallback_used")),
            fallback_reason=str(payload.get("fallback_reason", "") or ""),
        )


@dataclass(slots=True)
class RetrievalPack:
    schema_version: str
    pack_id: str
    report_date: str
    generated_at: str
    decision_cutoff: str
    write_scope: str
    non_executable: bool
    target: dict[str, Any]
    visibility: Visibility
    source_manifests: list[dict[str, Any]]
    raw_observation_refs: list[LayeredContextItem] = field(default_factory=list)
    canonical_facts: list[LayeredContextItem] = field(default_factory=list)
    derived_signals: list[LayeredContextItem] = field(default_factory=list)
    decision_history: list[LayeredContextItem] = field(default_factory=list)
    outcome_history: list[LayeredContextItem] = field(default_factory=list)
    similar_cases: list[LayeredContextItem] = field(default_factory=list)
    anti_patterns: list[LayeredContextItem] = field(default_factory=list)
    adaptive_policies: list[LayeredContextItem] = field(default_factory=list)
    strategy_skill_candidates: list[LayeredContextItem] = field(default_factory=list)
    long_text_evidence: list[LayeredContextItem] = field(default_factory=list)
    missing_data: list[MissingDataItem] = field(default_factory=list)
    rag_trace_refs: list[RagTraceRef] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        self.pack_id = _require(self.pack_id, "pack_id")
        self.report_date = _require(self.report_date, "report_date")
        self.generated_at = _require(self.generated_at, "generated_at")
        self.decision_cutoff = _require(self.decision_cutoff, "decision_cutoff")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.write_scope != "shadow_only":
            raise LayeredContextValidationError("Phase 2 retrieval packs must use write_scope=shadow_only")
        if self.non_executable is not True:
            raise LayeredContextValidationError("Phase 2 retrieval packs must be non_executable=true")
        self.target = _coerce_dict(self.target, "target")
        if not self.target.get("fund_code"):
            raise LayeredContextValidationError("target.fund_code is required")
        self.visibility = self.visibility if isinstance(self.visibility, Visibility) else Visibility.from_dict(self.visibility)
        self.source_manifests = _coerce_list(self.source_manifests, "source_manifests")
        if not self.source_manifests:
            raise LayeredContextValidationError("source_manifests is required")
        for field_name in _ITEM_SECTION_NAMES:
            setattr(
                self,
                field_name,
                [item if isinstance(item, LayeredContextItem) else LayeredContextItem.from_dict(item) for item in getattr(self, field_name)],
            )
        self.missing_data = [item if isinstance(item, MissingDataItem) else MissingDataItem.from_dict(item) for item in self.missing_data]
        self.rag_trace_refs = [item if isinstance(item, RagTraceRef) else RagTraceRef.from_dict(item) for item in self.rag_trace_refs]
        self.audit = _coerce_dict(self.audit, "audit")
        self.assert_no_future()

    def iter_items(self) -> list[LayeredContextItem]:
        items: list[LayeredContextItem] = []
        for field_name in _ITEM_SECTION_NAMES:
            items.extend(getattr(self, field_name))
        return items

    def assert_no_future(self) -> None:
        for item in self.iter_items():
            item.assert_not_future(self.decision_cutoff)

    def trace_completeness_rate(self) -> float:
        items = self.iter_items()
        if not items:
            return 1.0
        complete = sum(1 for item in items if item.trace_complete())
        return round(complete / len(items), 4)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "pack_id": self.pack_id,
            "report_date": self.report_date,
            "generated_at": self.generated_at,
            "decision_cutoff": self.decision_cutoff,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "target": dict(self.target),
            "visibility": self.visibility.to_dict(),
            "source_manifests": list(self.source_manifests),
            "missing_data": [item.to_dict() for item in self.missing_data],
            "rag_trace_refs": [item.to_dict() for item in self.rag_trace_refs],
            "audit": dict(self.audit),
        }
        for field_name in _ITEM_SECTION_NAMES:
            payload[field_name] = [item.to_dict() for item in getattr(self, field_name)]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalPack":
        kwargs = {field_name: list(payload.get(field_name, []) or []) for field_name in _ITEM_SECTION_NAMES}
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            pack_id=str(payload.get("pack_id", "") or ""),
            report_date=str(payload.get("report_date", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            decision_cutoff=str(payload.get("decision_cutoff", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            target=dict(payload.get("target", {}) or {}),
            visibility=dict(payload.get("visibility", {}) or {}),
            source_manifests=list(payload.get("source_manifests", []) or []),
            missing_data=list(payload.get("missing_data", []) or []),
            rag_trace_refs=list(payload.get("rag_trace_refs", []) or []),
            audit=dict(payload.get("audit", {}) or {}),
            **kwargs,
        )


@dataclass(slots=True)
class RetrievalPackArtifact:
    schema_version: str
    artifact_id: str
    artifact_kind: str
    report_date: str
    generated_at: str
    decision_cutoff: str
    write_scope: str
    non_executable: bool
    source_artifacts: list[dict[str, Any]]
    summary: dict[str, Any]
    packs: list[RetrievalPack]

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        self.artifact_id = _require(self.artifact_id, "artifact_id")
        self.artifact_kind = _require(self.artifact_kind, "artifact_kind")
        self.report_date = _require(self.report_date, "report_date")
        self.generated_at = _require(self.generated_at, "generated_at")
        self.decision_cutoff = _require(self.decision_cutoff, "decision_cutoff")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.write_scope != "shadow_only":
            raise LayeredContextValidationError("Phase 2 artifact must use write_scope=shadow_only")
        if self.non_executable is not True:
            raise LayeredContextValidationError("Phase 2 artifact must be non_executable=true")
        self.source_artifacts = _coerce_list(self.source_artifacts, "source_artifacts")
        if not self.source_artifacts:
            raise LayeredContextValidationError("source_artifacts is required")
        self.summary = _coerce_dict(self.summary, "summary")
        self.packs = [item if isinstance(item, RetrievalPack) else RetrievalPack.from_dict(item) for item in self.packs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "report_date": self.report_date,
            "generated_at": self.generated_at,
            "decision_cutoff": self.decision_cutoff,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "source_artifacts": list(self.source_artifacts),
            "summary": dict(self.summary),
            "packs": [item.to_dict() for item in self.packs],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalPackArtifact":
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            artifact_id=str(payload.get("artifact_id", "") or ""),
            artifact_kind=str(payload.get("artifact_kind", "") or ""),
            report_date=str(payload.get("report_date", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            decision_cutoff=str(payload.get("decision_cutoff", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            source_artifacts=list(payload.get("source_artifacts", []) or []),
            summary=dict(payload.get("summary", {}) or {}),
            packs=list(payload.get("packs", []) or []),
        )


_ITEM_SECTION_NAMES = (
    "raw_observation_refs",
    "canonical_facts",
    "derived_signals",
    "decision_history",
    "outcome_history",
    "similar_cases",
    "anti_patterns",
    "adaptive_policies",
    "strategy_skill_candidates",
    "long_text_evidence",
)
