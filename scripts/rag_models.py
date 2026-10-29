from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any


REQUIRED_DOCUMENT_FIELDS = (
    "doc_id",
    "source_kind",
    "source_path",
    "source_record_id",
    "title",
    "summary",
    "as_of_date",
    "available_from",
    "domain",
    "source_tier",
    "visibility",
)


def _clean_text(value: str | None) -> str:
    return str(value or "").strip()


def _date_text(value: str | date | datetime | None, field_name: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    try:
        date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"{field_name} must start with YYYY-MM-DD") from exc
    return text[:10]


def _timestamp_text(value: str | datetime | None, field_name: str) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    return text


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(json_dumps(value).encode("utf-8")).hexdigest()


def ensure_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = [_clean_text(item) for item in value if _clean_text(item)]
    return result


@dataclass(slots=True)
class RagDocument:
    doc_id: str
    source_kind: str
    source_path: str
    source_record_id: str
    title: str
    summary: str
    as_of_date: str
    available_from: str
    domain: str
    source_tier: str
    visibility: str = "default"
    event_date: str = ""
    published_at: str = ""
    entity_type: str = ""
    entity_id: str = ""
    fund_codes: list[str] = field(default_factory=list)
    status: str = ""
    valid_from: str = ""
    valid_until: str = ""
    learning_scope: str = ""
    is_negative_example: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    content_sha256: str = ""

    def __post_init__(self) -> None:
        for field_name in ("doc_id", "source_kind", "source_path", "source_record_id", "title", "summary", "domain", "source_tier", "visibility"):
            value = _clean_text(getattr(self, field_name))
            if not value:
                raise ValueError(f"{field_name} is required")
            setattr(self, field_name, value)
        self.as_of_date = _date_text(self.as_of_date, "as_of_date")
        self.available_from = _timestamp_text(self.available_from, "available_from")
        self.event_date = _date_text(self.event_date, "event_date") if _clean_text(self.event_date) else ""
        self.published_at = _timestamp_text(self.published_at, "published_at") if _clean_text(self.published_at) else ""
        self.valid_from = _date_text(self.valid_from, "valid_from") if _clean_text(self.valid_from) else ""
        self.valid_until = _date_text(self.valid_until, "valid_until") if _clean_text(self.valid_until) else ""
        self.fund_codes = ensure_string_list(self.fund_codes, "fund_codes")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        if not self.content_sha256:
            self.content_sha256 = stable_sha256(
                {
                    "doc_id": self.doc_id,
                    "source_kind": self.source_kind,
                    "source_record_id": self.source_record_id,
                    "title": self.title,
                    "summary": self.summary,
                    "payload": self.payload,
                    "metadata": self.metadata,
                }
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RagChunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text_for_embedding: str
    text_for_llm: str
    token_estimate: int = 0
    embedding_model: str = ""
    embedding_status: str = "pending"
    embedding_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("chunk_id", "doc_id", "text_for_embedding", "text_for_llm"):
            value = _clean_text(getattr(self, field_name))
            if not value:
                raise ValueError(f"{field_name} is required")
            setattr(self, field_name, value)
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be >= 0")
        if self.token_estimate < 0:
            raise ValueError("token_estimate must be >= 0")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        if not self.embedding_sha256:
            self.embedding_sha256 = hashlib.sha256(self.text_for_embedding.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RagQueryPlan:
    query: str
    retrieval_profile: str
    as_of_date: str
    query_date: str = ""
    decision_at: str | None = None
    time_mode: str = "selected_date"
    intent: str = "general_qa"
    fund_codes: list[str] = field(default_factory=list)
    source_kinds: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    top_k: int = 8
    token_budget: int = 6000
    allow_future_data: bool = False
    include_negative_memory: bool = False
    include_archived: bool = False
    include_rejected: bool = False
    include_execution: bool = False
    require_structured_facts: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.query = _clean_text(self.query)
        self.retrieval_profile = _clean_text(self.retrieval_profile)
        if not self.query:
            raise ValueError("query is required")
        if not self.retrieval_profile:
            raise ValueError("retrieval_profile is required")
        self.as_of_date = _date_text(self.as_of_date, "as_of_date")
        self.query_date = _date_text(self.query_date or self.as_of_date, "query_date")
        self.fund_codes = ensure_string_list(self.fund_codes, "fund_codes")
        self.source_kinds = ensure_string_list(self.source_kinds, "source_kinds")
        self.domains = ensure_string_list(self.domains, "domains")
        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.token_budget <= 0:
            raise ValueError("token_budget must be > 0")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        self.decision_at = self._validate_decision_at()

    def _validate_decision_at(self) -> str | None:
        raw = _clean_text(str(self.decision_at or ""))
        if not raw:
            self.metadata.setdefault("cutoff_precision", "end_of_day_legacy")
            self.metadata.setdefault(
                "time_basis_note",
                "date-only query: cutoff is end of day T23:59:59+08:00; does NOT guarantee no future intraday information",
            )
            return None
        try:
            instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("decision_at must be a timezone-aware ISO 8601 timestamp") from exc
        if instant.tzinfo is None:
            raise ValueError("decision_at must be timezone-aware (offset required), not naive")
        local_day = instant.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        if local_day != self.query_date:
            raise ValueError(
                f"decision_at local date {local_day} does not match query_date {self.query_date}"
            )
        self.metadata["cutoff_precision"] = "decision_at_instant"
        self.metadata["time_basis_note"] = "filtered by exact decision_at instant, including intraday"
        return instant.isoformat(timespec="seconds")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RagHit:
    chunk_id: str
    doc_id: str
    score: float
    source_kind: str
    title: str
    text_for_llm: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("chunk_id", "doc_id", "source_kind", "title", "text_for_llm"):
            value = _clean_text(getattr(self, field_name))
            if not value:
                raise ValueError(f"{field_name} is required")
            setattr(self, field_name, value)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RagTrace:
    trace_id: str
    query_plan: dict[str, Any]
    hits: list[dict[str, Any]] = field(default_factory=list)
    rejected_samples: list[dict[str, Any]] = field(default_factory=list)
    missing_data: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trace_id = _clean_text(self.trace_id)
        if not self.trace_id:
            raise ValueError("trace_id is required")
        if not isinstance(self.query_plan, dict):
            raise ValueError("query_plan must be a dict")
        for field_name in ("hits", "rejected_samples", "missing_data"):
            if not isinstance(getattr(self, field_name), list):
                raise ValueError(f"{field_name} must be a list")
        if not self.created_at:
            self.created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        else:
            self.created_at = _timestamp_text(self.created_at, "created_at")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
