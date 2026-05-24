from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BoundaryViolation(ValueError):
    """Raised when a refactor artifact attempts a forbidden write or execution."""


FORBIDDEN_OFFICIAL_PREFIXES = (
    "db/validated_advice/",
    "db/decision_latest/",
    "db/decision_ledger/",
    "db/portfolio_state/",
    "db/execution_sync/",
    "db/long_memory/",
)

SHADOW_ALLOWED_PREFIXES = (
    "db/refactor_shadow_runs/",
    "db/action_tickets/",
    "db/action_debates/",
    "tests/fixtures/golden_slices/",
)

LEARNING_ALLOWED_PREFIXES = (
    "db/refactor_shadow_runs/",
    "tests/fixtures/golden_slices/",
)


@dataclass(slots=True)
class BoundaryCheck:
    check: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"check": self.check, "status": self.status, "detail": self.detail}


def relative_posix(path: str | Path, agent_home: str | Path | None = None) -> str:
    raw = Path(path)
    base = Path(agent_home).resolve() if agent_home else Path(__file__).resolve().parents[1]
    try:
        resolved = raw.resolve()
    except OSError:
        resolved = raw
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError:
        return raw.as_posix().replace("\\", "/")


def artifact_write_scope(artifact: dict[str, Any]) -> str:
    return str(artifact.get("write_scope", "") or "").strip()


def _iter_nested_artifacts(artifact: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(artifact, dict):
        found.append(artifact)
        for key in ("tickets", "events", "policies", "recent_events"):
            value = artifact.get(key)
            if isinstance(value, list):
                for item in value:
                    found.extend(_iter_nested_artifacts(item))
    elif isinstance(artifact, list):
        for item in artifact:
            found.extend(_iter_nested_artifacts(item))
    return found


def assert_non_executable(artifact: dict[str, Any]) -> BoundaryCheck:
    violations: list[str] = []
    for index, item in enumerate(_iter_nested_artifacts(artifact)):
        if "non_executable" in item and item.get("non_executable") is not True:
            identifier = item.get("ticket_id") or item.get("outcome_id") or item.get("artifact_id") or f"item:{index}"
            violations.append(str(identifier))
    if violations:
        raise BoundaryViolation("non_executable=false is not allowed for refactor shadow artifacts: " + ", ".join(violations))
    return BoundaryCheck("non_executable", "pass", "all refactor artifacts are non-executable")


def _assert_no_forbidden_prefix(relative_path: str) -> None:
    normalized = relative_path.replace("\\", "/")
    for prefix in FORBIDDEN_OFFICIAL_PREFIXES:
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            raise BoundaryViolation(f"forbidden official write path: {relative_path}")


def assert_shadow_write_allowed(path: str | Path, artifact: dict[str, Any], agent_home: str | Path | None = None) -> BoundaryCheck:
    relative_path = relative_posix(path, agent_home)
    _assert_no_forbidden_prefix(relative_path)
    scope = artifact_write_scope(artifact)
    if scope != "shadow_only":
        raise BoundaryViolation(f"shadow write requires write_scope=shadow_only, got {scope or '<missing>'}")
    if not any(relative_path.startswith(prefix) for prefix in SHADOW_ALLOWED_PREFIXES):
        raise BoundaryViolation(f"shadow write path is outside allowed roots: {relative_path}")
    return BoundaryCheck("shadow_write", "pass", f"{relative_path} allowed")


def assert_learning_write_allowed(path: str | Path, artifact: dict[str, Any], agent_home: str | Path | None = None) -> BoundaryCheck:
    relative_path = relative_posix(path, agent_home)
    _assert_no_forbidden_prefix(relative_path)
    scope = artifact_write_scope(artifact)
    if scope != "learning_only":
        raise BoundaryViolation(f"learning write requires write_scope=learning_only, got {scope or '<missing>'}")
    if not any(relative_path.startswith(prefix) for prefix in LEARNING_ALLOWED_PREFIXES):
        raise BoundaryViolation(f"learning write path is outside allowed roots: {relative_path}")
    return BoundaryCheck("learning_write", "pass", f"{relative_path} allowed")


def assert_refactor_write_allowed(path: str | Path, artifact: dict[str, Any], agent_home: str | Path | None = None) -> list[BoundaryCheck]:
    checks = [assert_non_executable(artifact)]
    scope = artifact_write_scope(artifact)
    if scope == "shadow_only":
        checks.append(assert_shadow_write_allowed(path, artifact, agent_home))
    elif scope == "learning_only":
        checks.append(assert_learning_write_allowed(path, artifact, agent_home))
    else:
        raise BoundaryViolation(f"unsupported refactor write_scope: {scope or '<missing>'}")
    return checks


def find_forbidden_write_paths(paths: list[str | Path], agent_home: str | Path | None = None) -> list[str]:
    forbidden: list[str] = []
    for path in paths:
        relative_path = relative_posix(path, agent_home)
        try:
            _assert_no_forbidden_prefix(relative_path)
        except BoundaryViolation:
            forbidden.append(relative_path)
    return forbidden
