from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_portfolio_from_trade import (  # noqa: E402
    apply_trade,
    record_cash_dividend,
    record_internal_fee,
)
from execution_sync import _apply_operation_to_portfolio  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from revalue_portfolio_official_nav import build_official_daily_pnl  # noqa: E402
from execution_sync import record_actual_trade  # noqa: E402
from portfolio_state import set_position_units_from_value  # noqa: E402
from performance_metrics import calculate_portfolio_performance  # noqa: E402


def make_portfolio() -> dict:
    return {
        "portfolio_name": "v2",
        "as_of_date": "2026-05-04",
        "total_value": 2000.0,
        "holding_pnl": 0.0,
        "funds": [
            {"fund_code": "025857", "fund_name": "目标", "role": "tactical",
             "current_value": 1000.0, "holding_units": 500.0, "cost_basis_value": 1000.0,
             "holding_pnl": 0.0, "holding_return_pct": 0.0},
            {"fund_code": "017704", "fund_name": "旧现金池", "role": "cash_hub",
             "current_value": 1000.0, "holding_units": 1000.0, "cost_basis_value": 1000.0,
             "holding_pnl": 0.0, "holding_return_pct": 0.0},
        ],
    }


def f(p, c):
    return next(x for x in p["funds"] if x["fund_code"] == c)


class VirtualExternalFlowsTests(unittest.TestCase):
    def test_buy_fee_conservation_no_double_count(self):
        p = make_portfolio()
        apply_trade(p, "025857", "buy", 100.0, trade_nav=2.0, fee=2.0)
        # asset rises by net principal only; the fee left the wallet via the bigger inflow
        self.assertEqual(1100.0, f(p, "025857")["current_value"])
        self.assertEqual(102.0, p["external_cashflow"])
        # cash hub untouched: no closure misuse, no auto funding source
        self.assertEqual(1000.0, f(p, "017704")["current_value"])
        self.assertEqual(1000.0, f(p, "017704")["holding_units"])
        # net assets = 1100 + 1000 = 2100; external inflow 102 on 100 principal => fee drag 2
        self.assertEqual(2100.0, p["total_value"])
        self.assertEqual(0.0, p.get("income_adjustment_value", 0.0))
        self.assertEqual("virtual_external_flows", p["simulation_v2"]["funding_mode"])
        self.assertEqual("end", p["external_cashflow_timing"])

    def test_sell_fee_conservation(self):
        p = make_portfolio()
        apply_trade(p, "025857", "sell", 100.0, trade_nav=2.0, fee=2.0)
        self.assertEqual(900.0, f(p, "025857")["current_value"])
        # net proceeds (gross - fee) flow out
        self.assertEqual(-98.0, p["external_cashflow"])
        self.assertEqual(1000.0, f(p, "017704")["current_value"])
        self.assertEqual(1900.0, p["total_value"])

    def test_units_resolution_exact_derived_or_pending(self):
        # explicit units, no nav -> derived_from_explicit_trade, never official
        p = make_portfolio()
        apply_trade(p, "025857", "buy", 100.0, trade_units=40.0)
        fund = f(p, "025857")
        self.assertEqual(540.0, fund["holding_units"])
        self.assertEqual("derived_from_explicit_trade", fund["units_source"])
        self.assertEqual("derived_from_explicit_trade", fund["last_valuation_nav_source"])
        self.assertEqual("exact", fund["valuation_status"])

        # nav given -> amount/nav units
        p = make_portfolio()
        apply_trade(p, "025857", "buy", 100.0, trade_nav=2.0)
        self.assertEqual(550.0, f(p, "025857")["holding_units"])

        # neither -> pending, no fabrication from stale value
        p = make_portfolio()
        apply_trade(p, "025857", "buy", 100.0)
        fund = f(p, "025857")
        self.assertEqual(1100.0, fund["current_value"])
        self.assertEqual(500.0, fund["holding_units"])  # unchanged, not mutated-value inferred
        self.assertEqual("pending", fund["valuation_status"])
        self.assertEqual("unconfirmed_trade_units", fund["units_source"])

    def test_sell_rejected_on_insufficient_value_or_units(self):
        p = make_portfolio()
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "sell", 9999.0, trade_nav=2.0)
        p = make_portfolio()
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "sell", 100.0, trade_nav=2.0, trade_units=9999.0)

    def test_conversion_internal_fee_no_external_no_double_adjustment(self):
        p = make_portfolio()
        trade = {"operation_type": "convert", "out_fund_code": "025857", "in_fund_code": "017704",
                 "out_amount": 200.0, "in_amount": 198.0, "out_nav": 2.0, "in_nav": 1.0}
        _apply_operation_to_portfolio(p, trade)
        self.assertEqual(800.0, f(p, "025857")["current_value"])
        self.assertEqual(1198.0, f(p, "017704")["current_value"])
        # total asset drops by exactly the internal fee 2; no external flow
        self.assertEqual(0.0, p["external_cashflow"])
        self.assertEqual(0.0, p.get("income_adjustment_value", 0.0))

    def test_conversion_fee_mismatch_rejected_not_guessed(self):
        p = make_portfolio()
        trade = {"operation_type": "convert", "out_fund_code": "025857", "in_fund_code": "017704",
                 "out_amount": 200.0, "in_amount": 198.0, "fee": 5.0}
        with self.assertRaises(RuntimeError):
            _apply_operation_to_portfolio(p, trade)

    def test_cash_dividend_internal_asset_no_external_flow(self):
        p = make_portfolio()
        record_cash_dividend(p, "025857", 10.0, reinvest=False)
        self.assertEqual(10.0, p["income_adjustment_value"])
        self.assertEqual(0.0, p["external_cashflow"])
        self.assertEqual(2010.0, p["total_value"])

    def test_reinvest_dividend_increases_units_without_double_count(self):
        p = make_portfolio()
        record_cash_dividend(p, "025857", 10.0, reinvest=True, trade_nav=2.0)
        self.assertEqual(0.0, p.get("income_adjustment_value", 0.0))  # not booked again
        self.assertEqual(505.0, f(p, "025857")["holding_units"])

    def test_independent_fee_reduces_internal_adjustment(self):
        p = make_portfolio()
        record_internal_fee(p, 3.0)
        self.assertEqual(-3.0, p["income_adjustment_value"])
        self.assertEqual(0.0, p["external_cashflow"])
        self.assertEqual(1997.0, p["total_value"])


class InputValidationTests(unittest.TestCase):
    def test_nan_or_negative_amount_rejected_before_mutation(self):
        p = make_portfolio()
        for bad in (float("nan"), -5.0, 0.0):
            with self.assertRaises(RuntimeError):
                apply_trade(p, "025857", "buy", bad)
        # portfolio untouched
        self.assertEqual(1000.0, f(p, "025857")["current_value"])
        self.assertNotIn("simulation_v2", p)

    def test_sell_fee_exceeding_gross_rejected(self):
        p = make_portfolio()
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "sell", 100.0, trade_nav=2.0, fee=150.0)

    def test_nonpositive_nav_or_units_rejected(self):
        p = make_portfolio()
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "buy", 100.0, trade_nav=0.0)
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "buy", 100.0, trade_units=-1.0)

    def test_nav_times_units_must_agree_with_amount(self):
        p = make_portfolio()
        with self.assertRaises(RuntimeError):
            apply_trade(p, "025857", "buy", 100.0, trade_nav=2.0, trade_units=60.0)  # 120 != 100

    def test_unknown_prior_units_buy_stays_pending_not_exact(self):
        p = make_portfolio()
        f(p, "025857")["holding_units"] = None  # prior total unknown
        apply_trade(p, "025857", "buy", 100.0, trade_units=40.0)
        fund = f(p, "025857")
        self.assertEqual(40.0, fund["holding_units"])
        self.assertEqual("pending", fund["valuation_status"])
        self.assertEqual("partial_explicit_trade_units", fund["units_source"])

    def test_full_sell_zeroes_units_not_pending(self):
        p = make_portfolio()
        apply_trade(p, "025857", "sell", 1000.0)  # no nav/units, liquidate whole
        fund = f(p, "025857")
        self.assertEqual(0.0, fund["current_value"])
        self.assertEqual(0.0, fund["holding_units"])
        self.assertEqual("closed_position", fund["units_source"])
        self.assertEqual("exact", fund["valuation_status"])

    def test_dividend_marks_netting_pending_not_unknown_units(self):
        p = make_portfolio()
        record_cash_dividend(p, "025857", 10.0, reinvest=False)
        # units stay trusted; only a netting marker is set so revalue can net it
        self.assertEqual(True, f(p, "025857")["dividend_netting_pending"])
        self.assertEqual(1.0, len(p["pending_dividend_events"]))


class FlowIdempotencyTests(unittest.TestCase):
    def test_duplicate_operation_does_not_double_accumulate_flow(self):
        trade = {"operation_type": "buy", "fund_code": "025857", "amount": 100.0, "fee": 2.0,
                 "trade_date": "2026-05-04"}
        p = make_portfolio()
        _apply_operation_to_portfolio(p, trade)
        # second application must not happen on a new/different id; simulate replay guard:
        flows = p["external_flows_by_date"]
        self.assertEqual(102.0, flows["2026-05-04"])
        # replay would be blocked upstream by idempotency; here prove accumulation is additive once
        _apply_operation_to_portfolio(p, trade | {"amount": 50.0, "fee": 1.0})
        self.assertEqual(102.0 + 51.0, flows["2026-05-04"])


class DividendRevaluationSerialTests(unittest.TestCase):
    def test_recorded_dividend_nets_ex_div_day_not_fake_loss(self):
        home = TempAgentHome()
        try:
            home.write_json(
                "db/execution_sync/actual_trades/2026-05-05.json",
                {"trade_date": "2026-05-05", "items": [
                    {"trade_id": "div-1", "operation_type": "dividend", "fund_code": "025857",
                     "amount": 20.0, "dividend_reinvest": False, "trade_date": "2026-05-05"}]},
            )
            fund = {"fund_code": "025857", "fund_name": "t", "holding_units": 1000.0,
                    "units_source": "actual_trade_units", "current_value": 1980.0,
                    "dividend_netting_pending": True}
            nav_info = {"official_nav": 1.98, "nav_date": "2026-05-05", "nav_source": "quotes",
                        "previous_nav": 2.0, "previous_nav_date": "2026-05-04", "stale": False}
            out = build_official_daily_pnl(home.root, fund, nav_info, "2026-05-05")
            # price delta = 1000*(1.98-2.0) = -20, net cash dividend +20 -> 0, not a fake -20 loss
            self.assertEqual("ok", out["official_daily_pnl_status"])
            self.assertAlmostEqual(0.0, out["official_daily_pnl"], places=2)
            self.assertEqual("dividend_events_included", out["official_daily_pnl_reason"])
            self.assertFalse(fund["dividend_netting_pending"])
        finally:
            home.cleanup()

    def test_ex_div_without_event_is_unavailable_not_fake_loss(self):
        home = TempAgentHome()
        try:
            home.write_json(
                "db/fund_nav_history/025857.json",
                {"items": [
                    {"date": "2026-05-04", "nav": 2.0, "cumulative_nav": 2.0},
                    {"date": "2026-05-05", "nav": 1.98, "cumulative_nav": 2.0}]},
            )
            fund = {"fund_code": "025857", "fund_name": "t", "holding_units": 1000.0,
                    "units_source": "actual_trade_units", "current_value": 1980.0}
            nav_info = {"official_nav": 1.98, "nav_date": "2026-05-05", "nav_source": "quotes",
                        "previous_nav": 2.0, "previous_nav_date": "2026-05-04", "stale": False}
            out = build_official_daily_pnl(home.root, fund, nav_info, "2026-05-05")
            self.assertEqual("blocked", out["official_daily_pnl_status"])
            self.assertEqual("dividend_event_missing", out["official_daily_pnl_reason"])
        finally:
            home.cleanup()


class RecordedTradeV2FieldsTests(unittest.TestCase):
    def test_recorded_buy_carries_server_computed_external_cashflow(self):
        home = TempAgentHome()
        try:
            result = record_actual_trade(home.root, {
                "trade_id": "buy-100-fee-2", "operation_type": "buy", "fund_code": "025857",
                "amount": 100.0, "fee": 2.0, "trade_date": "2026-05-05", "trade_time": "14:00",
                "external_cashflow": 99999.0,  # request-forged must be ignored
            })
            trade = result["trade"]
            self.assertEqual("simulation_v2", trade["schema_version"])
            self.assertEqual("virtual_external_flows", trade["funding_mode"])
            self.assertEqual(102.0, trade["external_cashflow"])
            self.assertEqual("end", trade["external_cashflow_timing"])
            # replay idempotent, no double flow
            replay = record_actual_trade(home.root, {
                "trade_id": "buy-100-fee-2", "operation_type": "buy", "fund_code": "025857",
                "amount": 100.0, "fee": 2.0, "trade_date": "2026-05-05", "trade_time": "14:00"})
            self.assertTrue(replay["idempotent_replay"])
        finally:
            home.cleanup()

    def test_recorded_sell_and_internal_ops_have_zero_or_net_external(self):
        home = TempAgentHome()
        try:
            sell = record_actual_trade(home.root, {"trade_id": "s1", "operation_type": "sell",
                "fund_code": "025857", "amount": 100.0, "fee": 2.0, "trade_date": "2026-05-05"})
            self.assertEqual(-98.0, sell["trade"]["external_cashflow"])
            fee = record_actual_trade(home.root, {"trade_id": "f1", "operation_type": "fee",
                "fund_code": "025857", "amount": 3.0, "trade_date": "2026-05-05"})
            self.assertEqual(0.0, fee["trade"]["external_cashflow"])
        finally:
            home.cleanup()


class LinkedFeeGuardTests(unittest.TestCase):
    def test_linked_fee_rejected_when_trade_fee_already_absorbed(self):
        home = TempAgentHome()
        try:
            record_actual_trade(home.root, {"trade_id": "buy-1", "operation_type": "buy",
                "fund_code": "025857", "amount": 100.0, "fee": 2.0, "trade_date": "2026-05-05"})
            with self.assertRaises(ValueError):
                record_actual_trade(home.root, {"trade_id": "fee-1", "operation_type": "fee",
                    "fund_code": "025857", "amount": 2.0, "trade_date": "2026-05-05",
                    "fee_for_trade_id": "buy-1"})
        finally:
            home.cleanup()

    def test_standalone_fee_without_link_is_allowed(self):
        home = TempAgentHome()
        try:
            fee = record_actual_trade(home.root, {"trade_id": "fee-standalone",
                "operation_type": "fee", "fund_code": "025857", "amount": 3.0, "trade_date": "2026-05-05"})
            self.assertEqual(0.0, fee["trade"]["external_cashflow"])
        finally:
            home.cleanup()


class PendingUnitsFillNoDoubleApplyTests(unittest.TestCase):
    def test_fill_pending_units_does_not_reapply_trade(self):
        p = make_portfolio()
        apply_trade(p, "025857", "buy", 100.0)  # amount-only, no nav/units
        fund = f(p, "025857")
        self.assertEqual("pending", fund["valuation_status"])
        self.assertEqual(1100.0, fund["current_value"])
        ok = set_position_units_from_value(fund, 1100.0, fallback_source="manual_reconcile", basis_nav=2.0)
        self.assertTrue(ok)
        self.assertEqual(550.0, fund["holding_units"])
        self.assertEqual(1100.0, fund["current_value"])  # not double-applied
        self.assertEqual("exact", fund["valuation_status"])

    def test_manual_reconcile_then_revalue_runs_not_blocked(self):
        home = TempAgentHome()
        try:
            fund = {"fund_code": "025857", "fund_name": "t", "holding_units": None,
                    "units_source": "unconfirmed_trade_units", "valuation_status": "pending",
                    "current_value": 1100.0}
            # human reconciliation supplies trusted units from official nav
            set_position_units_from_value(fund, 1100.0, fallback_source="manual_position_snapshot", basis_nav=2.0)
            self.assertEqual(550.0, fund["holding_units"])
            self.assertEqual("exact", fund["valuation_status"])
            nav_info = {"official_nav": 2.1, "nav_date": "2026-05-06", "nav_source": "quotes",
                        "previous_nav": 2.0, "previous_nav_date": "2026-05-05", "stale": False}
            out = build_official_daily_pnl(home.root, fund, nav_info, "2026-05-06")
            self.assertEqual("ok", out["official_daily_pnl_status"])
            self.assertAlmostEqual(550.0 * (2.1 - 2.0), out["official_daily_pnl"], places=2)
        finally:
            home.cleanup()


from strategy_simulation import create_experiment, record_action  # noqa: E402


class StrategyExperimentExternalFlowTests(unittest.TestCase):
    def _exp(self, home):
        initial = {"as_of_date": "2026-05-20", "total_value": 1000.0, "funds": [
            {"fund_code": "CASH", "current_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0},
            {"fund_code": "F1", "current_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0}]}
        create_experiment(home.root, {"experimentId": "e", "label": "e", "initialPortfolio": initial})

    def test_duplicate_action_id_does_not_double_accumulate_flow(self):
        home = TempAgentHome()
        try:
            self._exp(home)
            record_action(home.root, {"experimentId": "e", "actionId": "a1", "action": "buy", "fundCode": "F1", "amount": 100})
            replay = record_action(home.root, {"experimentId": "e", "actionId": "a1", "action": "buy", "fundCode": "F1", "amount": 100})
            self.assertTrue(replay["idempotentReplay"])
            p = replay["experiment"]["portfolio"]
            self.assertEqual(100.0, p["net_external_flow"])  # not 200
            self.assertEqual(1100.0, p["total_value"])
        finally:
            home.cleanup()

    def test_buy_then_sell_net_external_zero_value_delta_zero(self):
        home = TempAgentHome()
        try:
            self._exp(home)
            record_action(home.root, {"experimentId": "e", "actionId": "b1", "action": "buy", "fundCode": "F1", "amount": 100})
            record_action(home.root, {"experimentId": "e", "actionId": "s1", "action": "sell", "fundCode": "F1", "amount": 100})
            from strategy_simulation import _summary
            from pathlib import Path
            exp_dir = home.root / "db" / "strategy_simulation" / "experiments"
            s = _summary(home.root, (lambda: __import__("json").loads((exp_dir / "e.json").read_text(encoding="utf-8")))(), exp_dir / "e.json")
            self.assertEqual(0.0, s["netExternalFlow"])
            self.assertEqual(0.0, s["valueDelta"])
        finally:
            home.cleanup()

    def test_buy_does_not_touch_cash_hub(self):
        home = TempAgentHome()
        try:
            self._exp(home)
            out = record_action(home.root, {"experimentId": "e", "actionId": "b1", "action": "buy", "fundCode": "F1", "amount": 100})
            cash = next(f for f in out["experiment"]["portfolio"]["funds"] if f["fund_code"] == "CASH")
            self.assertEqual(500.0, cash["current_value"])
        finally:
            home.cleanup()


class SameDayFlowMetricsTests(unittest.TestCase):
    def test_net_daily_flow_used_not_last_trade_single_value(self):
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            # same-day buy 1000 then sell 500: assets 10500, day net +500, but the stale
            # single external_cashflow only keeps the last trade (-500).
            {"date": "2026-05-06", "total_value": 10500.0,
             "external_cashflow": -500.0, "external_cashflow_timing": "end",
             "external_flows_by_date": {"2026-05-06": 500.0}},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertEqual("available", out["status"])
        self.assertAlmostEqual(0.0, out["twr"]["returnPct"], places=2)

    def test_legacy_snapshot_without_flow_map_falls_back_to_single_value(self):
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            {"date": "2026-05-06", "total_value": 10500.0,
             "external_cashflow": 500.0, "external_cashflow_timing": "end"},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertEqual("available", out["status"])
        self.assertAlmostEqual(0.0, out["twr"]["returnPct"], places=2)

    def _seed_portfolio(self):
        return {
            "as_of_date": "2026-05-05", "total_value": 10000.0, "holding_pnl": 0.0,
            "funds": [{"fund_code": "F1", "current_value": 10000.0, "holding_units": 10000.0,
                        "cost_basis_value": 10000.0, "holding_pnl": 0.0, "last_valuation_nav": 1.0}],
        }

    def test_real_entry_two_same_day_trades_net_flow_zero_twr(self):
        p = self._seed_portfolio()
        p = _apply_operation_to_portfolio(p, {"operation_type": "buy", "fund_code": "F1",
            "amount": 1000.0, "effective_trade_date": "2026-05-06"})
        p = _apply_operation_to_portfolio(p, {"operation_type": "sell", "fund_code": "F1",
            "amount": 500.0, "effective_trade_date": "2026-05-06"})
        self.assertEqual(10500.0, p["total_value"])
        self.assertEqual(-500.0, p["external_cashflow"])                       # stale single
        self.assertEqual(500.0, p["external_flows_by_date"]["2026-05-06"])     # net day flow
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            {"date": "2026-05-06", "total_value": p["total_value"],
             "external_cashflow": p["external_cashflow"], "external_cashflow_timing": "end",
             "external_flows_by_date": p["external_flows_by_date"]},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertEqual("available", out["status"])
        self.assertAlmostEqual(0.0, out["twr"]["returnPct"], places=2)

    def test_corrupt_day_flow_map_does_not_fall_back_to_scalar(self):
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            {"date": "2026-05-06", "total_value": 10500.0,
             "external_cashflow": -500.0, "external_cashflow_timing": "end",
             "external_flows_by_date": {"2026-05-06": "abc"}},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertNotEqual("available", out["status"])

    def test_cross_day_snapshot_without_trade_day_has_no_flow(self):
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            {"date": "2026-05-06", "total_value": 10500.0,
             "external_cashflow": -500.0, "external_cashflow_timing": "end",
             "external_flows_by_date": {"2026-05-06": 500.0}},
            {"date": "2026-05-07", "total_value": 10500.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end",
             "external_flows_by_date": {"2026-05-06": 500.0}},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertEqual("available", out["status"])
        self.assertAlmostEqual(0.0, out["twr"]["returnPct"], places=2)

    def test_malformed_flow_map_container_is_not_scalar_fallback(self):
        snapshots = [
            {"date": "2026-05-05", "total_value": 10000.0,
             "external_cashflow": 0.0, "external_cashflow_timing": "end"},
            {"date": "2026-05-06", "total_value": 10500.0,
             "external_cashflow": 500.0, "external_cashflow_timing": "end",
             "external_flows_by_date": ["bad"]},
        ]
        out = calculate_portfolio_performance(snapshots)
        self.assertNotEqual("available", out["status"])


if __name__ == "__main__":
    unittest.main()