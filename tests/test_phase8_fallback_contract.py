from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
GENERATED_AT = "2026-05-30T13:20:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed  # noqa: E402
from audit_phase8_readiness import build_phase8_audit  # noqa: E402
from build_phase8_fallback_contract import CONTRACT_PATH, run_builder  # noqa: E402
from helpers import TempAgentHome  # noqa: E402


class Phase8FallbackContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_contract_builder_writes_design_only_switch_and_rollback(self) -> None:
        path, payload = run_builder(self.agent.root, generated_at=GENERATED_AT)

        self.assertEqual(self.agent.root / CONTRACT_PATH, path)
        self.assertEqual("phase8_fallback_contract.v1", payload["schema_version"])
        self.assertEqual("shadow_only", payload["write_scope"])
        self.assertTrue(payload["non_executable"])
        self.assertEqual("OKRA_USE_SHADOW_ADVICE_ADAPTER", payload["fallback_switch"]["env_var"])
        self.assertFalse(payload["fallback_switch"]["active"])
        self.assertFalse(payload["summary"]["fallback_switch_active"])
        self.assertTrue(payload["summary"]["rollback_command_documented"])
        self.assertFalse(payload["summary"]["promotion_ready"])
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(self.agent.root / "db" / "validated_advice" / "fallback_contract.json", payload, self.agent.root)

    def test_readiness_uses_contract_without_promoting_fallback_gate(self) -> None:
        run_builder(self.agent.root, generated_at=GENERATED_AT)

        audit = build_phase8_audit(self.agent.root, "2026-05-22", generated_at=GENERATED_AT, promotion_approved=True)
        gates = {item["gate_id"]: item for item in audit["required_evidence"]}

        self.assertEqual("partial", gates["fallback_switch"]["status"])
        self.assertEqual("ready", gates["rollback_path"]["status"])
        self.assertIn("fallback_switch", audit["blocking_gates"])
        self.assertNotIn("rollback_path", audit["blocking_gates"])
        self.assertFalse(audit["promotion_ready"])

    def test_cli_contract_builder_works_with_temp_agent_home(self) -> None:
        completed = self.agent.run_script("build_phase8_fallback_contract.py", "--generated-at", GENERATED_AT)

        self.assertIn("wrote Phase 8 fallback contract", completed.stdout)
        payload = json.loads((self.agent.root / CONTRACT_PATH).read_text(encoding="utf-8"))
        self.assertFalse(payload["summary"]["fallback_switch_active"])


if __name__ == "__main__":
    unittest.main()
