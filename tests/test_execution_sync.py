from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import execution_sync as execution_sync_module
from execution_sync import apply_reconciliation, apply_saved_reconciliation, apply_settled_trade_to_portfolio, parse_alipay_screenshot_upload, preview_reconciliation, record_actual_trade, record_conversion, register_reconciliation_fund, sync_configured_simulated_dca, update_pending_confirmations
from common import lock_path, project_path
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

    def test_explicit_user_simulation_trade_updates_only_user_simulation_portfolio(self):
        result = record_actual_trade(
            self.agent.root,
            {
                "trade_id": "sim-buy-1",
                "trade_date": "2026-05-04",
                "fund_code": "025857",
                "fund_name": "电网设备C",
                "operation_type": "buy",
                "amount": 100,
                "simulation_track": "user_simulation",
                "simulation_status": "simulated",
            },
        )
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        target = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        cash = next(item for item in portfolio["funds"] if item["fund_code"] == "017704")
        pending = json.loads((self.agent.root / "db/execution_sync/pending_confirmations.json").read_text(encoding="utf-8"))
        replay = record_actual_trade(
            self.agent.root,
            {
                "trade_id": "sim-buy-1",
                "trade_date": "2026-05-04",
                "fund_code": "025857",
                "fund_name": "电网设备C",
                "operation_type": "buy",
                "amount": 100,
                "simulation_track": "user_simulation",
                "simulation_status": "simulated",
            },
        )
        self.assertTrue(result["trade"]["is_simulation"])
        self.assertEqual("simulated", result["trade"]["status"])
        self.assertEqual(1100.0, target["current_value"])
        # v2 virtual external flows: cash hub is never the funding source
        self.assertEqual(1000.0, cash["current_value"])
        self.assertEqual(100.0, portfolio["external_cashflow"])
        self.assertEqual("virtual_external_flows", portfolio["simulation_v2"]["funding_mode"])
        self.assertEqual([], pending["items"])
        self.assertTrue(result["trade"]["portfolio_simulation_event_path"])
        self.assertTrue(replay["idempotent_replay"])

    def test_configured_dca_materializes_once_on_trading_day(self):
        current_path = self.agent.root / "db/portfolio_state/current.json"
        portfolio = json.loads(current_path.read_text(encoding="utf-8"))
        portfolio["funds"][0]["fixed_daily_buy_amount"] = 25.0
        current_path.write_text(json.dumps(portfolio, ensure_ascii=False), encoding="utf-8")
        first = sync_configured_simulated_dca(self.agent.root, "2026-05-04")
        second = sync_configured_simulated_dca(self.agent.root, "2026-05-04")
        updated = json.loads(current_path.read_text(encoding="utf-8"))
        target = next(item for item in updated["funds"] if item["fund_code"] == "017641")
        cash = next(item for item in updated["funds"] if item["fund_code"] == "017704")
        self.assertEqual("ok", first["status"])
        self.assertFalse(first["created"][0]["idempotentReplay"])
        self.assertTrue(second["created"][0]["idempotentReplay"])
        self.assertEqual(1025.0, target["current_value"])
        # v2: old cash fund stays put; the 25 flows in as external money
        self.assertEqual(1000.0, cash["current_value"])

    def test_configured_dca_blocks_when_calendar_is_unavailable(self):
        self.agent.write_json("config/trading_calendar.json", {"holidays": [], "makeup_trading_days": []})

        result = sync_configured_simulated_dca(self.agent.root, "2026-05-04")

        self.assertEqual("blocked", result["status"])
        self.assertEqual("trading_calendar_unavailable", result["reason"])
        self.assertEqual("trading_calendar_unconfigured", result["calendar"]["reason"])
        self.assertEqual([], result["created"])

    def test_trade_record_id_is_idempotent_and_conflicts_across_dates(self):
        payload = {
            "trade_id": "trade-stable-1",
            "trade_date": "2026-05-04",
            "fund_code": "017641",
            "fund_name": "Index Fund",
            "operation_type": "buy",
            "amount": 100,
        }

        first = record_actual_trade(self.agent.root, payload)
        second = record_actual_trade(self.agent.root, payload)

        self.assertNotIn("idempotent_replay", first)
        self.assertTrue(second["idempotent_replay"])
        with self.assertRaisesRegex(ValueError, "trade_id already exists"):
            record_actual_trade(self.agent.root, {**payload, "trade_date": "2026-05-05"})

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
                    "daily_pnl": 12.34,
                }
            ],
            snapshot_date="2026-05-05",
            source="alipay_screenshot",
        )
        self.assertTrue(preview["apply_ready"])
        result = apply_reconciliation(self.agent.root, preview, drop_missing=False)
        self.assertTrue(result["ok"])
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1200.0)
        self.assertEqual(fund["holding_units"], 1100.0)
        self.assertEqual(fund["actual_daily_pnl"], 12.34)
        self.assertEqual(fund["actual_daily_pnl_date"], "2026-05-05")
        self.assertEqual(fund["actual_daily_pnl_source"], "alipay_screenshot")
        self.assertEqual(fund["last_real_position_date"], "2026-05-05")
        self.assertFalse(lock_path(self.agent.root, "portfolio_state").exists())

    def test_value_only_reconciliation_replaces_stale_units_from_last_nav(self):
        current_path = self.agent.root / "db/portfolio_state/current.json"
        portfolio = json.loads(current_path.read_text(encoding="utf-8"))
        portfolio["official_daily_pnl"] = 999.0
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        fund["official_daily_pnl"] = 999.0
        fund["official_daily_pnl_date"] = "2026-05-05"
        fund["official_daily_pnl_source"] = "official_nav_delta"
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        preview = preview_reconciliation(
            self.agent.root,
            [
                {
                    "fund_code": "025857",
                    "fund_name": "电网设备C",
                    "current_value": 1200.0,
                    "position_nav": 2.0,
                    "position_nav_date": "2026-05-04",
                }
            ],
            snapshot_date="2026-05-05",
            source="alipay_screenshot",
        )
        self.assertEqual(preview["matched_items"][0]["position_nav"], 2.0)
        apply_reconciliation(self.agent.root, preview, drop_missing=False)

        updated = json.loads(current_path.read_text(encoding="utf-8"))
        fund = next(item for item in updated["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["holding_units"], 600.0)
        self.assertEqual(fund["units_source"], "position_value_derived_from_official_nav")
        self.assertEqual(fund["holding_units_basis_nav"], 2.0)
        self.assertEqual(fund["holding_units_basis_nav_date"], "2026-05-04")
        self.assertNotIn("official_daily_pnl", fund)
        self.assertNotIn("official_daily_pnl", updated)

    def test_saved_reconciliation_rejects_tamper_stale_state_and_is_idempotent(self):
        preview = preview_reconciliation(
            self.agent.root,
            [{"fund_code": "025857", "fund_name": "Grid", "current_value": 1200, "holding_units": 1100}],
            snapshot_date="2026-05-05",
            source="manual_position_snapshot",
        )
        request = {
            "preview_sha256": preview["preview_sha256"],
            "expected_portfolio_state_sha256": preview["portfolio_state_sha256"],
        }

        first = apply_saved_reconciliation(self.agent.root, preview["reconcile_id"], **request)
        second = apply_saved_reconciliation(self.agent.root, preview["reconcile_id"], **request)

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])

        stale = preview_reconciliation(
            self.agent.root,
            [{"fund_code": "025857", "fund_name": "Grid", "current_value": 1300}],
            snapshot_date="2026-05-06",
            source="manual_position_snapshot",
        )
        current_path = self.agent.root / "db/portfolio_state/current.json"
        current = json.loads(current_path.read_text(encoding="utf-8"))
        current["funds"][0]["current_value"] = 9999
        self.agent.write_json("db/portfolio_state/current.json", current)
        with self.assertRaisesRegex(ValueError, "Portfolio state changed"):
            apply_saved_reconciliation(
                self.agent.root,
                stale["reconcile_id"],
                preview_sha256=stale["preview_sha256"],
                expected_portfolio_state_sha256=stale["portfolio_state_sha256"],
            )

        with self.assertRaisesRegex(ValueError, "preview hash mismatch"):
            apply_saved_reconciliation(
                self.agent.root,
                stale["reconcile_id"],
                preview_sha256="0" * 64,
                expected_portfolio_state_sha256=stale["portfolio_state_sha256"],
            )

    def test_reconciliation_apply_rejects_unmatched_screenshot_holdings(self):
        preview = {
            "source": "alipay_screenshot",
            "platform": "alipay",
            "snapshot_date": "2026-05-05",
            "matched_items": [
                {
                    "fund_code": "025857",
                    "fund_name": "鐢电綉璁惧C",
                    "current_value": 1200,
                    "holding_pnl": 200,
                    "holding_return_pct": 20,
                }
            ],
            "unmatched_detected": [{"display_name": "New Fund", "current_value": 100}],
            "apply_ready": False,
        }

        with self.assertRaises(ValueError):
            apply_reconciliation(self.agent.root, preview, drop_missing=False)

    def test_reconciliation_apply_rejects_unregistered_new_fund_code(self):
        preview = preview_reconciliation(
            self.agent.root,
            [{"fund_code": "012348", "fund_name": "New Fund", "current_value": 500}],
            snapshot_date="2026-05-05",
            source="manual_position_snapshot",
        )

        with self.assertRaisesRegex(ValueError, "confirmed and registered"):
            apply_reconciliation(self.agent.root, preview, drop_missing=False)

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
                    "files": [{"name": "page1.jpg", "data": base64.b64encode(b"not-an-image").decode("ascii")}],
                },
            )

        self.assertFalse(result["auto_parse_ok"])
        self.assertTrue(result["auto_parse_attempted"])
        self.assertIn("HTTP 502", result["auto_parse_error"])
        self.assertTrue(result["saved_files"])
        self.assertFalse(Path(result["saved_files"][0]).is_absolute())
        saved = project_path(self.agent.root, result["saved_files"][0])
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
                    "files": [{"name": "page1.jpg", "data": base64.b64encode(b"not-an-image").decode("ascii")}],
                },
            )

        self.assertTrue(result["auto_parse_ok"])
        self.assertTrue(result["auto_parse_attempted"])
        self.assertEqual(result["transport_name"], "direct")
        self.assertTrue(result["apply_ready"])
        self.assertEqual(result["matched_items"][0]["matched_fund_code"], "025857")
        self.assertRegex(result["portfolio_state_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["preview_sha256"], r"^[0-9a-f]{64}$")

        applied = apply_saved_reconciliation(
            self.agent.root,
            result["reconcile_id"],
            preview_sha256=result["preview_sha256"],
            expected_portfolio_state_sha256=result["portfolio_state_sha256"],
        )
        self.assertTrue(applied["ok"])

    def test_confirmed_new_fund_is_registered_before_position_apply(self):
        extracted = {
            "items": [
                {
                    "display_name": "电网设备C",
                    "current_value": 1200,
                    "daily_pnl": 1,
                    "holding_pnl": 200,
                    "holding_return_pct": 20,
                    "page_index": 1,
                    "row_index": 1,
                },
                {
                    "display_name": "天弘恒生科技ETF联接(QDII)A",
                    "current_value": 500,
                    "daily_pnl": -2,
                    "holding_pnl": -50,
                    "holding_return_pct": -9.09,
                    "page_index": 1,
                    "row_index": 2,
                },
            ],
            "warnings": [],
            "_transport_name": "direct",
        }
        with patch("sync_portfolio_from_screenshots.call_screenshot_vision", return_value=extracted):
            preview = parse_alipay_screenshot_upload(
                self.agent.root,
                {
                    "import_id": "alipay_with_new_fund",
                    "snapshot_date": "2026-05-05",
                    "files": [{"name": "page1.jpg", "data": base64.b64encode(b"not-an-image").decode("ascii")}],
                },
            )
        self.assertFalse(preview["apply_ready"])
        self.assertEqual(len(preview["unmatched_detected"]), 1)

        candidate = {
            "fund_code": "012348",
            "fund_name": "天弘恒生科技ETF联接A",
            "fund_type": "指数型-海外股票",
            "category": "etf_linked",
            "risk_level": "high",
            "company_name": "天弘基金",
            "manager_name": "胡超",
            "latest_nav": 0.6466,
            "nav_date": "2026-05-05",
            "aliases": ["天弘恒生科技指数(QDII)A"],
            "source_url": "https://fundf10.eastmoney.com/jbgk_012348.html",
            "search_source_url": "https://fundsuggest.eastmoney.com/?key=012348",
        }
        profile = {
            "fund_code": "012348",
            "fund_name": candidate["fund_name"],
            "benchmark": "恒生科技指数收益率*95%",
            "category": "etf_linked",
            "risk_level": "high",
            "status": "ok",
        }
        with patch("fund_registry.lookup_fund_by_code", return_value=candidate), patch("fund_registry.fetch_one_profile", return_value=profile):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                register_reconciliation_fund(
                    self.agent.root,
                    preview["reconcile_id"],
                    expected_preview_sha256="0" * 64,
                    display_name="天弘恒生科技ETF联接(QDII)A",
                    fund_code="012348",
                )
            resolved = register_reconciliation_fund(
                self.agent.root,
                preview["reconcile_id"],
                expected_preview_sha256=preview["preview_sha256"],
                display_name="天弘恒生科技ETF联接(QDII)A",
                fund_code="012348",
            )

        self.assertTrue(resolved["apply_ready"])
        self.assertNotEqual(resolved["reconcile_id"], preview["reconcile_id"])
        self.assertFalse(resolved["unmatched_detected"])
        definition = json.loads((self.agent.root / "config/portfolio_definition.json").read_text(encoding="utf-8"))
        registered = next(item for item in definition["funds"] if item["fund_code"] == "012348")
        self.assertFalse(registered["allow_trade"])
        self.assertEqual(registered["classification_status"], "pending_review")
        self.assertEqual(registered["benchmark"], "恒生科技指数收益率*95%")
        watchlist = json.loads((self.agent.root / "config/watchlist.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item["code"] == "012348" for item in watchlist["funds"]))

        applied = apply_saved_reconciliation(
            self.agent.root,
            resolved["reconcile_id"],
            preview_sha256=resolved["preview_sha256"],
            expected_portfolio_state_sha256=resolved["portfolio_state_sha256"],
        )
        self.assertIn("012348", applied["added_fund_codes"])
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        new_fund = next(item for item in portfolio["funds"] if item["fund_code"] == "012348")
        self.assertEqual(new_fund["current_value"], 500.0)
        self.assertFalse(new_fund["allow_trade"])

    def test_alipay_screenshot_upload_rejects_unsafe_import_id(self):
        with self.assertRaisesRegex(ValueError, "import_id"):
            parse_alipay_screenshot_upload(
                self.agent.root,
                {
                    "import_id": "..\\..\\escaped",
                    "files": [{"name": "page1.jpg", "data": base64.b64encode(b"image").decode("ascii")}],
                },
            )
        self.assertFalse((self.agent.root / "escaped").exists())

    def test_alipay_screenshot_upload_rejects_invalid_base64_and_too_many_files(self):
        with self.assertRaisesRegex(ValueError, "valid base64"):
            parse_alipay_screenshot_upload(
                self.agent.root,
                {"import_id": "invalid_base64", "files": [{"name": "page1.jpg", "data": "not-base64!"}]},
            )
        valid_file = {"name": "page.jpg", "data": base64.b64encode(b"image").decode("ascii")}
        with self.assertRaisesRegex(ValueError, "between 1 and 4"):
            parse_alipay_screenshot_upload(
                self.agent.root,
                {"import_id": "too_many", "files": [dict(valid_file) for _ in range(5)]},
            )

    def test_alipay_screenshot_upload_enforces_decoded_size_limits(self):
        with patch.object(execution_sync_module, "MAX_SCREENSHOT_FILE_BYTES", 3):
            with self.assertRaisesRegex(ValueError, "decoded bytes"):
                parse_alipay_screenshot_upload(
                    self.agent.root,
                    {
                        "import_id": "file_too_large",
                        "files": [{"name": "page.jpg", "data": base64.b64encode(b"1234").decode("ascii")}],
                    },
                )
        with patch.object(execution_sync_module, "MAX_SCREENSHOT_FILE_BYTES", 10), patch.object(
            execution_sync_module, "MAX_SCREENSHOT_TOTAL_BYTES", 5
        ):
            with self.assertRaisesRegex(ValueError, "payload exceeds"):
                parse_alipay_screenshot_upload(
                    self.agent.root,
                    {
                        "import_id": "total_too_large",
                        "files": [
                            {"name": "one.jpg", "data": base64.b64encode(b"123").decode("ascii")},
                            {"name": "two.jpg", "data": base64.b64encode(b"456").decode("ascii")},
                        ],
                    },
                )
        self.assertFalse((self.agent.root / "db/execution_sync/imports/alipay_screenshots/file_too_large").exists())
        self.assertFalse((self.agent.root / "db/execution_sync/imports/alipay_screenshots/total_too_large").exists())

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

        self.assertFalse(Path(recorded["path"]).is_absolute())
        actual_path = project_path(self.agent.root, recorded["path"])
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

    def test_settlement_metadata_paths_are_project_relative(self):
        record_actual_trade(
            self.agent.root,
            {
                "trade_id": "trade_relative_paths",
                "trade_date": "2026-05-04",
                "fund_code": "025857",
                "fund_name": "鐢电綉璁惧C",
                "operation_type": "buy",
                "amount": 100,
                "confirm_date": "2026-05-05",
            },
        )
        update_pending_confirmations(self.agent.root, "2026-05-05")

        current = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        metadata = current["state_metadata"]
        self.assertEqual("db/execution_sync/actual_trades/2026-05-04.json", metadata["source_path"])
        self.assertEqual("db/execution_sync/settlement_events/trade_relative_paths.json", metadata["settlement_event_path"])
        self.assertEqual("db/portfolio_state/events/2026-05-05/actual_trade_settlement_trade_relative_paths.json", metadata["event_journal_path"])
        self.assertNotRegex(json.dumps(metadata), r"[A-Za-z]:\\")

    def test_settlement_retry_recovers_after_portfolio_write_without_double_apply(self):
        record_actual_trade(
            self.agent.root,
            {
                "trade_id": "trade_crash_recovery",
                "trade_date": "2026-05-04",
                "fund_code": "025857",
                "fund_name": "grid equipment C",
                "operation_type": "buy",
                "amount": 300,
                "confirm_date": "2026-05-05",
            },
        )
        event_path = self.agent.root / "db/execution_sync/settlement_events/trade_crash_recovery.json"
        real_dump_json = execution_sync_module.dump_json
        fault_injected = False

        def flaky_dump_json(path, payload):
            nonlocal fault_injected
            if Path(path) == event_path and not fault_injected:
                fault_injected = True
                raise OSError("simulated crash before settlement marker")
            return real_dump_json(path, payload)

        with patch.object(execution_sync_module, "dump_json", side_effect=flaky_dump_json):
            first = update_pending_confirmations(self.agent.root, "2026-05-05")
        self.assertTrue(fault_injected)
        self.assertEqual(first["portfolio_applied_count"], 0)
        self.assertTrue(first["apply_errors"])
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1300.0)
        self.assertFalse(event_path.exists())

        second = update_pending_confirmations(self.agent.root, "2026-05-06")
        self.assertEqual(second["portfolio_applied_count"], 0)
        portfolio = json.loads((self.agent.root / "db/portfolio_state/current.json").read_text(encoding="utf-8"))
        fund = next(item for item in portfolio["funds"] if item["fund_code"] == "025857")
        self.assertEqual(fund["current_value"], 1300.0)
        self.assertTrue(event_path.exists())
        journal = json.loads(
            (self.agent.root / "db/execution_sync/settlement_journal/trade_crash_recovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(journal["status"], "completed")
        self.assertTrue(journal["recovered"])

    def test_settlement_rejects_same_idempotency_key_with_different_trade(self):
        trade = {
            "trade_id": "trade_digest_conflict",
            "trade_date": "2026-05-04",
            "confirm_date": "2026-05-05",
            "fund_code": "025857",
            "operation_type": "buy",
            "amount": 100,
        }
        first = apply_settled_trade_to_portfolio(self.agent.root, trade)
        self.assertTrue(first["ok"])
        with self.assertRaisesRegex(RuntimeError, "different trade payload"):
            apply_settled_trade_to_portfolio(self.agent.root, {**trade, "amount": 200})
        journal = json.loads(
            (self.agent.root / "db/execution_sync/settlement_journal/trade_digest_conflict.json").read_text(encoding="utf-8")
        )
        self.assertEqual(journal["status"], "conflict")

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
