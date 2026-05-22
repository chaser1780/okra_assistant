from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from execution_sync import apply_reconciliation, parse_alipay_screenshot_upload, preview_reconciliation, record_actual_trade, record_conversion, update_pending_confirmations
from common import lock_path
from helpers import TempAgentHome
from long_memory_store import build_fund_memory
from trade_lifecycle import effective_trade_date, resolve_trade_lifecycle


class ExecutionSyncTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()
        portfolio = {
            "portfolio_name": "测试组合",
            "as_of_date": "2026-05-04",
            "total_value": 3000.0,
            "holding_pnl": 0.0,
            "funds": [
                {
                    "fund_code": "017641",
                    "fund_name": "标普500指数QDII",
                    "role": "core_dca",
                    "style_group": "sp500_core",
                    "current_value": 1000.0,
                    "holding_units": 500.0,
                    "cost_basis_value": 1000.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "redeem_settlement_days": 3,
                    "allow_trade": True,
                },
                {
                    "fund_code": "025857",
                    "fund_name": "电网设备C",
                    "role": "tactical",
                    "style_group": "grid_equipment",
                    "current_value": 1000.0,
                    "holding_units": 1000.0,
                    "cost_basis_value": 1000.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": True,
                },
                {
                    "fund_code": "017704",
                    "fund_name": "现金存单",
                    "role": "cash_hub",
                    "style_group": "cash_buffer",
                    "current_value": 1000.0,
                    "holding_units": 1000.0,
                    "cost_basis_value": 1000.0,
                    "holding_pnl": 0.0,
                    "holding_return_pct": 0.0,
                    "allow_trade": True,
                },
            ],
        }
        self.agent.write_json("config/portfolio.json", portfolio)
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json(
            "db/validated_advice/2026-05-04.json",
            {
                "tactical_actions": [
                    {
                        "suggestion_id": "s1",
                        "fund_code": "025857",
                        "fund_name": "电网设备C",
                        "validated_action": "add",
                        "validated_amount": 500.0,
                    }
                ],
                "dca_actions": [],
                "hold_actions": [],
            },
        )

    def tearDown(self):
        self.agent.cleanup()

    def test_trade_lifecycle_cutoff_and_weekend(self):
        self.assertEqual(effective_trade_date("2026-05-04", "14:59"), "2026-05-04")
        self.assertEqual(effective_trade_date("2026-05-04", "15:01"), "2026-05-05")
        self.assertEqual(effective_trade_date("2026-05-09", "10:00"), "2026-05-11")
        lifecycle = resolve_trade_lifecycle(self.agent.root, fund_code="017641", operation_type="buy", trade_date="2026-05-04", trade_time="15:01")
        self.assertEqual(lifecycle["effective_trade_date"], "2026-05-05")
        self.assertGreaterEqual(lifecycle["confirm_days"], 1)

    def test_record_actual_trade_writes_execution_only_and_pending(self):
        result = record_actual_trade(
            self.agent.root,
            {
                "trade_date": "2026-05-04",
                "trade_time": "14:50",
                "fund_code": "025857",
                "fund_name": "电网设备C",
                "operation_type": "buy",
                "amount": 300,
                "linked_suggestion_id": "s1",
                "linked_advice_date": "2026-05-04",
            },
        )
        self.assertTrue(result["ok"])
        actual = json.loads((self.agent.root / "db/execution_sync/actual_trades/2026-05-04.json").read_text(encoding="utf-8"))
        pending = json.loads((self.agent.root / "db/execution_sync/pending_confirmations.json").read_text(encoding="utf-8"))
        self.assertEqual(actual["items"][0]["execution_deviation"]["type"], "partial_execution")
        self.assertFalse(actual["items"][0]["execution_deviation"]["affects_advice_accuracy"])
        self.assertEqual(len(pending["items"]), 1)
        self.assertFalse(lock_path(self.agent.root, "execution_sync").exists())

    def test_record_conversion_uses_single_group_id(self):
        result = record_conversion(
            self.agent.root,
            {
                "trade_date": "2026-05-04",
                "out_fund_code": "025857",
                "out_fund_name": "电网设备C",
                "in_fund_code": "017641",
                "in_fund_name": "标普500指数QDII",
                "out_amount": 200,
                "in_amount": 198,
                "fee": 2,
            },
        )
        conversion = result["conversion"]
        self.assertEqual(conversion["operation_type"], "convert")
        self.assertTrue(conversion["conversion_id"])
        actual = json.loads((self.agent.root / "db/execution_sync/actual_trades/2026-05-04.json").read_text(encoding="utf-8"))
        self.assertEqual(actual["items"][0]["conversion_id"], conversion["conversion_id"])
        self.assertFalse(lock_path(self.agent.root, "execution_sync").exists())

    def test_reconciliation_preview_and_apply_updates_portfolio(self):
        preview = preview_reconciliation(
            self.agent.root,
            [
                {
                    "fund_code": "025857",
                    "fund_name": "电网设备C",
                    "current_value": 1200,
                    "holding_units": 1100,
                    "cost_basis_value": 1000,
                    "holding_pnl": 200,
                    "holding_return_pct": 20,
                }
            ],
            snapshot_date="2026-05-05",
            source="manual_position_snapshot",
        )
        self.assertTrue(preview["apply_ready"])
        result = apply_reconciliation(self.agent.root, preview, drop_missing=False)
        self.assertTrue(result["ok"])
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1200.0)
        self.assertEqual(fund["holding_units"], 1100.0)
        self.assertFalse(lock_path(self.agent.root, "portfolio_state").exists())

    def test_reconciliation_replace_zeros_missing_holdings(self):
        preview = preview_reconciliation(
            self.agent.root,
            [
                {
                    "fund_code": "025857",
                    "fund_name": "电网设备C",
                    "current_value": 1200,
                    "holding_units": 1100,
                    "cost_basis_value": 1000,
                    "holding_pnl": 200,
                    "holding_return_pct": 20,
                }
            ],
            snapshot_date="2026-05-05",
            source="alipay_screenshot",
        )
        result = apply_reconciliation(self.agent.root, preview, drop_missing=True)
        self.assertTrue(result["ok"])
        self.assertIn("017641", result["dropped_missing_fund_codes"])
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        dropped = next(item for item in portfolio["funds"] if item["fund_code"] == "017641")
        self.assertEqual(dropped["current_value"], 0.0)

    def test_alipay_screenshot_upload_reports_vision_failure(self):
        with patch("sync_portfolio_from_screenshots.call_screenshot_vision", side_effect=RuntimeError("HTTP 502 from portfolio screenshot API")):
            result = parse_alipay_screenshot_upload(
                self.agent.root,
                {
                    "import_id": "alipay_test_fail",
                    "snapshot_date": "2026-05-05",
                    "files": [{"name": "page1.jpg", "data": "not-an-image"}],
                },
            )

        self.assertFalse(result["auto_parse_ok"])
        self.assertTrue(result["auto_parse_attempted"])
        self.assertIn("HTTP 502", result["auto_parse_error"])
        self.assertTrue(result["saved_files"])
        saved = Path(result["saved_files"][0])
        self.assertTrue(saved.exists())

    def test_alipay_screenshot_upload_uses_llm_vision_preview(self):
        extracted = {
            "items": [
                {
                    "display_name": "电网设备C",
                    "current_value": 1200,
                    "daily_pnl": 0,
                    "holding_pnl": 200,
                    "holding_return_pct": 20,
                    "page_index": 1,
                    "row_index": 1,
                }
            ],
            "warnings": [],
            "_transport_name": "direct",
        }
        with patch("sync_portfolio_from_screenshots.call_screenshot_vision", return_value=extracted):
            result = parse_alipay_screenshot_upload(
                self.agent.root,
                {
                    "import_id": "alipay_test_ok",
                    "snapshot_date": "2026-05-05",
                    "files": [{"name": "page1.jpg", "data": "not-an-image"}],
                },
            )

        self.assertTrue(result["auto_parse_ok"])
        self.assertTrue(result["auto_parse_attempted"])
        self.assertEqual(result["transport_name"], "direct")
        self.assertTrue(result["apply_ready"])
        self.assertEqual(result["matched_items"][0]["matched_fund_code"], "025857")

    def test_pending_settlement_updates_portfolio_once(self):
        recorded = record_actual_trade(
            self.agent.root,
            {
                "trade_id": "trade_once",
                "trade_date": "2026-05-04",
                "trade_time": "14:50",
                "fund_code": "025857",
                "fund_name": "电网设备C",
                "operation_type": "buy",
                "amount": 300,
                "confirm_date": "2026-05-05",
            },
        )
        first = update_pending_confirmations(self.agent.root, "2026-05-05")
        self.assertEqual(first["portfolio_applied_count"], 1)
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1300.0)
        event_path = self.agent.root / "db/execution_sync/settlement_events/trade_once.json"
        self.assertTrue(event_path.exists())
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertEqual(event["trade_id"], "trade_once")
        self.assertEqual(event["idempotency_key"], "trade_once")
        self.assertTrue(event["before_state_hash"])
        self.assertTrue(event["after_state_hash"])

        actual_path = Path(recorded["path"])
        actual_payload = json.loads(actual_path.read_text(encoding="utf-8"))
        for item in actual_payload["items"]:
            item.pop("portfolio_applied_at", None)
            item.pop("portfolio_applied_as_of", None)
        actual_path.write_text(json.dumps(actual_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.agent.write_json(
            "db/execution_sync/pending_confirmations.json",
            {"updated_at": "", "items": actual_payload["items"]},
        )
        second = update_pending_confirmations(self.agent.root, "2026-05-06")
        self.assertEqual(second["portfolio_applied_count"], 0)
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1300.0)

    def test_fund_memory_ignores_actual_trade_journal(self):
        record_actual_trade(
            self.agent.root,
            {
                "trade_date": "2026-05-04",
                "fund_code": "025857",
                "fund_name": "电网设备C",
                "operation_type": "buy",
                "amount": 300,
            },
        )
        payload = build_fund_memory(self.agent.root, write=False)
        self.assertTrue(payload.get("items", []))
        for item in payload.get("items", []):
            self.assertEqual(item["source"], "system_advice_reviews")
            self.assertFalse(item.get("evidence_refs"))


if __name__ == "__main__":
    unittest.main()
