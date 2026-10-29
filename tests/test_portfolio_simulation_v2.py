from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from web_api_services import PageService


class PortfolioSimulationV2PayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = TempAgentHome()
        self.service = PageService(self.agent.root, state_service=None)

    def tearDown(self) -> None:
        self.agent.cleanup()

    def _payload(self, portfolio: dict, *, state: dict | None = None) -> dict:
        base = {"portfolio": portfolio, "portfolio_date": "2026-10-28"}
        if state:
            base.update(state)
        return self.service.portfolio_payload(base)["simulationV2"]

    def test_v2_marker_exposes_record_fields_without_trade_scan(self) -> None:
        portfolio = {
            "as_of_date": "2026-10-27",
            "total_value": 1000.0,
            "funds": [
                {"fund_code": "AAA", "current_value": 600.0, "valuation_status": "exact"},
                {"fund_code": "BBB", "current_value": 400.0, "valuation_status": "pending"},
            ],
            "simulation_v2": {
                "version": 2,
                "funding_mode": "virtual_external_flows",
                "activated_at": "2026-10-20T00:00:00+08:00",
            },
            "external_flows_by_date": {"2026-10-20": 1000.0, "2026-10-27": -200.0},
            "external_cashflow": -200.0,
            "external_cashflow_timing": "end",
        }

        payload = self._payload(portfolio)

        self.assertEqual(payload["schemaVersion"], "simulation_v2")
        self.assertEqual(payload["fundingMode"], "virtual_external_flows")
        self.assertEqual(payload["netExternalFlow"], 800.0)
        self.assertEqual(payload["externalCashflow"], -200.0)
        self.assertEqual(payload["externalCashflowTiming"], "end")
        self.assertEqual(payload["valuationStatus"], "pending")

    def test_selected_date_takes_priority_over_record_as_of(self) -> None:
        portfolio = {
            "as_of_date": "2026-10-27",
            "total_value": 800.0,
            "funds": [{"fund_code": "AAA", "current_value": 800.0, "valuation_status": "exact"}],
            "simulation_v2": {"version": 2, "funding_mode": "virtual_external_flows"},
            "external_flows_by_date": {"2026-10-20": 1000.0, "2026-10-27": -200.0, "2026-10-29": 200.0},
            "external_cashflow": -200.0,
            "external_cashflow_timing": "end",
        }

        payload = self._payload(portfolio, state={"selected_date": "2026-10-28"})

        self.assertEqual(payload["portfolioDate"], "2026-10-27")
        self.assertEqual(payload["externalCashflow"], 0.0)
        self.assertEqual(payload["netExternalFlow"], 800.0)  # future 10-29 flow excluded

    def test_invalid_flow_values_render_as_none_not_nan(self) -> None:
        portfolio = {
            "as_of_date": "2026-10-28",
            "total_value": 800.0,
            "funds": [{"fund_code": "AAA", "current_value": 800.0}],
            "simulation_v2": {"version": 2, "funding_mode": "virtual_external_flows"},
            "external_flows_by_date": {"2026-10-28": "garbage"},
        }

        payload = self._payload(portfolio)

        self.assertIsNone(payload["externalCashflow"])
        self.assertIsNone(payload["netExternalFlow"])
        self.assertIsNone(payload["valuationStatus"])

    def test_legacy_portfolio_marks_legacy_without_fabricating_flows(self) -> None:
        portfolio = {
            "as_of_date": "2026-10-28",
            "total_value": 1000.0,
            "cash": 300.0,
            "funds": [{"fund_code": "AAA", "current_value": 700.0, "valuation_status": "exact"}],
        }

        payload = self._payload(portfolio)

        self.assertEqual(payload["schemaVersion"], "legacy")
        self.assertIsNone(payload["fundingMode"])
        self.assertIsNone(payload["netExternalFlow"])
        self.assertIsNone(payload["externalCashflow"])
        self.assertIsNone(payload["externalCashflowTiming"])
        self.assertEqual(payload["valuationStatus"], "exact")


if __name__ == "__main__":
    unittest.main()
