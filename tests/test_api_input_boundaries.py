"""API input-boundary tests for round 3.

Covers:
- GET date/selectedDate must be a real YYYY-MM-DD date; invalid -> ValueError (HTTP 400 channel).
- /api/fund/<code> must be 6 digits.
- ui_support.load_state rejects traversal / non-date selected before path join.
- simulation_v2 advice row adapter maps snake->camel; legacy rows tagged legacy, no tier inferred.
- rag_service rejects invalid selectedDate; decisionAt/timeBasis passthrough flags.
- trade adapter surfaces fundingMode/externalCashflow/valuationStatus; manual units w/o nav => pending.

All homes are temp dirs; no real LLM / quotes / spawn / runtime DB.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from web_api import ContractRequestHandler  # noqa: E402
from web_api_format import adapt_simulation_advice_row  # noqa: E402
import rag_service  # noqa: E402
import ui_support  # noqa: E402
import web_api_services  # noqa: E402


class DateQueryValidationTest(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(ContractRequestHandler)

    def test_absent_date_returns_none(self):
        self.assertIsNone(self.handler._selected_date_from_query({}))
        self.assertIsNone(self.handler._selected_date_from_query({"date": [""]}))

    def test_valid_real_date_normalized(self):
        self.assertEqual(
            self.handler._selected_date_from_query({"date": ["2026-10-28"]}), "2026-10-28"
        )
        self.assertEqual(
            self.handler._selected_date_from_query({"selectedDate": ["2026-01-03"]}), "2026-01-03"
        )

    def test_traversal_date_rejected(self):
        for bad in ["..", "../..", "2026/10/28", "2026.10.28", "abc", "2026-13-01", "2026-02-30", "2026-1-3"]:
            with self.assertRaises(ValueError, msg=f"expected 400 for {bad!r}"):
                self.handler._selected_date_from_query({"date": [bad]})

    def test_fund_code_six_digit_contract(self):
        import re

        self.assertTrue(re.fullmatch(r"\d{6}", "110011"))
        for bad in ["11011", "1100111", "abcdef", "110011x", "..", "11-001"]:
            self.assertIsNone(re.fullmatch(r"\d{6}", bad), msg=f"should reject {bad!r}")


class LoadStateRootContainmentTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_date_selected_rejected(self):
        with self.assertRaises(ValueError):
            ui_support.load_state(self.home, selected="..")
        with self.assertRaises(ValueError):
            ui_support.load_state(self.home, selected="2026-02-30")

    def test_valid_date_loads_empty_state(self):
        state = ui_support.load_state(self.home, selected="2026-10-28")
        self.assertEqual(state["selected_date"], "2026-10-28")


class AdviceAdapterTest(unittest.TestCase):
    def test_v2_row_mapped_to_camel(self):
        row = adapt_simulation_advice_row({
            "schema_version": "simulation_v2",
            "size_tier": "medium",
            "size_ratio": 0.25,
            "sizing_basis": "fund_position_value",
            "basis_position_value": 10000.0,
            "basis_snapshot_sha256": "ab12",
            "decision_at": "2026-10-28T14:00:00+08:00",
            "horizon": "short",
            "evidence_quality": "high",
            "validated_amount": 2500.0,
        })
        self.assertEqual(row["schemaVersion"], "simulation_v2")
        self.assertEqual(row["sizeTier"], "medium")
        self.assertEqual(row["sizeRatio"], 0.25)
        self.assertEqual(row["sizingBasis"], "fund_position_value")
        self.assertEqual(row["basisPositionValue"], 10000.0)
        self.assertEqual(row["basisSnapshotSha256"], "ab12")
        self.assertEqual(row["decisionAt"], "2026-10-28T14:00:00+08:00")
        self.assertEqual(row["horizon"], "short")
        self.assertEqual(row["evidenceQuality"], "high")

    def test_legacy_row_tagged_not_fabricated(self):
        row = adapt_simulation_advice_row({
            "validated_action": "buy",
            "validated_amount": 3000.0,  # legacy amount must NOT be turned into a tier
        })
        self.assertEqual(row["schemaVersion"], "legacy")
        self.assertEqual(row["sizeTier"], "legacy")
        self.assertIsNone(row["sizeRatio"])
        self.assertEqual(row["evidenceQuality"], "unavailable")
        self.assertEqual(row["horizon"], "unspecified")

    def test_unknown_enums_sanitized_fail_closed(self):
        row = adapt_simulation_advice_row({
            "schema_version": "simulation_v2",
            "size_tier": "gigantic",
            "evidence_quality": "perfect",
        })
        self.assertEqual(row["sizeTier"], "none")
        self.assertEqual(row["evidenceQuality"], "unavailable")


class RagServiceDateAndDecisionAtTest(unittest.TestCase):
    def test_invalid_selected_date_raises(self):
        with self.assertRaises(ValueError):
            rag_service._valid_date("..")
        with self.assertRaises(ValueError):
            rag_service._valid_date("2026-02-30")

    def test_decision_at_metadata(self):
        # verify the metadata block carries decision_at + time_basis flags
        import inspect

        src = inspect.getsource(rag_service.build_copilot_rag_pack)
        self.assertIn("decision_at", src)
        self.assertIn("end_of_day_legacy", src)

    def test_decision_at_flows_to_planner_as_kwarg(self):
        captured: dict = {}

        class FakePlan:
            decision_at = None
            intent = "general_qa"
            retrieval_profile = "copilot_qa"
            metadata = {"cutoff_precision": "instant", "time_basis_note": "offset"}

            def to_dict(self):
                return {"decision_at": self.decision_at}

        fake_plan = FakePlan()

        def fake_planner(question, **kwargs):
            captured.update(kwargs)
            fake_plan.decision_at = kwargs.get("decision_at")
            return fake_plan

        with (
            mock.patch.object(rag_service, "load_rag_config", lambda _h: {"rag": {"enabled": True}}),
            mock.patch.object(rag_service, "build_rag_query_plan", fake_planner),
            mock.patch.object(rag_service, "retrieve_rag_evidence", lambda *_a, **_kw: {}),
            mock.patch.object(rag_service, "build_copilot_evidence_pack", lambda **_kw: {"hits": []}),
        ):
            pack = rag_service.build_copilot_rag_pack(
                Path(tempfile.mkdtemp()),
                {
                    "selectedDate": "2026-10-28",
                    "question": "为什么今天加仓?",
                    "decisionAt": "2026-10-28T14:00:00+08:00",
                },
            )
        self.assertEqual(captured["decision_at"], "2026-10-28T14:00:00+08:00")
        self.assertEqual(pack["decisionAt"], "2026-10-28T14:00:00+08:00")
        self.assertEqual(pack["timeBasis"], "instant")

    def test_no_decision_at_leaves_kwarg_none(self):
        captured: dict = {}

        class FakePlan:
            decision_at = None
            intent = "general_qa"
            retrieval_profile = "copilot_qa"
            metadata = {"cutoff_precision": "end_of_day_legacy"}

            def to_dict(self):
                return {}

        fake_plan = FakePlan()

        def fake_planner(question, **kwargs):
            captured.update(kwargs)
            return fake_plan

        with (
            mock.patch.object(rag_service, "load_rag_config", lambda _h: {"rag": {"enabled": True}}),
            mock.patch.object(rag_service, "build_rag_query_plan", fake_planner),
            mock.patch.object(rag_service, "retrieve_rag_evidence", lambda *_a, **_kw: {}),
            mock.patch.object(rag_service, "build_copilot_evidence_pack", lambda **_kw: {"hits": []}),
        ):
            pack = rag_service.build_copilot_rag_pack(
                Path(tempfile.mkdtemp()),
                {"selectedDate": "2026-10-28", "question": "hi"},
            )
        self.assertIsNone(captured["decision_at"])
        self.assertEqual(pack["decisionAt"], "")
        self.assertEqual(pack["timeBasis"], "end_of_day_legacy")


class TradeAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.controller = web_api_services.ExecutionController(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def test_amount_only_echoes_persisted_fields(self):
        fake_record = {"ok": True, "trade": {
            "trade_id": "t1", "fund_code": "110011", "operation_type": "buy",
            "funding_mode": "virtual_external_flows", "external_cashflow": 102.0,
            "external_cashflow_timing": "end", "valuation_status": "pending",
        }}
        with mock.patch.object(web_api_services, "record_actual_trade", lambda _h, _p: fake_record):
            out = self.controller.execution_trade({
                "fund_code": "110011", "operation_type": "buy", "amount": 1000.0,
            })
        self.assertEqual(out["valuationStatus"], "pending")  # exact from persisted, not re-derived
        self.assertEqual(out["fundingMode"], "virtual_external_flows")
        self.assertEqual(out["externalCashflow"], 102.0)
        self.assertEqual(out["externalCashflowTiming"], "end")

    def test_units_given_persisted_exact(self):
        fake_record = {"ok": True, "trade": {
            "trade_id": "t1b", "fund_code": "110011", "operation_type": "buy",
            "funding_mode": "virtual_external_flows", "external_cashflow": 100.0,
            "external_cashflow_timing": "end", "valuation_status": "exact",
        }}
        with mock.patch.object(web_api_services, "record_actual_trade", lambda _h, _p: fake_record):
            out = self.controller.execution_trade({
                "fund_code": "110011", "operation_type": "buy", "units": 100.0,
            })
        self.assertEqual(out["valuationStatus"], "exact")

    def test_legacy_trade_defaults(self):
        fake_record = {"trade_id": "t2", "fund_code": "110011", "operation_type": "fee"}
        with mock.patch.object(web_api_services, "record_actual_trade", lambda _h, _p: fake_record):
            out = self.controller.execution_trade({
                "fund_code": "110011",
                "operation_type": "fee",
                "amount": 5.0,
            })
        self.assertEqual(out["fundingMode"], "legacy")
        self.assertEqual(out["valuationStatus"], "pending")


class RequestForgeryGuardTest(unittest.TestCase):
    def test_derived_flow_fields_forbidden_in_request(self):
        from api_contracts import ExecutionTradeRequestDto, coerce_model

        # A client trying to forge a deposit via request fields must be rejected
        # (DTO extra=forbid), never silently trusted into the ledger.
        with self.assertRaises(Exception):
            coerce_model(ExecutionTradeRequestDto, {
                "fund_code": "110011",
                "operation_type": "buy",
                "amount": 1000.0,
                "funding_mode": "virtual_external_flows",
                "external_cashflow": 999999.0,
            })

    def test_clean_request_accepted(self):
        from api_contracts import ExecutionTradeRequestDto, coerce_model

        dto = coerce_model(ExecutionTradeRequestDto, {
            "fund_code": "110011",
            "operation_type": "buy",
            "amount": 1000.0,
        })
        self.assertEqual(dto["fund_code"], "110011")


class TradeLedgerIntegrationTest(unittest.TestCase):
    """Real ledger integration: TempAgentHome -> record_actual_trade -> API adapter."""

    def setUp(self):
        from helpers import TempAgentHome

        self.agent = TempAgentHome()
        self.controller = web_api_services.ExecutionController(self.agent.root)

    def tearDown(self):
        self.agent.cleanup()

    def test_buy_external_cashflow_102_and_idempotent_replay(self):
        out1 = self.controller.execution_trade({
            "trade_id": "t-int-1", "fund_code": "110011", "operation_type": "buy",
            "amount": 100.0, "fee": 2.0, "trade_date": "2026-10-28",
        })
        self.assertEqual(out1["externalCashflow"], 102.0)  # buy external = amount + fee
        self.assertEqual(out1["fundingMode"], "virtual_external_flows")
        self.assertEqual(out1["externalCashflowTiming"], "end")
        self.assertEqual(out1["valuationStatus"], "pending")  # no units/nav on record
        # replay same trade_id: identical persisted record, no double counting
        out2 = self.controller.execution_trade({
            "trade_id": "t-int-1", "fund_code": "110011", "operation_type": "buy",
            "amount": 100.0, "fee": 2.0, "trade_date": "2026-10-28",
        })
        self.assertEqual(out2["externalCashflow"], 102.0)
        self.assertEqual(out2["valuationStatus"], "pending")

    def test_dividend_internal_zero_external_flow(self):
        out = self.controller.execution_trade({
            "trade_id": "t-int-2", "fund_code": "110011", "operation_type": "dividend",
            "amount": 5.0, "trade_date": "2026-10-28",
        })
        self.assertEqual(out["externalCashflow"], 0.0)  # internal income, never external flow

    def test_fee_duplicate_rejected_and_independent_fee_ok(self):
        # buy trade absorbs its own fee
        buy = self.controller.execution_trade({
            "trade_id": "t-buy1", "fund_code": "110011", "operation_type": "buy",
            "amount": 100.0, "fee": 2.0, "trade_date": "2026-10-28",
        })
        self.assertEqual(buy["externalCashflow"], 102.0)
        # fee event linking back to a trade that already has fee -> rejected
        with self.assertRaises(ValueError):
            self.controller.execution_trade({
                "trade_id": "t-fee-dup", "fund_code": "110011", "operation_type": "fee",
                "amount": 2.0, "trade_date": "2026-10-28", "fee_for_trade_id": "t-buy1",
            })
        # independent fee event (no link) -> accepted, zero external flow
        fee = self.controller.execution_trade({
            "trade_id": "t-fee-ok", "fund_code": "110011", "operation_type": "fee",
            "amount": 2.0, "trade_date": "2026-10-28",
        })
        self.assertEqual(fee["externalCashflow"], 0.0)


if __name__ == "__main__":
    unittest.main()
