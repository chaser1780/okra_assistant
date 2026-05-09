from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from migrate_runtime_state import run_cutover


class RuntimeStateMigrationTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def legacy_trade_path(self, filename: str) -> str:
        return "/".join(["db", "trade_journal", filename])

    def test_dry_run_reports_legacy_files_without_deleting(self):
        legacy_file = self.agent.write_json(self.legacy_trade_path("2026-03-10.json"), {"items": []})

        report = run_cutover(self.agent.root, dry_run=True)

        self.assertTrue(legacy_file.exists())
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["archived_trade_files"], 1)
        self.assertEqual(report["deleted_legacy_source_dirs"], [])

    def test_cutover_writes_manifest_before_deleting_legacy_dirs(self):
        legacy_file = self.agent.write_json(self.legacy_trade_path("2026-03-10.json"), {"items": [{"fund_code": "F1"}]})

        report = run_cutover(self.agent.root, dry_run=False)

        self.assertFalse(legacy_file.exists())
        manifest_path = Path(report["archive_manifests"]["trade_journal"])
        self.assertTrue(manifest_path.exists())
        archived_file = self.agent.root / "db" / "legacy" / "trade_journal" / "2026-03-10.json"
        self.assertTrue(archived_file.exists())
        self.assertIn(str(legacy_file.parent), report["deleted_legacy_source_dirs"])


if __name__ == "__main__":
    unittest.main()
