from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


SKILL_SCHEMA_VERSION = "strategy_skill.v1"
SKILL_EVENT_SCHEMA_VERSION = "strategy_skill_event.v1"
REGISTRY_SCHEMA_VERSION = "strategy_skill_registry.v1"

WRITE_SCOPES = {"learning_only"}
SKILL_STATUSES = {"draft", "candidate", "active", "strengthened", "revised", "archived"}
SKILL_EVENT_TYPES = {
    "draft_created",
    "candidate_created",
    "active_promoted",
    "strengthened",
    "revised",
    "archived",
    "user_approved",
}
REQUIRED_SECTIONS = (
    "Purpose",
    "When To Apply",
    "Required Inputs",
    "Procedure",
    "Position Sizing Notes",
    "Invalidation Conditions",
    "Anti-Patterns",
    "Evidence Requirements",
    "Known Failure Modes",
    "Output Contract",
)
ALLOWED_SKILL_OUTPUTS = {
    "sizing_note",
    "confidence_delta",
    "wait_trigger",
    "invalidation_condition",
    "evidence_requirement_note",
}
FORBIDDEN_SKILL_OUTPUTS = {
    "hard_block",
    "force_trade",
    "direct_portfolio_mutation",
    "execution_command",
}


class StrategySkillValidationError(ValueError):
    pass


def _require(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise StrategySkillValidationError(f"{field_name} is required")
    return text


def _require_enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = _require(value, field_name)
    if text not in allowed:
        raise StrategySkillValidationError(f"{field_name}={text!r} is not one of {sorted(allowed)}")
    return text


def _timestamp(value: Any, field_name: str) -> str:
    text = _require(value, field_name)
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise StrategySkillValidationError(f"{field_name} must be an ISO timestamp") from exc
    return text


def _int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise StrategySkillValidationError(f"{field_name} must be an integer") from exc
    if result < 0:
        raise StrategySkillValidationError(f"{field_name} must be non-negative")
    return result


def _float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StrategySkillValidationError(f"{field_name} must be numeric") from exc


def _dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StrategySkillValidationError(f"{field_name} must be a dict")
    return dict(value)


def _list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise StrategySkillValidationError(f"{field_name} must be a list")
    return list(value)


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text.strip('"').strip("'")


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        raise StrategySkillValidationError("skill Markdown must start with frontmatter")
    try:
        end_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise StrategySkillValidationError("skill Markdown frontmatter is not closed") from exc

    metadata: dict[str, Any] = {}
    current_key = ""
    for raw_line in lines[1:end_index]:
        if not raw_line.strip():
            continue
        if raw_line.startswith("  - "):
            if not current_key:
                raise StrategySkillValidationError("frontmatter list item has no key")
            if metadata.get(current_key) is None:
                metadata[current_key] = []
            if not isinstance(metadata[current_key], list):
                raise StrategySkillValidationError(f"frontmatter key {current_key} mixes list and non-list values")
            metadata[current_key].append(parse_scalar(raw_line[4:]))
            continue
        if raw_line.startswith("  ") and ":" in raw_line:
            if not current_key:
                raise StrategySkillValidationError("frontmatter nested value has no key")
            if metadata.get(current_key) is None:
                metadata[current_key] = {}
            if not isinstance(metadata[current_key], dict):
                raise StrategySkillValidationError(f"frontmatter key {current_key} mixes dict and non-dict values")
            nested_key, nested_value = raw_line.strip().split(":", 1)
            metadata[current_key][nested_key.strip()] = parse_scalar(nested_value)
            continue
        if ":" not in raw_line:
            raise StrategySkillValidationError(f"invalid frontmatter line: {raw_line}")
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        stripped_value = value.strip()
        metadata[current_key] = parse_scalar(stripped_value) if stripped_value else None
    return metadata, "\n".join(lines[end_index + 1 :]).strip()


def extract_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def render_frontmatter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for nested_key, nested_value in value.items():
                lines.append(f"  {nested_key}: {str(nested_value).lower() if isinstance(nested_value, bool) else nested_value}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


@dataclass(slots=True)
class StrategySkillDocument:
    schema_version: str
    skill_id: str
    name: str
    status: str
    version: int
    scope: str
    created_at: str
    updated_at: str
    source_policy_ids: list[str]
    source_outcome_ids: list[str]
    promotion: dict[str, Any]
    hard_constraints_editable: bool
    default_write_scope: str
    non_executable: bool
    auto_activation_allowed: bool
    sections: dict[str, str]

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != SKILL_SCHEMA_VERSION:
            raise StrategySkillValidationError(f"schema_version must be {SKILL_SCHEMA_VERSION}")
        self.skill_id = _require(self.skill_id, "skill_id")
        self.name = _require(self.name, "name")
        self.status = _require_enum(self.status, SKILL_STATUSES, "status")
        self.version = max(1, _int(self.version, "version"))
        self.scope = _require(self.scope, "scope")
        self.created_at = _timestamp(self.created_at, "created_at")
        self.updated_at = _timestamp(self.updated_at, "updated_at")
        self.source_policy_ids = [str(item) for item in _list(self.source_policy_ids, "source_policy_ids")]
        self.source_outcome_ids = [str(item) for item in _list(self.source_outcome_ids, "source_outcome_ids")]
        self.promotion = _dict(self.promotion, "promotion")
        if self.hard_constraints_editable is not False:
            raise StrategySkillValidationError("strategy skills cannot edit hard constraints")
        self.default_write_scope = _require_enum(self.default_write_scope, WRITE_SCOPES, "default_write_scope")
        if self.non_executable is not True:
            raise StrategySkillValidationError("strategy skills must be non_executable=true")
        if self.auto_activation_allowed is not False:
            raise StrategySkillValidationError("auto_activation_allowed must be false in Phase 6")
        self.sections = _dict(self.sections, "sections")
        missing = [section for section in REQUIRED_SECTIONS if not str(self.sections.get(section, "") or "").strip()]
        if missing:
            raise StrategySkillValidationError(f"skill Markdown missing required sections: {', '.join(missing)}")
        if not self.source_policy_ids:
            raise StrategySkillValidationError("source_policy_ids is required")
        if not self.source_outcome_ids:
            raise StrategySkillValidationError("source_outcome_ids is required")

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skill_id": self.skill_id,
            "name": self.name,
            "status": self.status,
            "version": self.version,
            "scope": self.scope,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_policy_ids": list(self.source_policy_ids),
            "source_outcome_ids": list(self.source_outcome_ids),
            "promotion": dict(self.promotion),
            "hard_constraints_editable": self.hard_constraints_editable,
            "default_write_scope": self.default_write_scope,
            "non_executable": self.non_executable,
            "auto_activation_allowed": self.auto_activation_allowed,
        }

    def to_markdown(self) -> str:
        lines = [render_frontmatter(self.metadata()), "", f"# {self.name}", ""]
        for section in REQUIRED_SECTIONS:
            lines.extend([f"## {section}", "", str(self.sections.get(section, "")).strip(), ""])
        return "\n".join(lines).rstrip() + "\n"

    def to_boundary_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.skill_id,
            "artifact_kind": "strategy_skill_markdown",
            "write_scope": self.default_write_scope,
            "non_executable": self.non_executable,
            "hard_constraints_editable": self.hard_constraints_editable,
            "auto_activation_allowed": self.auto_activation_allowed,
        }

    @classmethod
    def from_markdown(cls, markdown: str) -> "StrategySkillDocument":
        metadata, body = parse_frontmatter(markdown)
        sections = extract_sections(body)
        return cls(
            schema_version=str(metadata.get("schema_version", "") or ""),
            skill_id=str(metadata.get("skill_id", "") or ""),
            name=str(metadata.get("name", "") or ""),
            status=str(metadata.get("status", "") or ""),
            version=metadata.get("version", 0),
            scope=str(metadata.get("scope", "") or ""),
            created_at=str(metadata.get("created_at", "") or ""),
            updated_at=str(metadata.get("updated_at", "") or ""),
            source_policy_ids=list(metadata.get("source_policy_ids", []) or []),
            source_outcome_ids=list(metadata.get("source_outcome_ids", []) or []),
            promotion=dict(metadata.get("promotion", {}) or {}),
            hard_constraints_editable=metadata.get("hard_constraints_editable"),
            default_write_scope=str(metadata.get("default_write_scope", "") or ""),
            non_executable=metadata.get("non_executable"),
            auto_activation_allowed=metadata.get("auto_activation_allowed"),
            sections=sections,
        )


@dataclass(slots=True)
class StrategySkillEvent:
    event_id: str
    skill_id: str
    schema_version: str
    event_type: str
    event_time: str
    status_after: str
    source_policy_ids: list[str]
    source_outcome_ids: list[str]
    notes: str
    write_scope: str = "learning_only"
    non_executable: bool = True
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.event_id = _require(self.event_id, "event_id")
        self.skill_id = _require(self.skill_id, "skill_id")
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != SKILL_EVENT_SCHEMA_VERSION:
            raise StrategySkillValidationError(f"schema_version must be {SKILL_EVENT_SCHEMA_VERSION}")
        self.event_type = _require_enum(self.event_type, SKILL_EVENT_TYPES, "event_type")
        self.event_time = _timestamp(self.event_time, "event_time")
        self.status_after = _require_enum(self.status_after, SKILL_STATUSES, "status_after")
        self.source_policy_ids = [str(item) for item in _list(self.source_policy_ids, "source_policy_ids")]
        self.source_outcome_ids = [str(item) for item in _list(self.source_outcome_ids, "source_outcome_ids")]
        self.notes = _require(self.notes, "notes")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.non_executable is not True:
            raise StrategySkillValidationError("strategy skill events must be non_executable=true")
        self.audit = _dict(self.audit, "audit")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategySkillEvent":
        return cls(
            event_id=str(payload.get("event_id", "") or ""),
            skill_id=str(payload.get("skill_id", "") or ""),
            schema_version=str(payload.get("schema_version", "") or ""),
            event_type=str(payload.get("event_type", "") or ""),
            event_time=str(payload.get("event_time", "") or ""),
            status_after=str(payload.get("status_after", "") or ""),
            source_policy_ids=list(payload.get("source_policy_ids", []) or []),
            source_outcome_ids=list(payload.get("source_outcome_ids", []) or []),
            notes=str(payload.get("notes", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            audit=dict(payload.get("audit", {}) or {}),
        )


@dataclass(slots=True)
class StrategySkillRegistryEntry:
    skill_id: str
    name: str
    status: str
    version: int
    scope: str
    confidence: float
    support_count: int
    contradiction_count: int
    source_policy_ids: list[str]
    source_outcome_ids: list[str]
    skill_path: str
    event_log_path: str
    updated_at: str
    auto_activation_allowed: bool
    non_executable: bool
    write_scope: str

    def __post_init__(self) -> None:
        self.skill_id = _require(self.skill_id, "skill_id")
        self.name = _require(self.name, "name")
        self.status = _require_enum(self.status, SKILL_STATUSES, "status")
        self.version = max(1, _int(self.version, "version"))
        self.scope = _require(self.scope, "scope")
        self.confidence = _float(self.confidence, "confidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise StrategySkillValidationError("confidence must be between 0 and 1")
        self.support_count = _int(self.support_count, "support_count")
        self.contradiction_count = _int(self.contradiction_count, "contradiction_count")
        self.source_policy_ids = [str(item) for item in _list(self.source_policy_ids, "source_policy_ids")]
        self.source_outcome_ids = [str(item) for item in _list(self.source_outcome_ids, "source_outcome_ids")]
        self.skill_path = _require(self.skill_path, "skill_path")
        self.event_log_path = _require(self.event_log_path, "event_log_path")
        self.updated_at = _timestamp(self.updated_at, "updated_at")
        if self.auto_activation_allowed is not False:
            raise StrategySkillValidationError("auto_activation_allowed must be false in Phase 6")
        if self.non_executable is not True:
            raise StrategySkillValidationError("registry entries must be non_executable=true")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategySkillRegistryEntry":
        return cls(**{field_name: payload.get(field_name) for field_name in cls.__dataclass_fields__})


@dataclass(slots=True)
class StrategySkillRegistry:
    schema_version: str
    generated_at: str
    write_scope: str
    non_executable: bool
    auto_activation_allowed: bool
    entries: list[StrategySkillRegistryEntry]
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = _require(self.schema_version, "schema_version")
        if self.schema_version != REGISTRY_SCHEMA_VERSION:
            raise StrategySkillValidationError(f"schema_version must be {REGISTRY_SCHEMA_VERSION}")
        self.generated_at = _timestamp(self.generated_at, "generated_at")
        self.write_scope = _require_enum(self.write_scope, WRITE_SCOPES, "write_scope")
        if self.non_executable is not True:
            raise StrategySkillValidationError("strategy skill registry must be non_executable=true")
        if self.auto_activation_allowed is not False:
            raise StrategySkillValidationError("auto_activation_allowed must be false in Phase 6")
        self.entries = [
            item if isinstance(item, StrategySkillRegistryEntry) else StrategySkillRegistryEntry.from_dict(item)
            for item in _list(self.entries, "entries")
        ]
        self.summary = _dict(self.summary, "summary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "write_scope": self.write_scope,
            "non_executable": self.non_executable,
            "auto_activation_allowed": self.auto_activation_allowed,
            "entries": [item.to_dict() for item in self.entries],
            "summary": dict(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategySkillRegistry":
        return cls(
            schema_version=str(payload.get("schema_version", "") or ""),
            generated_at=str(payload.get("generated_at", "") or ""),
            write_scope=str(payload.get("write_scope", "") or ""),
            non_executable=payload.get("non_executable"),
            auto_activation_allowed=payload.get("auto_activation_allowed"),
            entries=list(payload.get("entries", []) or []),
            summary=dict(payload.get("summary", {}) or {}),
        )


def validate_skill_output(output: dict[str, Any]) -> dict[str, Any]:
    payload = _dict(output, "skill_output")
    output_type = _require(payload.get("output_type", ""), "output_type")
    if output_type in FORBIDDEN_SKILL_OUTPUTS:
        raise StrategySkillValidationError(f"skill output {output_type!r} is forbidden")
    if output_type not in ALLOWED_SKILL_OUTPUTS:
        raise StrategySkillValidationError(f"skill output {output_type!r} is not allowed")
    payload["skill_id"] = _require(payload.get("skill_id", ""), "skill_id")
    payload["output_type"] = output_type
    payload["value"] = _require(payload.get("value", ""), "value")
    payload["non_executable"] = True
    return payload
