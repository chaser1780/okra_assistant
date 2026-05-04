from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from qtui.state_service import DesktopSnapshot, DesktopStateService
from ui_support import summarize_state


class QtStateServiceTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(r"F:\okra_assistant")
        self.service = DesktopStateService(self.home)

    def build_snapshot(self) -> DesktopSnapshot:
        state = {
            "selected_date": "2026-03-10",
            "dates": ["2026-03-09", "2026-03-10"],
            "portfolio_date": "2026-03-09",
            "portfolio_report": "组合报告",
            "portfolio": {
                "portfolio_name": "测试组合",
                "total_value": 1200.0,
                "funds": [
                    {"fund_code": "F1", "fund_name": "基金一", "role": "tactical", "current_value": 300.0, "holding_return_pct": 2.5},
                    {"fund_code": "CASH", "fund_name": "现金仓", "role": "cash_hub", "current_value": 400.0},
                ],
            },
            "strategy": {"schedule": {"report_mode": "intraday_proxy"}},
            "validated": {
                "market_view": {"regime": "mixed", "summary": "市场偏均衡"},
                "tactical_actions": [
                    {
                        "fund_code": "F1",
                        "fund_name": "基金一",
                        "validated_action": "add",
                        "validated_amount": 200.0,
                        "thesis": "趋势改善",
                        "execution_status": "pending",
                    }
                ],
                "dca_actions": [],
                "hold_actions": [
                    {
                        "fund_code": "F2",
                        "fund_name": "基金二",
                        "validated_action": "hold",
                        "validated_amount": 0.0,
                        "execution_status": "not_applicable",
                    }
                ],
            },
            "aggregate": {
                "agents": {"research_manager": {"status": "ok", "output": {"confidence": 0.8}}},
                "agent_roles": {"research_manager": "manager"},
                "ordered_agents": ["research_manager"],
                "failed_agents": [],
                "degraded_agent_names": [],
            },
            "realtime": {
                "items": [
                    {
                        "fund_code": "F1",
                        "fund_name": "基金一",
                        "estimated_position_value": 320.0,
                        "estimated_intraday_pnl_amount": 12.0,
                        "effective_change_pct": 1.2,
                        "confidence": 0.82,
                        "mode": "estimate",
                        "stale": False,
                        "anomaly_score": 1.6,
                    },
                    {
                        "fund_code": "F2",
                        "fund_name": "基金二",
                        "estimated_position_value": 280.0,
                        "estimated_intraday_pnl_amount": -8.0,
                        "effective_change_pct": -0.8,
                        "confidence": 0.42,
                        "mode": "proxy",
                        "stale": True,
                        "anomaly_score": 2.4,
                    },
                ]
            },
            "realtime_date": "2026-03-10",
            "review_results_for_date": [{"items": [{"fund_code": "F1", "outcome": "supportive"}]}],
            "review_memory": {},
            "learning_cycle": {"batch_count": 2},
            "memory_ledger": {"summary": {"strategic": 1, "permanent": 0, "core_permanent": 0}, "rules": []},
            "replay_experiments": [{"experiment_id": "exp1", "mode": "revalidate", "changed_days": 1, "edge_delta_total": 2.5, "applied_to_learning": False}],
            "learning_report": "学习报告",
            "llm_config": {"model": "gpt-5.4", "model_provider": "openai"},
            "preflight": {"status": "ok"},
            "llm_context": {
                "exposure_summary": {
                    "allocation_plan": {"rebalance_needed": False, "rebalance_band_pct": 5.0},
                    "concentration_metrics": {"high_volatility_theme_weight_pct": 12.5, "defensive_buffer_weight_pct": 18.0},
                }
            },
        }
        summary = summarize_state(state)
        return DesktopSnapshot(home=self.home, state=state, summary=summary, selected_date="2026-03-10", dates=["2026-03-09", "2026-03-10"])

    def test_build_dashboard_view_model(self):
        snapshot = self.build_snapshot()
        vm = self.service.build_dashboard_view_model(snapshot)
        self.assertEqual(vm.primary_fund_code, "F1")
        self.assertEqual(vm.metrics[0].title, "今日主动作")
        self.assertIn("基金一", vm.focus_text)

    def test_build_research_and_realtime_view_models(self):
        snapshot = self.build_snapshot()
        research_vm = self.service.build_research_view_model(snapshot)
        self.assertEqual(len(research_vm.rows), 2)
        self.assertTrue(research_vm.rows[0]["_is_actionable"])
        realtime_vm = self.service.build_realtime_view_model(snapshot)
        self.assertEqual(len(realtime_vm.items), 2)
        self.assertEqual(realtime_vm.metrics[1].title, "陈旧数据")

    def test_build_shell_and_runtime_view_models(self):
        snapshot = self.build_snapshot()
        shell_vm = self.service.build_shell_view_model(snapshot, running=False, chain_status="今日链路：已更新")
        self.assertEqual(shell_vm.status_badge_state, "idle")
        runtime_vm = self.service.build_runtime_view_model(
            {
                "intraday": {"status": "ok"},
                "realtime": {"status": "idle"},
                "nightly": {"status": "pending"},
            },
            "replay_experiment",
        )
        self.assertIn("当前任务=replay_experiment", runtime_vm.banner)


if __name__ == "__main__":
    unittest.main()
