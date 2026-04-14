from __future__ import annotations

import json
import unittest

from helpers import TempAgentHome
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from run_multiagent_research import compact_agent_output, degradation_summary, sanitize_agent_output
from decision_support import build_agent_stage_snapshot, summarize_fund_stage_signals
from ui_support import build_auto_realtime_status_text, build_dashboard_text


class MultiagentAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def build_context(self):
        self.agent.write_json(
            "db/llm_context/2026-03-10.json",
            {
                "analysis_date": "2026-03-10",
                "mode": "intraday",
                "generated_at": "2026-03-10T14:00:00+08:00",
                "portfolio_summary": {
                    "portfolio_name": "测试组合",
                    "total_value": 1000.0,
                    "holding_pnl": 0.0,
                    "risk_profile": "balanced",
                    "role_counts": {"tactical": 2},
                    "all_intraday_proxies_stale": False,
                    "all_estimates_stale": False,
                    "stale_proxy_count": 0,
                    "stale_estimate_count": 0,
                    "delayed_official_nav_count": 0,
                },
                "constraints": {
                    "daily_max_trade_amount": 1000.0,
                    "fixed_dca_total": 0.0,
                    "tactical_budget_after_dca": 1000.0,
                    "cash_hub_floor": 100.0,
                },
                "external_reference": {"use_yangjibao_board_heat": True, "manual_biases": []},
                "memory_digest": {"updated_at": "", "recent_lessons": [], "recent_review_history": [], "recent_bias_adjustments": [], "recent_agent_feedback": []},
                "funds": [
                    {
                        "fund_code": "F1",
                        "fund_name": "基金一",
                        "role": "tactical",
                        "style_group": "growth",
                        "current_value": 400.0,
                        "holding_pnl": 0.0,
                        "holding_return_pct": 0.0,
                        "cap_value": 1000.0,
                        "allow_trade": True,
                        "locked_amount": 0.0,
                        "fixed_daily_buy_amount": 0.0,
                        "quote": {"day_change_pct": 1.0, "week_change_pct": 2.0, "month_change_pct": 3.0},
                        "intraday_proxy": {"change_pct": 1.2, "stale": False, "proxy_name": "代理一"},
                        "estimated_nav": {"estimate_change_pct": 1.1, "confidence": 0.8, "stale": False},
                        "recent_news": [],
                    },
                    {
                        "fund_code": "F2",
                        "fund_name": "基金二",
                        "role": "tactical",
                        "style_group": "value",
                        "current_value": 300.0,
                        "holding_pnl": -10.0,
                        "holding_return_pct": -3.0,
                        "cap_value": 1000.0,
                        "allow_trade": True,
                        "locked_amount": 0.0,
                        "fixed_daily_buy_amount": 0.0,
                        "quote": {"day_change_pct": -1.0, "week_change_pct": -2.0, "month_change_pct": -3.0},
                        "intraday_proxy": {"change_pct": -0.5, "stale": False, "proxy_name": "代理二"},
                        "estimated_nav": {"estimate_change_pct": -0.3, "confidence": 0.7, "stale": False},
                        "recent_news": [],
                    },
                ],
            },
        )

    def test_run_multiagent_research_mock_writes_aggregate(self):
        self.build_context()
        self.agent.run_script("run_multiagent_research.py", "--date", "2026-03-10", "--mock")
        aggregate = json.loads((self.agent.root / "db" / "agent_outputs" / "2026-03-10" / "aggregate.json").read_text(encoding="utf-8"))
        self.assertTrue(aggregate["all_agents_ok"])
        self.assertIn("market_analyst", aggregate["ordered_agents"])
        self.assertIn("portfolio_trader", aggregate["agents"])
        self.assertEqual(aggregate["agents"]["portfolio_trader"]["status"], "ok")
        self.assertIn("analyst", aggregate["agent_groups"])
        self.assertIn("portfolio_trader", aggregate["agent_dependencies"])
        self.assertIn("manager", aggregate["stage_status"])
        self.assertEqual(aggregate["agent_roles"]["research_manager"], "manager")

    def test_build_nightly_review_report_aggregates_multiple_horizons(self):
        self.agent.write_json(
            "db/review_results/2026-03-10_T0.json",
            {
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 0,
                "summary": {"supportive": 1, "adverse": 0, "missed_upside": 0, "unknown": 0},
                "items": [{"fund_code": "F1", "fund_name": "基金一", "validated_action": "add", "validated_amount": 100.0, "outcome": "supportive", "review_day_change_pct": 1.5, "review_week_change_pct": 2.0, "estimated_change_pct": 1.1, "proxy_change_pct": 1.0}],
            },
        )
        self.agent.write_json(
            "db/review_results/2026-03-06_T5.json",
            {
                "base_date": "2026-03-06",
                "review_date": "2026-03-11",
                "horizon": 5,
                "summary": {"supportive": 0, "adverse": 1, "missed_upside": 0, "unknown": 0},
                "items": [{"fund_code": "F2", "fund_name": "基金二", "validated_action": "reduce", "validated_amount": 200.0, "outcome": "adverse", "review_day_change_pct": -0.5, "review_week_change_pct": 1.2, "estimated_change_pct": -0.3, "proxy_change_pct": -0.2}],
            },
        )
        self.agent.write_json(
            "db/review_memory/memory.json",
            {
                "updated_at": "2026-03-11T21:00:00+08:00",
                "lessons": [{"base_date": "2026-03-10", "horizon": 0, "text": "测试 lesson"}],
                "review_history": [],
                "bias_adjustments": [],
                "agent_feedback": [],
            },
        )
        self.agent.write_json(
            "db/portfolio_valuation/2026-03-11.json",
            {
                "report_date": "2026-03-11",
                "generated_at": "2026-03-11T20:00:00+08:00",
                "updated_fund_count": 2,
                "skipped_fund_count": 0,
                "stale_fund_codes": [],
            },
        )

        self.agent.run_script("build_nightly_review_report.py", "--review-date", "2026-03-11")
        report = (self.agent.root / "reports" / "daily" / "2026-03-11_review.md").read_text(encoding="utf-8")
        self.assertIn("T0｜建议日期 2026-03-10", report)
        self.assertIn("T+5｜建议日期 2026-03-06", report)
        self.assertIn("## 官方净值重估摘要", report)

    def test_compact_agent_output_keeps_core_fields(self):
        output = {
            "agent_name": "research_manager",
            "summary": "summary",
            "confidence": 0.8,
            "evidence_strength": "high",
            "data_freshness": "fresh",
            "key_points": ["a", "b"],
            "watchouts": ["w1"],
            "portfolio_view": {"regime": "mixed", "risk_bias": "balanced", "key_drivers": ["d1"], "portfolio_implications": ["i1"]},
            "fund_views": [{"fund_code": "F1", "action_bias": "add", "thesis": "t", "comment": "c", "risks": ["r1", "r2", "r3"]}],
        }
        compact = compact_agent_output(output)
        self.assertEqual(compact["agent_name"], "research_manager")
        self.assertEqual(compact["portfolio_view"]["regime"], "mixed")
        self.assertEqual(compact["fund_views"][0]["fund_code"], "F1")
        self.assertEqual(compact["fund_views"][0]["risks"], ["r1", "r2"])

    def test_sanitize_agent_output_removes_tail_noise(self):
        output = {
            "agent_name": "research_manager",
            "summary": "  研究结论  ",
            "key_points": ["有效信息", "完成。", "结束。", "有效信息"],
            "missing_info": ["缺少规模数据", " "],
            "watchouts": ["no_trade_list如下。", "请特别注意其中QDII相关理由的低置信属性。", "保留高质量动作"],
            "portfolio_view": {"regime": "mixed", "risk_bias": "balanced", "key_drivers": ["主驱动", "完成。"], "portfolio_implications": ["先控仓", "结束。"]},
            "fund_views": [{"fund_code": "F1", "thesis": "  继续观察  ", "action_bias": "hold", "comment": "结束。", "catalysts": ["有效催化", "完成。"], "risks": ["风险一", "风险一"]}],
        }
        cleaned = sanitize_agent_output(output)
        self.assertEqual(cleaned["summary"], "研究结论")
        self.assertEqual(cleaned["key_points"], ["有效信息"])
        self.assertEqual(cleaned["watchouts"], ["保留高质量动作"])
        self.assertEqual(cleaned["portfolio_view"]["portfolio_implications"], ["先控仓"])
        self.assertEqual(cleaned["fund_views"][0]["catalysts"], ["有效催化"])

    def test_degradation_summary_allows_non_core_failure(self):
        aggregate = {
            "failed_agents": [{"agent_name": "sentiment_analyst", "error": "compatibility"}],
            "agents": {
                "research_manager": {"status": "ok"},
                "risk_manager": {"status": "ok"},
                "portfolio_trader": {"status": "ok"},
            },
        }
        summary = degradation_summary(aggregate, ["research_manager", "risk_manager", "portfolio_trader"])
        self.assertTrue(summary["committee_ready"])
        self.assertTrue(summary["degraded_ok"])
        self.assertEqual(summary["blocking_failures"], [])

    def test_build_agent_stage_snapshot_and_fund_stage_summary(self):
        aggregate = {
            "agent_roles": {
                "market_analyst": "analyst",
                "bull_researcher": "researcher",
                "research_manager": "manager",
            },
            "agent_dependencies": {
                "market_analyst": [],
                "bull_researcher": ["market_analyst"],
                "research_manager": ["market_analyst", "bull_researcher"],
            },
            "required_committee_agents": ["research_manager"],
            "agents": {
                "market_analyst": {"status": "ok", "output": {"fund_views": [{"fund_code": "F1", "action_bias": "add", "comment": "trend improving"}]}},
                "bull_researcher": {"status": "ok", "output": {"fund_views": [{"fund_code": "F1", "action_bias": "bullish_add", "comment": "upside remains"}]}},
                "research_manager": {"status": "ok", "output": {"fund_views": [{"fund_code": "F1", "action_bias": "hold", "comment": "wait for confirmation"}]}},
            },
        }
        snapshot = build_agent_stage_snapshot("research_manager", aggregate)
        self.assertEqual(snapshot["stage"], "manager")
        self.assertTrue(snapshot["is_committee_core"])
        self.assertEqual(snapshot["depends_on"], ["market_analyst", "bull_researcher"])
        stage_summary = summarize_fund_stage_signals(aggregate, "F1")
        self.assertEqual(stage_summary["analyst"]["support"], ["market_analyst"])
        self.assertEqual(stage_summary["researcher"]["support"], ["bull_researcher"])
        self.assertEqual(stage_summary["manager"]["neutral"], ["research_manager"])

    def test_build_dashboard_text_handles_failed_agent_dicts(self):
        summary = {
            "selected_date": "2026-03-10",
            "portfolio_name": "测试组合",
            "all_agents_ok": False,
            "failed_agents": [{"agent_name": "sentiment_analyst", "error": "bad"}],
            "failed_agent_names": ["sentiment_analyst"],
            "transport_name": "direct",
            "advice_mode": "committee_fallback",
            "advice_is_fallback": True,
            "advice_is_mock": False,
            "aggregate_degraded_ok": True,
            "preflight_status": "warning",
        }
        text = build_dashboard_text(
            summary,
            {"market_view": {"regime": "mixed", "summary": "测试摘要"}, "tactical_actions": []},
            {"as_of_date": "2026-03-09", "last_valuation_generated_at": "2026-03-09T21:00:00+08:00"},
            "",
            None,
            [],
            [],
            ["测试摘要", "暂无动作", "存在告警"],
        )
        self.assertIn("失败智能体：sentiment_analyst", text)
        self.assertIn("建议生成模式：committee_fallback（fallback）", text)

    def test_build_auto_realtime_status_text_contains_schedule(self):
        from datetime import datetime

        text = build_auto_realtime_status_text("2026-03-13T14:00:00+08:00", datetime(2026, 3, 13, 14, 5, 0), True)
        self.assertIn("启动即刷新", text)
        self.assertIn("最近成功刷新", text)
        self.assertIn("下次计划刷新", text)

    def test_update_review_memory_dedupes_existing_lessons(self):
        self.agent.write_json(
            "db/review_results/2026-03-10_T1.json",
            {
                "base_date": "2026-03-10",
                "review_date": "2026-03-11",
                "horizon": 1,
                "summary": {"supportive": 1, "adverse": 0, "missed_upside": 0, "unknown": 0},
                "items": [],
            },
        )
        self.agent.write_json(
            "db/review_memory/memory.json",
            {
                "updated_at": "2026-03-11T21:00:00+08:00",
                "lessons": [
                    {
                        "base_date": "2026-03-10",
                        "horizon": 1,
                        "type": "edge",
                        "text": "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。",
                        "confidence": 0.68,
                        "applies_to": "committee_process",
                    }
                ],
                "review_history": [],
                "bias_adjustments": [],
                "agent_feedback": [],
            },
        )
        self.agent.run_script("update_review_memory.py", "--base-date", "2026-03-10", "--horizon", "1")
        memory = json.loads((self.agent.root / "db" / "review_memory" / "memory.json").read_text(encoding="utf-8"))
        matching = [item for item in memory["lessons"] if item.get("text") == "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。"]
        self.assertEqual(len(matching), 1)

    def test_review_advice_execution_source_writes_execution_review(self):
        self.agent.write_json(
            "config/portfolio.json",
            {
                "portfolio_name": "测试组合",
                "as_of_date": "2026-03-10",
                "total_value": 1000.0,
                "holding_pnl": 0.0,
                "funds": [
                    {
                        "fund_code": "F1",
                        "fund_name": "基金一",
                        "role": "tactical",
                        "style_group": "growth",
                        "current_value": 400.0,
                        "holding_pnl": 0.0,
                        "holding_return_pct": 0.0,
                        "holding_units": 200.0,
                        "cost_basis_value": 400.0,
                        "last_valuation_nav": 2.0,
                        "allow_trade": True,
                    }
                ],
            },
        )
        self.agent.write_json(
            "config/watchlist.json",
            {
                "funds": [
                    {"code": "F1", "name": "基金一", "category": "active_equity", "benchmark": "成长代理", "risk_level": "high"}
                ]
            },
        )
        self.agent.write_json(
            "db/trade_journal/2026-03-10.json",
            {
                "trade_date": "2026-03-10",
                "items": [{"fund_code": "F1", "fund_name": "基金一", "action": "buy", "amount": 100.0, "note": "执行"}],
            },
        )
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {
                "funds": [{"code": "F1", "day_change_pct": 1.2, "week_change_pct": 2.5}],
            },
        )
        self.agent.write_json(
            "db/estimated_nav/2026-03-10.json",
            {"items": [{"fund_code": "F1", "estimate_change_pct": 0.9}]},
        )
        self.agent.write_json(
            "db/intraday_proxies/2026-03-10.json",
            {"proxies": [{"proxy_fund_code": "F1", "change_pct": 1.0}]},
        )
        self.agent.run_script("review_advice.py", "--base-date", "2026-03-10", "--review-date", "2026-03-11", "--source", "execution", "--horizon", "1")
        payload = json.loads((self.agent.root / "db" / "execution_reviews" / "2026-03-10_execution_T1.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["source"], "execution")
        self.assertEqual(payload["aggregate_metrics"]["reviewed_item_count"], 1)


if __name__ == "__main__":
    unittest.main()
