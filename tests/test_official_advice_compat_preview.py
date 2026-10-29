from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DATE = "2026-06-01"
TICKET_GENERATED_AT = "2026-06-01T21:30:00+08:00"
PACK_GENERATED_AT = "2026-06-01T21:35:00+08:00"
DEBATE_GENERATED_AT = "2026-06-01T21:40:00+08:00"
PREVIEW_GENERATED_AT = "2026-06-01T22:00:00+08:00"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from artifact_boundary import BoundaryViolation, assert_refactor_write_allowed
from build_action_ticket_shadow import run_builder as run_action_ticket_builder
from build_layered_retrieval_pack import run_builder as run_retrieval_pack_builder
from build_official_advice_compat_preview import (
    CompatPreviewError,
    build_committee_decision,
    build_final_decision,
    preview_path,
    run_builder as run_compat_preview_builder,
)
from action_debate_graph import run_debate_graph
from helpers import TempAgentHome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_repo_json(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


class OfficialAdviceCompatPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()

    def tearDown(self) -> None:
        self.agent.cleanup()

    def test_promoted_action_former_proposal_supplies_tactical_action_and_amount(self) -> None:
        ticket = {
            "ticket_id": "ticket:2026-05-22:F1:hold:001",
            "fund_code": "F1",
            "fund_name": "Fund 1",
            "role": "tactical",
            "action_verb": "hold",
            "validated_amount": 0.0,
            "ticket_status": "shadow_only",
            "hard_guardrail_results": [],
        }
        debate = {
            "node_outputs": {
                "action_former": {"action": "add", "amount": 250.0, "reason": "promoted evidence"},
                "ticket_writer": {"proposed_ticket_patch": {"confidence": 0.7}},
            }
        }

        decision = build_committee_decision(ticket, {}, debate, 1)

        self.assertEqual("add", decision["proposed_action"])
        self.assertEqual(250.0, decision["suggest_amount"])
        self.assertEqual("action_former", decision["proposed_amount_source"])
        self.assertTrue(decision["execution_eligible"])

    def test_debate_level_degraded_or_blocked_forces_hold_end_to_end(self) -> None:
        # P1 回归：原 ticket 仍是 shadow_only 时，debate/former 自身的 degraded/blocked
        # 也必须否决交易并在 final decision 强制 hold（修复前软降级照样买）。
        def make(ticket_status, debate_status, former_status):
            ticket = {
                "ticket_id": "t1", "fund_code": "F1", "fund_name": "Fund 1", "role": "tactical",
                "action_verb": "hold", "validated_amount": 0.0, "ticket_status": ticket_status,
                "hard_guardrail_results": [],
            }
            debate = {
                "ticket_status": debate_status,
                "node_outputs": {
                    "action_former": {"action": "add", "amount": 250.0, "target_status": former_status},
                    "hard_guardrail_check": {"result": "pass", "block_count": 0},
                },
            }
            return ticket, debate

        for ticket_status, debate_status, former_status in [
            ("shadow_only", "degraded", "degraded"),   # referee 正常降级
            ("shadow_only", "blocked", "blocked"),     # former/硬门 block
            ("shadow_only", None, "degraded"),         # 仅 former 降级
            # P1 反例：referee 已 degrade，former LLM 报 shadow_only（抬权），仍须保持 hold。
            ("shadow_only", "degraded", "shadow_only"),
        ]:
            ticket, debate = make(ticket_status, debate_status, former_status)
            cd = build_committee_decision(ticket, {}, debate, 1)
            fd = build_final_decision(cd, ticket, {}, debate)
            self.assertTrue(cd["risk_veto"], (ticket_status, debate_status, former_status))
            self.assertFalse(cd["execution_eligible"])
            self.assertEqual("hold", fd["action"])

    def copy_real_inputs(self) -> None:
        # 合成最小自包含 fixture（不拷用户真实 db）：与 promoted chain 同构。
        self.agent.write_json("config/benchmark_mappings.json", {"fund_benchmarks": {}})
        portfolio = {
            "portfolio_name": "test",
            "as_of_date": REPORT_DATE,
            "total_value": 1250.0,
            "funds": [
                {"fund_code": "DCA1", "fund_name": "Core DCA", "role": "core_dca", "style_group": "core",
                 "current_value": 100.0, "allow_trade": True, "fixed_daily_buy_amount": 25.0,
                 "holding_units": 100.0, "last_valuation_nav": 1.0, "units_source": "stored"},
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub", "style_group": "cash",
                 "current_value": 500.0, "allow_trade": True, "holding_units": 500.0,
                 "last_valuation_nav": 1.0, "units_source": "stored"},
                {"fund_code": "TADD", "fund_name": "Add Target", "role": "tactical", "style_group": "growth_rotation",
                 "current_value": 200.0, "cap_value": 800.0, "allow_trade": True,
                 "holding_units": 100.0, "last_valuation_nav": 2.0, "units_source": "stored"},
                {"fund_code": "TRED", "fund_name": "Reduce Target", "role": "tactical", "style_group": "industrial_metal",
                 "current_value": 250.0, "cap_value": 800.0, "allow_trade": True,
                 "holding_units": 125.0, "last_valuation_nav": 2.0, "units_source": "stored"},
            ],
        }
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json(f"db/portfolio_state/snapshots/{REPORT_DATE}.json", portfolio)
        self.agent.write_json(f"db/daily_scores/{REPORT_DATE}.json", {
            "report_date": REPORT_DATE, "generated_at": TICKET_GENERATED_AT,
            "funds": [
                {"code": "TADD", "name": "Add Target", "score": 88.0, "action": "add", "confidence": 0.84, "reasons": ["strong"], "risk_flags": []},
                {"code": "TRED", "name": "Reduce Target", "score": 24.0, "action": "avoid", "confidence": 0.8, "reasons": ["weak"], "risk_flags": ["drawdown"]},
            ],
        })
        self.agent.write_json(f"db/llm_context/{REPORT_DATE}.json", {
            "analysis_date": REPORT_DATE, "generated_at": TICKET_GENERATED_AT,
            "funds": [
                {"fund_code": "DCA1", "fund_name": "Core DCA", "role": "core_dca"},
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub"},
                {"fund_code": "TADD", "fund_name": "Add Target", "role": "tactical",
                 "quote": {"day_change_pct": 1.2, "as_of_date": "2026-05-29"},
                 "recent_news": [{"title": "pos", "summary": "pos", "impact": "positive", "published_at": TICKET_GENERATED_AT}],
                 "intraday_proxy": {"change_pct": 2.1, "trade_date": REPORT_DATE}},
                {"fund_code": "TRED", "fund_name": "Reduce Target", "role": "tactical",
                 "quote": {"day_change_pct": -2.5, "as_of_date": "2026-05-29"},
                 "recent_news": [{"title": "neg", "summary": "neg", "impact": "negative", "published_at": TICKET_GENERATED_AT}],
                 "intraday_proxy": {"change_pct": -1.7, "trade_date": REPORT_DATE}},
            ],
            "evidence_items": [],
        })
        self.agent.write_json(f"db/evidence_index/{REPORT_DATE}.json", {"items": []})
        # 最小官方 validated_advice 基线（preview 据此 replay/compare；不拷用户 db）。
        self.agent.write_json(f"db/validated_advice/{REPORT_DATE}.json", {
            "report_date": REPORT_DATE, "generated_at": TICKET_GENERATED_AT,
            "tactical_actions": [], "dca_actions": [], "hold_actions": [],
            "market_view": {"summary": "synthetic baseline"},
        })

    def build_shadow_chain(self) -> None:
        self.copy_real_inputs()
        run_action_ticket_builder(self.agent.root, REPORT_DATE, generated_at=TICKET_GENERATED_AT, source_mode="native")
        run_retrieval_pack_builder(self.agent.root, REPORT_DATE, generated_at=PACK_GENERATED_AT, source_mode="native")
        run_debate_graph(self.agent.root, REPORT_DATE, generated_at=DEBATE_GENERATED_AT)

    def test_preview_builds_official_compatible_shapes_without_official_mutation(self) -> None:
        self.build_shadow_chain()
        validated_path = self.agent.root / "db" / "validated_advice" / f"{REPORT_DATE}.json"
        portfolio_path = self.agent.root / "db" / "portfolio_state" / "current.json"
        before_validated = _sha256(validated_path)
        before_portfolio = _sha256(portfolio_path)

        path, payload = run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        self.assertEqual(preview_path(self.agent.root, REPORT_DATE), path)
        self.assertEqual("official_advice_compat_preview.v1", payload["schema_version"])
        self.assertEqual("shadow_only", payload["write_scope"])
        self.assertTrue(payload["non_executable"])
        self.assertTrue(payload["summary"]["official_shape_compatible"])
        self.assertFalse(payload["summary"]["fallback_switch_active"])
        self.assertFalse(payload["summary"]["promotion_ready"])
        self.assertEqual([], payload["summary"]["official_paths_written"])
        self.assertGreaterEqual(payload["summary"]["committee_decision_count"], 1)
        self.assertEqual(payload["summary"]["committee_decision_count"], len(payload["committee_decision_bundle_preview"]["fund_decisions"]))
        self.assertEqual(len(payload["final_advice_preview"]["fund_decisions"]), len(payload["committee_decision_bundle_preview"]["fund_decisions"]))
        self.assertFalse(payload["committee_decision_bundle_preview"]["execution_eligible"])
        section_items = (
            payload["validated_action_sections_preview"]["tactical_actions"]
            + payload["validated_action_sections_preview"]["dca_actions"]
            + payload["validated_action_sections_preview"]["hold_actions"]
        )
        self.assertTrue(section_items)
        for item in section_items:
            self.assertIn("cash_impact", item)
            self.assertIn("allocation_impact", item)
            self.assertIn("source_signal_ids", item)
            self.assertIn("opposing_signal_ids", item)
        self.assertEqual(before_validated, _sha256(validated_path))
        self.assertEqual(before_portfolio, _sha256(portfolio_path))
        with self.assertRaises(BoundaryViolation):
            assert_refactor_write_allowed(validated_path, payload, self.agent.root)

    def test_golden_slice_fund_maps_to_final_advice_decision(self) -> None:
        self.build_shadow_chain()

        _path, payload = run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        decisions = {
            item["fund_code"]: item
            for item in payload["final_advice_preview"]["fund_decisions"]
        }
        golden = decisions["DCA1"]
        self.assertEqual("scheduled_dca", golden["action"])
        self.assertEqual(25.0, golden["suggest_amount"])

    def test_source_hash_mismatch_rejects_preview(self) -> None:
        self.build_shadow_chain()
        ticket_path = self.agent.root / "db" / "action_tickets" / f"{REPORT_DATE}.json"
        ticket_payload = json.loads(ticket_path.read_text(encoding="utf-8"))
        ticket_payload["tickets"][0]["confidence"] = 0.99
        ticket_path.write_text(json.dumps(ticket_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with self.assertRaises(CompatPreviewError) as ctx:
            run_compat_preview_builder(self.agent.root, REPORT_DATE, generated_at=PREVIEW_GENERATED_AT)

        self.assertIn("hash mismatch", str(ctx.exception))

    def test_cli_outputs_summary_json(self) -> None:
        self.build_shadow_chain()

        completed = self.agent.run_script(
            "build_official_advice_compat_preview.py",
            "--date",
            REPORT_DATE,
            "--generated-at",
            PREVIEW_GENERATED_AT,
            "--format",
            "json",
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(
            f"db/refactor_shadow_runs/{REPORT_DATE}__official_advice_compat_preview/official_advice_compat_preview.json",
            payload["path"],
        )
        self.assertTrue(payload["summary"]["official_shape_compatible"])


if __name__ == "__main__":
    unittest.main()
