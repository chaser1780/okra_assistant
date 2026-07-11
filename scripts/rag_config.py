from __future__ import annotations

import copy
from pathlib import Path
import tomllib
from typing import Any


DEFAULT_RAG_CONFIG: dict[str, Any] = {
    "rag": {
        "enabled": False,
        "default_profile": "copilot_qa",
        "index_dir": "db/rag",
        "trace_enabled": True,
        "fallback_to_legacy": True,
        "agent_shadow": {
            "enabled": False,
            "write_trace": True,
            "inject_into_prompt": False,
            "compare_legacy": True,
        },
        "agent_default": {
            "enabled": False,
            "min_hits": 1,
            "write_trace": True,
            "fallback_to_legacy": True,
        },
        "profile_evidence": {
            "enabled": False,
            "write_trace": True,
            "decision": {
                "enabled": False,
                "top_k": 8,
                "min_hits": 1,
                "source_kinds": ["committee_bundle", "validated_advice"],
                "domains": ["decision"],
            },
            "memory": {
                "enabled": False,
                "top_k": 6,
                "skip_duplicate_permanent": True,
                "source_kinds": ["long_memory"],
            },
            "review": {
                "enabled": False,
                "top_k": 8,
                "source_kinds": ["long_memory"],
                "include_negative_memory": True,
            },
            "backtest": {
                "enabled": False,
                "top_k": 8,
                "source_kinds": ["long_memory", "validated_advice", "committee_bundle", "portfolio_state"],
                "strict_no_future": True,
            },
        },
        "agent_profiles": {
            "market_analyst": {
                "source_kinds": ["llm_context", "evidence_item", "long_memory"],
                "domains": ["market", "fund"],
                "top_k_portfolio": 8,
                "top_k_per_fund": 3,
                "allow_negative_memory": False,
                "include_execution": False,
                "enabled": True,
            },
            "risk_manager": {
                "source_kinds": ["llm_context", "evidence_item", "long_memory", "validated_advice", "committee_bundle"],
                "domains": ["market", "portfolio", "memory", "risk", "decision", "fund"],
                "top_k_portfolio": 12,
                "top_k_per_fund": 4,
                "allow_negative_memory": False,
                "include_execution": False,
                "enabled": True,
            },
            "portfolio_trader": {
                "source_kinds": ["portfolio_state", "validated_advice", "committee_bundle", "evidence_item", "llm_context"],
                "domains": ["portfolio", "decision", "fund", "market"],
                "top_k_portfolio": 10,
                "top_k_per_fund": 4,
                "allow_negative_memory": False,
                "include_execution": False,
                "enabled": True,
            },
        },
        "embedding": {
            "enabled": False,
            "provider": "OpenAI",
            "model": "text-embedding-3-large",
            "dimensions": 1536,
            "batch_size": 64,
            "timeout_seconds": 60,
            "cache_enabled": True,
            "dry_run": True,
        },
        "vector_store": {
            "backend": "sqlite_mock",
            "sqlite_path": "db/rag/rag.sqlite",
            "allow_chroma": False,
            "allow_faiss": False,
        },
        "sources": {
            "long_memory": True,
            "portfolio_state": True,
            "llm_context": True,
            "evidence_index": True,
            "validated_advice": True,
            "committee_bundle": True,
            "agent_outputs": False,
            "execution_sync": False,
            "raw_news": False,
        },
        "safety": {
            "require_available_from": True,
            "require_source_path": True,
            "exclude_archived_by_default": True,
            "exclude_rejected_by_default": True,
            "exclude_execution_by_default": True,
        },
    }
}


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_repo_path(agent_home: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return agent_home / path


def rag_config_path(agent_home: Path) -> Path:
    return agent_home / "config" / "rag.toml"


def load_rag_config(agent_home: Path) -> dict[str, Any]:
    path = rag_config_path(agent_home)
    if not path.exists():
        return copy.deepcopy(DEFAULT_RAG_CONFIG)
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return _deep_merge(DEFAULT_RAG_CONFIG, payload)


def rag_settings(agent_home: Path) -> dict[str, Any]:
    return load_rag_config(agent_home)["rag"]


def rag_embedding_settings(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    return dict(settings.get("embedding", {}) or {})


def rag_vector_store_settings(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    return dict(settings.get("vector_store", {}) or {})


def rag_agent_shadow_settings(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    return dict(settings.get("agent_shadow", {}) or {})


def rag_agent_default_settings(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    agent_default = dict(settings.get("agent_default", {}) or {})
    agent_default["enabled"] = bool(settings.get("enabled", False)) and bool(agent_default.get("enabled", False))
    return agent_default


def rag_profile_evidence_settings(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    return dict(settings.get("profile_evidence", {}) or {})


def rag_profile_evidence_profile(agent_home: Path, profile_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = rag_profile_evidence_settings(agent_home, config)
    profile = settings.get(profile_name, {}) or {}
    global_enabled = bool(settings.get("enabled", False))
    profile_enabled = bool(profile.get("enabled", False))
    merged = {"enabled": global_enabled and profile_enabled, "write_trace": bool(settings.get("write_trace", True))}
    merged.update(profile)
    merged["enabled"] = global_enabled and profile_enabled
    return merged


def rag_agent_profile(agent_home: Path, agent_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = (config or load_rag_config(agent_home))["rag"]
    profiles = settings.get("agent_profiles", {}) or {}
    profile = profiles.get(agent_name, {}) or {}
    return dict(profile)


def embedding_provider_settings(agent_home: Path, provider_name: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = config or load_rag_config(agent_home)
    embedding = rag_embedding_settings(agent_home, payload)
    name = provider_name or str(embedding.get("provider", "OpenAI") or "OpenAI")
    providers = payload.get("embedding_provider", {}) or {}
    provider = providers.get(name, {}) or providers.get(str(name).lower(), {}) or {}
    return dict(provider)


def is_rag_enabled(agent_home: Path) -> bool:
    return bool(rag_settings(agent_home).get("enabled", False))


def rag_index_dir(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    settings = (config or load_rag_config(agent_home))["rag"]
    return _resolve_repo_path(agent_home, settings.get("index_dir", "db/rag"))


def rag_db_path(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    settings = (config or load_rag_config(agent_home))["rag"]
    vector_store = settings.get("vector_store", {})
    return _resolve_repo_path(agent_home, vector_store.get("sqlite_path", "db/rag/rag.sqlite"))


def rag_vector_store_dir(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    return rag_index_dir(agent_home, config) / "vector_store"


def rag_manifest_dir(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    return rag_index_dir(agent_home, config) / "manifests"


def rag_trace_dir(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    return rag_index_dir(agent_home, config) / "traces"


def rag_eval_dir(agent_home: Path, config: dict[str, Any] | None = None) -> Path:
    return rag_index_dir(agent_home, config) / "eval"


def ensure_rag_layout(agent_home: Path, config: dict[str, Any] | None = None) -> dict[str, Path]:
    paths = {
        "index_dir": rag_index_dir(agent_home, config),
        "vector_store_dir": rag_vector_store_dir(agent_home, config),
        "manifest_dir": rag_manifest_dir(agent_home, config),
        "trace_dir": rag_trace_dir(agent_home, config),
        "eval_dir": rag_eval_dir(agent_home, config),
        "db_path": rag_db_path(agent_home, config),
    }
    for key, path in paths.items():
        if key == "db_path":
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    return paths
