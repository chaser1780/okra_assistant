from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
GENERATED_AT = "2026-05-30T13:00:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed  # noqa: E402
from build_hard_constraint_catalog import CATALOG_PATH, build_catalog, run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402


class HardConstraintCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()
        target = self.agent.root / "docs" / "refactor_runs" / "2026-05-agent-memory-refactor"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            PROJECT_ROOT / "docs" / "refactor_runs" / "2026-05-agent-memory-refactor" / "hard_constraints_inventory.md",
            target / "hard_constraints_inventory.md",
        )

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_catalog_parses_inventory_into_machine_readable_rules(self) -> None:
        payload = build_catalog(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual("hard_constraint_catalog.v1", payload["schema_version"])
        self.assertEqual("shadow_only", payload["write_scope"])
        self.assertTrue(payload["non_executable"])
        self.assertGreaterEqual(payload["summary"]["rule_count"], 20)
        self.assertTrue(payload["summary"]["hard_constraints_remain_deterministic"])
        self.assertFalse(payload["summary"]["soft_policy_can_block"])
        self.assertFalse(payload["summary"]["strategy_skill_can_edit_hard_constraints"])
        self.assertTrue(any(rule["rule_id"] == "guardrail:dca:fixed_schedule" for rule in payload["rules"]))
        self.assertTrue(any(rule["classification"] == "execution_boundary" for rule in payload["rules"]))

    def test_builder_writes_shadow_catalog_only(self) -> None:
        path, payload = run_builder(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(self.agent.root / CATALOG_PATH, path)
        self.assertEqual(payload, json.loads(path.read_text(encoding="utf-8")))
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(self.agent.root / "db" / "validated_advice" / "hard_constraint_catalog.json", payload, self.agent.root)

    def test_cli_catalog_builder_works_with_temp_agent_home(self) -> None:
        completed = self.agent.run_script("build_hard_constraint_catalog.py", "--generated-at", GENERATED_AT)

        self.assertIn("wrote", completed.stdout)
        self.assertTrue((self.agent.root / CATALOG_PATH).exists())


if __name__ == "__main__":
    unittest.main()
