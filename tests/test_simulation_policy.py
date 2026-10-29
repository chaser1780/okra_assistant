from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import simulation_policy as sp  # noqa: E402


class SizeTierTests(unittest.TestCase):
    def test_invalid_tier_fails_closed_to_none_never_inferred_medium(self):
        # 非法/缺失 tier -> none（hold），绝不回退成 medium 或按旧金额反推
        for bad in ("mediumm", "", None, "huge", 99):
            self.assertEqual("none", sp.normalize_size_tier(bad))
        self.assertEqual("medium", sp.normalize_size_tier(" Medium "))

    def test_evidence_quality_invalid_fails_closed_to_unavailable(self):
        for bad in ("good", "", None, 7):
            self.assertEqual("unavailable", sp.normalize_evidence_quality(bad))
        self.assertEqual("high", sp.normalize_evidence_quality("HIGH"))

    def test_sized_amount_is_exact_ratio_not_100_rounded_not_capped(self):
        # 25% of 12345.67 -> 3086.42（不取整到100、不被静态cap截断）
        amt = sp.sized_amount(12345.67, "medium")
        self.assertEqual(round(12345.67 * 0.25, 2), amt)
        self.assertNotEqual(round(amt, -2), amt, "不应取整到100元粒度")
        # 即便 basis 远大于任何静态 cap_value，新路径也不在这里截断
        self.assertEqual(round(2_000_000 * 0.50, 2), sp.sized_amount(2_000_000, "large"))

    def test_zero_basis_gated_to_hold_manual_establishment(self):
        out = sp.resolve_sized_direction("add", "large", 0.0)
        self.assertEqual("hold", out["direction"])
        self.assertEqual("none", out["size_tier"])
        self.assertTrue(out["zero_basis_gated"])
        # 有仓位则放行
        out2 = sp.resolve_sized_direction("add", "small", 5000.0)
        self.assertEqual("add", out2["direction"])
        self.assertEqual("small", out2["size_tier"])


class StatePriorityTests(unittest.TestCase):
    def test_strictest_state_order(self):
        self.assertEqual("blocked", sp.strictest_state("approved", "degraded", "blocked"))
        self.assertEqual("degraded", sp.strictest_state("shadow_only", "degraded"))
        # approved / shadow_only 同级（契约 §5），均允许交易
        self.assertIn(sp.strictest_state("approved", "shadow_only"), {"approved", "shadow_only"})

    def test_unknown_state_fails_closed_to_blocked(self):
        self.assertEqual("blocked", sp.strictest_state("approved", "weird_state"))
        self.assertEqual("blocked", sp.strictest_state(None))
        self.assertTrue(sp.state_allows_trade("approved"))
        self.assertFalse(sp.state_allows_trade("degraded"))
        self.assertFalse(sp.state_allows_trade("nonsense"))


class BasisFreezeTests(unittest.TestCase):
    def _portfolio(self, as_of="2026-06-01", values=None):
        values = values or {"F1": 10000.0, "F2": 4000.0}
        return {
            "as_of_date": as_of,
            "funds": [{"fund_code": c, "current_value": v} for c, v in values.items()],
        }

    def test_first_decision_builds_basis_reused_on_same_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            pf = self._portfolio()
            basis = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True)
            # 同日重复运行，即便 portfolio 对象"看起来"更新，也复用冻结 basis，不复利重取
            reused = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True)
            self.assertEqual(basis["snapshot_sha256"], reused["snapshot_sha256"])
            self.assertEqual(10000.0, sp.basis_value_for(basis, "F1"))
            self.assertTrue(sp.decision_basis_path(home, "2026-06-01").exists())

    def test_same_day_drift_reuses_frozen_basis_no_compounding(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            b0 = sp.get_or_freeze_basis(home, "2026-06-01", self._portfolio(), write=True)
            # 同日实时组合漂移/再估值：必须复用冻结 basis，绝不按新值复利重算
            drifted = self._portfolio(values={"F1": 12000.0, "F2": 4000.0})
            reused = sp.get_or_freeze_basis(home, "2026-06-01", drifted, write=True)
            self.assertEqual(b0["funds"]["F1"], reused["funds"]["F1"])
            self.assertNotEqual(12000.0, reused["funds"]["F1"])

    def test_corrupt_manifest_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            path = sp.decision_basis_path(home, "2026-06-01")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"run_date": "2099-01-01", "funds": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                sp.get_or_freeze_basis(home, "2026-06-01", self._portfolio(), write=True)

    def test_force_rerun_does_not_magnify_basis(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            pf = self._portfolio()
            b1 = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True)
            b2 = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True)
            self.assertEqual(b1["funds"]["F1"], b2["funds"]["F1"])


class LegacyTests(unittest.TestCase):
    def test_legacy_advice_detected_and_not_tier_inferred(self):
        self.assertTrue(sp.is_legacy_advice({"schema_version": "v1", "tactical_amount": 5000}))
        self.assertFalse(sp.is_legacy_advice({"schema_version": "simulation_v2"}))

    def test_config_loads_defaults(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            cfg = sp.load_simulation_config(home)  # 无文件 -> 内置默认
            self.assertEqual("virtual_external_flows", cfg["funding_mode"])
            self.assertAlmostEqual(0.25, cfg["size_ratios"]["medium"])


class SecurityHardeningTests(unittest.TestCase):
    def test_tampered_funds_rejected_by_fingerprint(self):
        import tempfile, json
        with tempfile.TemporaryDirectory() as home:
            pf = {"as_of_date": "2026-06-01", "funds": [{"fund_code": "F1", "current_value": 10000.0}]}
            basis = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True)
            path = sp.decision_basis_path(home, "2026-06-01")
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["funds"]["F1"] = 999999.0  # 篡改放大
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                sp.get_or_freeze_basis(home, "2026-06-01", pf)

    def test_bad_run_date_rejected_no_path_escape(self):
        with self.assertRaises(ValueError):
            sp.decision_basis_path("home", "../etc/passwd")
        with self.assertRaises(ValueError):
            sp.validate_run_date("2026-13-99")

    def test_config_bad_ordering_rejected(self):
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as home:
            home = _P(home)
            (home / "config").mkdir(parents=True, exist_ok=True)
            (home / "config" / "simulation.toml").write_text(
                '[size_tiers]\nsmall=0.5\nmedium=0.2\nlarge=0.9\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                sp.load_simulation_config(home)

    def test_none_tier_add_collapses_to_hold_no_execute_zero(self):
        out = sp.resolve_sized_direction("add", "none", 5000.0)
        self.assertEqual("hold", out["direction"])
        self.assertEqual("none", out["size_tier"])
        self.assertEqual(0.0, out["validated_amount"])


if __name__ == "__main__":
    unittest.main()
