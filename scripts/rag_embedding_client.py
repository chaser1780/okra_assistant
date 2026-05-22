from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

from common import load_llm_config, resolve_agent_home
from multiagent_utils import resolve_api_key
from rag_config import embedding_provider_settings, load_rag_config, rag_embedding_settings
from rag_index_store import get_embedding_cache, mark_chunk_embedding, upsert_embedding_cache


def text_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def embedding_cache_key(model: str, text_hash: str) -> str:
    return f"{model}:{text_hash}"


def mock_embedding(text: str, dimensions: int) -> list[float]:
    digest = hashlib.sha256(str(text or "").encode("utf-8")).digest()
    values: list[float] = []
    for index in range(max(1, int(dimensions))):
        byte = digest[index % len(digest)]
        values.append(round((byte / 255.0) * 2.0 - 1.0, 6))
    return values


def _resolve_embedding_provider(agent_home: Path, config: dict[str, Any]) -> dict[str, Any]:
    embedding = rag_embedding_settings(agent_home, config)
    provider_name = str(embedding.get("provider", "OpenAI") or "OpenAI")
    explicit = embedding_provider_settings(agent_home, provider_name, config)
    llm_config = load_llm_config(agent_home)
    llm_provider = (llm_config.get("model_providers", {}) or {}).get(provider_name, {})
    base_url = str(explicit.get("base_url") or llm_provider.get("base_url") or "").rstrip("/")
    if base_url.endswith("/responses"):
        base_url = base_url[: -len("/responses")]
    endpoint = str(explicit.get("embeddings_url") or "")
    if not endpoint:
        endpoint = f"{base_url}/embeddings" if base_url else ""
    resolved = {
        "provider": provider_name,
        "base_url": base_url,
        "endpoint": endpoint,
        "api_key_env": explicit.get("api_key_env") or llm_config.get("api_key_env", "OPENAI_API_KEY"),
        "api_key_file": explicit.get("api_key_file") or llm_config.get("api_key_file", ""),
        "api_key": explicit.get("api_key") or llm_config.get("api_key", ""),
    }
    return resolved


def _resolve_embedding_api_key(provider: dict[str, Any]) -> str:
    temp_config = {
        "model_provider": provider.get("provider", "OpenAI"),
        "api_key": str(provider.get("api_key", "") or ""),
        "api_key_file": str(provider.get("api_key_file", "") or ""),
        "api_key_env": str(provider.get("api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY"),
    }
    return resolve_api_key(temp_config)


class RagEmbeddingClient:
    def __init__(self, agent_home: Path, config: dict[str, Any] | None = None):
        self.agent_home = agent_home
        self.config = config or load_rag_config(agent_home)
        self.settings = rag_embedding_settings(agent_home, self.config)
        self.provider = _resolve_embedding_provider(agent_home, self.config)
        self.model = str(self.settings.get("model", "text-embedding-3-large") or "text-embedding-3-large")
        self.dimensions = int(self.settings.get("dimensions", 1536) or 1536)
        self.timeout_seconds = int(self.settings.get("timeout_seconds", 60) or 60)

    @property
    def dry_run(self) -> bool:
        return bool(self.settings.get("dry_run", True)) or not bool(self.settings.get("enabled", False))

    def probe(self, *, dry_run: bool | None = None) -> dict[str, Any]:
        use_dry_run = self.dry_run if dry_run is None else dry_run
        if use_dry_run:
            vector = mock_embedding("okra rag probe", min(self.dimensions, 8))
            return {
                "status": "ok",
                "mode": "dry_run",
                "provider": self.provider["provider"],
                "model": self.model,
                "dimensions": self.dimensions,
                "detail": "dry-run/mock embedding available; no network request sent",
                "sample_dimensions": len(vector),
            }
        if not self.provider.get("endpoint"):
            return {"status": "error", "mode": "live", "detail": "embedding endpoint is not configured", "provider": self.provider["provider"]}
        try:
            api_key = _resolve_embedding_api_key(self.provider)
        except Exception as exc:
            return {"status": "warning", "mode": "mock_fallback", "detail": str(exc), "provider": self.provider["provider"], "model": self.model}
        try:
            response = requests.post(
                self.provider["endpoint"],
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": "okra rag probe", "dimensions": self.dimensions},
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                return {
                    "status": "warning",
                    "mode": "mock_fallback",
                    "provider": self.provider["provider"],
                    "endpoint": self.provider["endpoint"],
                    "status_code": response.status_code,
                    "detail": response.text[:500],
                }
            payload = response.json()
            vector = ((payload.get("data") or [{}])[0] or {}).get("embedding") or []
            return {
                "status": "ok",
                "mode": "live",
                "provider": self.provider["provider"],
                "endpoint": self.provider["endpoint"],
                "model": self.model,
                "dimensions": len(vector),
            }
        except Exception as exc:
            return {"status": "warning", "mode": "mock_fallback", "provider": self.provider["provider"], "detail": str(exc)}

    def embed_texts(self, texts: list[str], *, dry_run: bool | None = None) -> list[list[float]]:
        use_dry_run = self.dry_run if dry_run is None else dry_run
        if use_dry_run:
            return [mock_embedding(text, self.dimensions) for text in texts]
        api_key = _resolve_embedding_api_key(self.provider)
        response = requests.post(
            self.provider["endpoint"],
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts, "dimensions": self.dimensions},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json().get("data", []) or []
        return [item.get("embedding", []) for item in data]

    def embed_chunk_with_cache(self, chunk: dict[str, Any], *, dry_run: bool | None = None) -> dict[str, Any]:
        text = str(chunk.get("text_for_embedding", "") or "")
        chunk_id = str(chunk.get("chunk_id", "") or "")
        digest = text_sha256(text)
        cache_key = embedding_cache_key(self.model, digest)
        cached = get_embedding_cache(self.agent_home, cache_key)
        if cached and cached.get("status") == "ok":
            mark_chunk_embedding(self.agent_home, chunk_id, model=self.model, status="ok", embedding_sha256=digest)
            return {"status": "cached", "cache_key": cache_key, "chunk_id": chunk_id, "vector_ref": cached.get("vector_ref", "")}
        try:
            vector = self.embed_texts([text], dry_run=dry_run)[0]
            vector_ref = f"sqlite_mock:{cache_key}"
            upsert_embedding_cache(
                self.agent_home,
                {
                    "cache_key": cache_key,
                    "chunk_id": chunk_id,
                    "embedding_model": self.model,
                    "text_sha256": digest,
                    "vector_ref": vector_ref,
                    "status": "ok",
                    "error": {},
                },
            )
            mark_chunk_embedding(self.agent_home, chunk_id, model=self.model, status="ok", embedding_sha256=digest)
            return {"status": "embedded", "cache_key": cache_key, "chunk_id": chunk_id, "dimensions": len(vector), "vector_ref": vector_ref}
        except Exception as exc:
            upsert_embedding_cache(
                self.agent_home,
                {
                    "cache_key": cache_key,
                    "chunk_id": chunk_id,
                    "embedding_model": self.model,
                    "text_sha256": digest,
                    "vector_ref": "",
                    "status": "error",
                    "error": {"message": str(exc)},
                },
            )
            mark_chunk_embedding(self.agent_home, chunk_id, model=self.model, status="error", embedding_sha256=digest)
            return {"status": "error", "cache_key": cache_key, "chunk_id": chunk_id, "error": str(exc)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe or use OKRA RAG embeddings.")
    parser.add_argument("--agent-home", default=None)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent_home = resolve_agent_home(args.agent_home)
    client = RagEmbeddingClient(agent_home)
    if args.probe:
        result = client.probe(dry_run=True if args.dry_run else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"ok", "warning"} else 1
    print(json.dumps({"status": "error", "detail": "use --probe"}, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
