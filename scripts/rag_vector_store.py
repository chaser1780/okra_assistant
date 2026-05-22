from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rag_config import load_rag_config, rag_vector_store_settings
from rag_index_store import upsert_embedding_cache
from rag_embedding_client import embedding_cache_key, text_sha256


class RagVectorStore(ABC):
    @abstractmethod
    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(self, query_vector: list[float], *, filters: dict[str, Any] | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def delete_missing(self, manifest_id: str) -> None:
        ...


class SQLiteMockVectorStore(RagVectorStore):
    def __init__(self, agent_home: Path, model: str):
        self.agent_home = agent_home
        self.model = model
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors):
            text_hash = text_sha256(str(chunk.get("text_for_embedding", "") or ""))
            cache_key = embedding_cache_key(self.model, text_hash)
            vector_ref = f"sqlite_mock:{cache_key}"
            self._vectors[vector_ref] = list(vector)
            upsert_embedding_cache(
                self.agent_home,
                {
                    "cache_key": cache_key,
                    "chunk_id": str(chunk.get("chunk_id", "")),
                    "embedding_model": self.model,
                    "text_sha256": text_hash,
                    "vector_ref": vector_ref,
                    "status": "ok",
                    "error": {},
                },
            )

    def search(self, query_vector: list[float], *, filters: dict[str, Any] | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        results = []
        for vector_ref, vector in self._vectors.items():
            score = _cosine_similarity(query_vector, vector)
            results.append({"vector_ref": vector_ref, "score": score})
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

    def delete_missing(self, manifest_id: str) -> None:
        return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = sum(left[index] * left[index] for index in range(size)) ** 0.5
    right_norm = sum(right[index] * right[index] for index in range(size)) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return round(dot / (left_norm * right_norm), 6)


def build_vector_store(agent_home: Path, config: dict[str, Any] | None = None) -> RagVectorStore:
    payload = config or load_rag_config(agent_home)
    vector_settings = rag_vector_store_settings(agent_home, payload)
    embedding = payload.get("rag", {}).get("embedding", {}) or {}
    backend = str(vector_settings.get("backend", "sqlite_mock") or "sqlite_mock")
    model = str(embedding.get("model", "text-embedding-3-large") or "text-embedding-3-large")
    if backend == "sqlite_mock":
        return SQLiteMockVectorStore(agent_home, model)
    raise ValueError(f"Unsupported RAG vector backend: {backend}")
