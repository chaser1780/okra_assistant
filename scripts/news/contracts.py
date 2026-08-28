from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    source_key: str
    retrieved_at: str
    records: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    freshness: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    retry_count: int = 0
    latency_ms: int | None = None
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "sourceKey": self.source_key,
            "retrievedAt": self.retrieved_at,
            "records": self.records,
            "coverage": self.coverage,
            "freshness": self.freshness,
            "warnings": self.warnings,
            "retryCount": self.retry_count,
            "latencyMs": self.latency_ms,
            "status": self.status,
        }
