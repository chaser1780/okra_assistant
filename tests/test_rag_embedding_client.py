from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_embedding_client import RagEmbeddingClient, embedding_cache_key, text_sha256
from rag_index_store import get_embedding_cache, upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument
from rag_vector_store import build_vector_store


class RagEmbeddingClientTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _chunk(self) -> RagChunk:
        doc = RagDocument(
            doc_id="doc-1",
            source_kind="llm_context",
            source_path="db/llm_context/2026-05-20.json",
            source_record_id="doc-1",
            title="Doc",
            summary="AI fund risk",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="fund",
            source_tier="daily_context",
        )
        chunk = RagChunk(
            chunk_id="chunk-1",
            doc_id="doc-1",
            chunk_index=0,
            text_for_embedding="AI fund risk only",
            text_for_llm="AI fund risk",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])
        return chunk

    def test_probe_dry_run_succeeds_without_api_key(self):
        client = RagEmbeddingClient(self.agent.root)
        result = client.probe(dry_run=True)
        self.assertEqual("ok", result["status"])
        self.assertEqual("dry_run", result["mode"])

    def test_live_probe_falls_back_when_api_key_missing(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag]
enabled = false

[rag.embedding]
enabled = true
dry_run = false
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 8

[rag.vector_store]
backend = "sqlite_mock"
""",
        )
        self.agent.write_text("config/llm.toml", 'model_provider = "OpenAI"\napi_key_env = "MISSING_RAG_KEY"\napi_key_file = ""\n[model_providers.OpenAI]\nbase_url = "https://api.example.test/v1"\n')
        result = RagEmbeddingClient(self.agent.root).probe(dry_run=False)
        self.assertEqual("warning", result["status"])
        self.assertEqual("mock_fallback", result["mode"])

    def test_relative_api_key_file_resolves_under_project_root(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag]
enabled = false

[rag.embedding]
enabled = true
dry_run = false
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 8

[rag.vector_store]
backend = "sqlite_mock"
""",
        )
        self.agent.write_text(
            "config/llm.toml",
            'model_provider = "OpenAI"\napi_key_file = "config/openai_api_key.txt"\napi_key_env = "MISSING_RAG_KEY"\n[model_providers.OpenAI]\nbase_url = "https://api.example.test/v1"\n',
        )
        self.agent.write_text("config/openai_api_key.txt", "file-key")

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"data": [{"embedding": [0.2] * 8}]}

        seen = {}

        def fake_post(url, headers, json, timeout):
            seen["auth"] = headers["Authorization"]
            return FakeResponse()

        with patch("rag_embedding_client.requests.post", side_effect=fake_post):
            result = RagEmbeddingClient(self.agent.root).probe(dry_run=False)

        self.assertEqual("ok", result["status"])
        self.assertEqual("Bearer file-key", seen["auth"])

    def test_embed_chunk_uses_cache_on_second_call(self):
        chunk = self._chunk()
        client = RagEmbeddingClient(self.agent.root)
        first = client.embed_chunk_with_cache(chunk.to_dict(), dry_run=True)
        second = client.embed_chunk_with_cache(chunk.to_dict(), dry_run=True)
        cache_key = embedding_cache_key(client.model, text_sha256(chunk.text_for_embedding))
        self.assertEqual("embedded", first["status"])
        self.assertEqual("cached", second["status"])
        self.assertIsNotNone(get_embedding_cache(self.agent.root, cache_key))

    def test_vector_store_sqlite_mock_upserts_cache(self):
        chunk = self._chunk()
        client = RagEmbeddingClient(self.agent.root)
        vector = client.embed_texts([chunk.text_for_embedding], dry_run=True)[0]
        store = build_vector_store(self.agent.root)
        store.upsert([chunk.to_dict()], [vector])
        results = store.search(vector, top_k=1)
        self.assertEqual(1, len(results))
        self.assertGreaterEqual(results[0]["score"], 0.99)

    def test_live_embed_sends_only_text_input(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag]
enabled = false

[rag.embedding]
enabled = true
dry_run = false
provider = "OpenAI"
model = "text-embedding-3-large"
dimensions = 8

[rag.vector_store]
backend = "sqlite_mock"
""",
        )
        self.agent.write_text("config/llm.toml", 'model_provider = "OpenAI"\napi_key = "test-key"\napi_key_file = ""\napi_key_env = "OPENAI_API_KEY"\n[model_providers.OpenAI]\nbase_url = "https://api.example.test/v1"\n')

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"embedding": [0.1] * 8}]}

        seen = {}

        def fake_post(url, headers, json, timeout):
            seen["json"] = json
            return FakeResponse()

        with patch("rag_embedding_client.requests.post", side_effect=fake_post):
            vectors = RagEmbeddingClient(self.agent.root).embed_texts(["safe text"], dry_run=False)
        self.assertEqual([[0.1] * 8], vectors)
        self.assertEqual("safe text", seen["json"]["input"][0])
        self.assertNotIn("payload_json", seen["json"])


if __name__ == "__main__":
    unittest.main()
