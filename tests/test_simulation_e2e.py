from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from promoted_advice_guardrails import build_candidate  # noqa: E402
import simulation_policy as sp  # noqa: E402

STRATEGY = {
    "tactical": {"default_cap_value": 1_000_000.0, "max_add_amount": 500.0, "max_reduce_amount": 500.0,
                 "max_actions_per_day": 3},
    "core_dca": {"amount_per_fund": 0.0},
    "portfolio": {"allow_full_exit": True, "cash_hub_floor": 0.0, "risk_profile": "x",
                  "daily_max_trade_amount": 1e9, "daily_max_gross_trade_amount": 1e9,
                  "daily_max_net_buy_amount": 1e9},
}
RATIOS = sp.DEFAULT_SIZE_RATIOS


class SimulationV2RuntimeTests(unittest.TestCase):
    def test_v2_amount_is_basis_times_tier_not_capped_not_100_rounded(self):
        fund = {"fund_code": "F1", "fund_name": "F1", "current_value": 10033.0, "cap_value": 1_000_000.0, "allow_trade": True}
        # LLM 只给方向+tier，不给金额
        cand = build_candidate(fund, {"action": "add", "size_tier": "medium", "evidence_quality": "medium"},
                               strategy=STRATEGY, constraint={}, basis_value=10033.0, size_ratios=RATIOS)
        self.assertIsNotNone(cand)
        # 10033*0.25 = 2508.25：不被 max_add(500) 截断，也不被 100 粒度取整
        self.assertEqual(2508.25, cand["amount"])
        self.assertNotIn("strategy_amount_cap", cand["policy_rule_hits"])

    def test_zero_basis_v2_add_gated(self):
        fund = {"fund_code": "F2", "fund_name": "F2", "current_value": 0.0, "cap_value": 1_000_000.0, "allow_trade": True}
        cand = build_candidate(fund, {"action": "add", "size_tier": "small"},
                               strategy=STRATEGY, constraint={}, basis_value=0.0, size_ratios=RATIOS)
        self.assertIsNone(cand)  # 零仓 add 无 room -> hold，不"执行 0"

    def test_reduce_v2_bounded_by_sellable(self):
        fund = {"fund_code": "F3", "fund_name": "F3", "current_value": 4000.0, "cap_value": 1_000_000.0, "allow_trade": True}
        cand = build_candidate(fund, {"action": "reduce", "size_tier": "large", "evidence_quality": "medium"},
                               strategy=STRATEGY, constraint={"available_to_sell": 2000.0},
                               basis_value=4000.0, size_ratios=RATIOS)
        self.assertIsNotNone(cand)
        # 4000*0.5=2000，受可卖额约束=2000（非负/可卖保留）
        self.assertEqual(2000.0, cand["amount"])

    def test_unavailable_evidence_blocks_v2_trade(self):
        fund = {"fund_code": "F9", "fund_name": "F9", "current_value": 1000.0, "cap_value": 1_000_000.0, "allow_trade": True}
        cand = build_candidate(fund, {"action": "add", "size_tier": "medium", "evidence_quality": "unavailable"},
                               strategy=STRATEGY, constraint={}, basis_value=1000.0, size_ratios=RATIOS)
        self.assertIsNone(cand)  # 真实无证据/invalid enum -> 不可执行

    def test_low_evidence_still_tradable_with_risk(self):
        fund = {"fund_code": "F8", "fund_name": "F8", "current_value": 1000.0, "cap_value": 1_000_000.0, "allow_trade": True}
        cand = build_candidate(fund, {"action": "add", "size_tier": "small", "evidence_quality": "low"},
                               strategy=STRATEGY, constraint={}, basis_value=1000.0, size_ratios=RATIOS)
        self.assertIsNotNone(cand)

    def test_basis_freeze_written_and_reused(self):
        with tempfile.TemporaryDirectory() as home:
            pf = {"as_of_date": "2026-06-01", "funds": [{"fund_code": "F1", "current_value": 10033.0}]}
            b1 = sp.get_or_freeze_basis(home, "2026-06-01", pf, write=True, decision_at="2026-06-01T09:30:00+08:00")
            self.assertEqual("2026-06-01T09:30:00+08:00", b1["decision_at"])
            self.assertTrue(sp.decision_basis_path(home, "2026-06-01").exists())
            # 漂移后组合复用旧 basis
            drifted = {"as_of_date": "2026-06-01", "funds": [{"fund_code": "F1", "current_value": 99999.0}]}
            b2 = sp.get_or_freeze_basis(home, "2026-06-01", drifted, write=True)
            self.assertEqual(10033.0, sp.basis_value_for(b2, "F1"))


if __name__ == "__main__":
    unittest.main()
