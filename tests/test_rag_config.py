from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_config import ensure_rag_layout, is_rag_enabled, load_rag_config, rag_db_path, rag_index_dir, rag_profile_evidence_profile


class RagConfigTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_missing_config_uses_safe_disabled_defaults(self):
        config = load_rag_config(self.agent.root)
        self.assertFalse(config["rag"]["enabled"])
        self.assertTrue(config["rag"]["fallback_to_legacy"])
        self.assertTrue(config["rag"]["embedding"]["dry_run"])
        self.assertFalse(config["rag"]["embedding"]["enabled"])
        self.assertEqual("sqlite_mock", config["rag"]["vector_store"]["backend"])
        self.assertFalse(config["rag"]["profile_evidence"]["enabled"])
        self.assertFalse(rag_profile_evidence_profile(self.agent.root, "decision")["enabled"])
        self.assertFalse(is_rag_enabled(self.agent.root))

    def test_profile_evidence_requires_global_and_profile_enable(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag.profile_evidence]
enabled = false

[rag.profile_evidence.decision]
enabled = true
""",
        )
        self.assertFalse(rag_profile_evidence_profile(self.agent.root, "decision")["enabled"])
        self.agent.write_text(
            "config/rag.toml",
            """[rag.profile_evidence]
enabled = true

[rag.profile_evidence.decision]
enabled = true
""",
        )
        self.assertTrue(rag_profile_evidence_profile(self.agent.root, "decision")["enabled"])

    def test_config_file_overrides_defaults_without_dropping_nested_values(self):
        self.agent.write_text(
            "config/rag.toml",
            """[rag]
enabled = true
index_dir = "db/custom_rag"

[rag.embedding]
model = "custom-embedding"

[rag.sources]
execution_sync = true
""",
        )
        config = load_rag_config(self.agent.root)
        self.assertTrue(config["rag"]["enabled"])
        self.assertEqual("db/custom_rag", config["rag"]["index_dir"])
        self.assertEqual("custom-embedding", config["rag"]["embedding"]["model"])
        self.assertEqual(1536, config["rag"]["embedding"]["dimensions"])
        self.assertTrue(config["rag"]["sources"]["execution_sync"])
        self.assertFalse(config["rag"]["sources"]["raw_news"])

    def test_layout_paths_are_repo_relative(self):
        paths = ensure_rag_layout(self.agent.root)
        self.assertEqual(self.agent.root / "db" / "rag", rag_index_dir(self.agent.root))
        self.assertEqual(self.agent.root / "db" / "rag" / "rag.sqlite", rag_db_path(self.agent.root))
        self.assertTrue(paths["index_dir"].exists())
        self.assertTrue(paths["vector_store_dir"].exists())
        self.assertTrue(paths["manifest_dir"].exists())
        self.assertTrue(paths["trace_dir"].exists())
        self.assertTrue(paths["eval_dir"].exists())


if __name__ == "__main__":
    unittest.main()
