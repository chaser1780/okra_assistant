from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from build_llm_context import build_event_risks, build_memory_digest, build_news_digest, build_sentiment_digest
from build_daily_report import related_news
from learning_memory import run_learning_sync, write_learning_artifacts
from long_memory_store import upsert_memory_record
from portfolio_exposure import analyze_portfolio_exposure
import agent_inputs
from decision_support import build_agent_stage_snapshot, summarize_fund_stage_signals
from ui_support import build_auto_realtime_status_text, build_dashboard_text, load_state


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

    def test_agent_input_rag_shadow_does_not_inject_by_default(self):
        self.build_context()
        context = json.loads((self.agent.root / "db" / "llm_context" / "2026-03-10.json").read_text(encoding="utf-8"))
        context["_agent_home"] = self.agent.root
        context["_rag_agent_shadow"] = {"enabled": True, "write_trace": False, "inject_into_prompt": False}
        with patch("agent_inputs.retrieve_rag_evidence", return_value={"trace_id": "ragq-test", "hits": [{"doc_id": "d1", "source_kind": "evidence_item", "title": "hit", "summary": "summary"}], "missing_data": []}):
            agent_input = agent_inputs.build_agent_input("market_analyst", context, {})
        self.assertEqual("ragq-test", agent_input["rag_retrieval_trace_id"])
        self.assertEqual(1, agent_input["rag_legacy_diff"]["rag_hit_count"])
        self.assertNotIn("rag_retrieved_evidence", agent_input)

    def test_agent_input_rag_shadow_can_be_injected_explicitly(self):
        self.build_context()
        context = json.loads((self.agent.root / "db" / "llm_context" / "2026-03-10.json").read_text(encoding="utf-8"))
        context["_agent_home"] = self.agent.root
        context["_rag_agent_shadow"] = {"enabled": True, "write_trace": False, "inject_into_prompt": True}
        with patch("agent_inputs.retrieve_rag_evidence", return_value={"trace_id": "ragq-test", "hits": [{"doc_id": "d1", "source_kind": "evidence_item", "title": "hit", "summary": "summary"}], "missing_data": []}):
            agent_input = agent_inputs.build_agent_input("market_analyst", context, {})
        self.assertIn("rag_retrieved_evidence", agent_input)
        self.assertEqual("ragq-test", agent_input["rag_retrieved_evidence"]["trace_id"])

    def test_agent_default_rag_uses_rag_hits_when_enabled(self):
        self.build_context()
        context = json.loads((self.agent.root / "db" / "llm_context" / "2026-03-10.json").read_text(encoding="utf-8"))
        context["_agent_home"] = self.agent.root
        context["_rag_agent_default"] = {"enabled": True, "write_trace": False, "fallback_to_legacy": True, "min_hits": 1}
        context["_rag_agent_profiles"] = {"market_analyst": {"enabled": True, "top_k_portfolio": 4, "source_kinds": ["evidence_item"], "domains": ["fund"]}}
        with patch(
            "agent_inputs.retrieve_rag_evidence",
            return_value={
                "trace_id": "ragq-default",
                "hits": [{"doc_id": "d1", "chunk_id": "c1", "source_kind": "evidence_item", "title": "rag hit", "summary": "rag summary", "text_for_llm": "rag text"}],
                "missing_data": [],
            },
        ):
            agent_input = agent_inputs.build_agent_input("market_analyst", context, {})
        self.assertEqual("rag", agent_input["retrieval_backend"])
        self.assertEqual("ragq-default", agent_input["rag_default_trace_id"])
        self.assertEqual("rag hit", agent_input["evidence_items"][0]["title"])
        self.assertEqual("rag:d1#c1", agent_input["evidence_items"][0]["evidence_id"])

    def test_agent_default_rag_falls_back_to_legacy_when_hits_low(self):
        self.build_context()
        context = json.loads((self.agent.root / "db" / "llm_context" / "2026-03-10.json").read_text(encoding="utf-8"))
        context["_agent_home"] = self.agent.root
        context["_rag_agent_default"] = {"enabled": True, "write_trace": False, "fallback_to_legacy": True, "min_hits": 2}
        with patch("agent_inputs.retrieve_rag_evidence", return_value={"trace_id": "ragq-low", "hits": [], "missing_data": []}):
            agent_input = agent_inputs.build_agent_input("market_analyst", context, {})
        self.assertEqual("legacy_fallback", agent_input["retrieval_backend"])
        self.assertEqual("hit_count_below_min", agent_input["rag_default_fallback_reason"])
        self.assertNotIn("rag_retrieved_evidence", agent_input)

    def test_agent_default_rag_evidence_id_and_fund_map_contract(self):
        self.build_context()
        context = json.loads((self.agent.root / "db" / "llm_context" / "2026-03-10.json").read_text(encoding="utf-8"))
        context["_agent_home"] = self.agent.root
        context["_rag_agent_default"] = {"enabled": True, "write_trace": False, "fallback_to_legacy": True, "min_hits": 1}
        with patch(
            "agent_inputs.retrieve_rag_evidence",
            return_value={
                "trace_id": "ragq-contract",
                "hits": [
                    {
                        "doc_id": "doc-f1",
                        "chunk_id": "chunk-f1",
                        "source_kind": "committee_bundle",
                        "title": "F1 decision",
                        "summary": "F1 decision summary",
                        "text_for_llm": "F1 decision text",
                        "fund_codes": ["F1"],
                        "score": 0.91,
                    },
                    {
                        "doc_id": "doc-market",
                        "chunk_id": "chunk-market",
                        "source_kind": "llm_context",
                        "title": "market",
                        "summary": "global market summary",
                        "text_for_llm": "global market text",
                        "fund_codes": [],
                        "score": 0.5,
                    },
                ],
                "missing_data": [],
            },
        ):
            agent_input = agent_inputs.build_agent_input("market_analyst", context, {})

        self.assertEqual("rag", agent_input["retrieval_backend"])
        self.assertEqual("rag:doc-f1#chunk-f1", agent_input["evidence_items"][0]["evidence_id"])
        self.assertEqual("rag:doc-market#chunk-market", agent_input["evidence_items"][1]["evidence_id"])
        self.assertEqual(["rag:doc-f1#chunk-f1"], [item["evidence_id"] for item in agent_input["fund_evidence_map"]["F1"]])
        self.assertNotIn("F2", agent_input["fund_evidence_map"])

    def test_news_and_sentiment_digest_helpers(self):
        payload = {
            "items": [
                {
                    "code": "F1",
                    "title": "F1 官方公告",
                    "summary": "manager update",
                    "impact": "negative",
                    "source_name": "eastmoney_notice",
                    "source_role": "fund_news",
                    "source_tier": "official_notice",
                    "evidence_type": "official_notice",
                    "published_at": "2026-05-10T09:00:00+08:00",
                    "url": "https://example.com/notice",
                    "historical_significance": 0.8,
                },
                {
                    "code": "F1",
                    "title": "F1 social heat",
                    "summary": "social sample",
                    "impact": "positive",
                    "source_name": "xueqiu_web",
                    "source_role": "sentiment_news",
                    "evidence_type": "social_post",
                    "sentiment_score": 0.4,
                    "virality_score": 0.7,
                    "published_at": "2026-05-10T10:00:00+08:00",
                    "provider": "xueqiu_web",
                },
            ],
            "source_health": [
                {"source_key": "sentiment:xueqiu_web", "source_role": "sentiment_news", "provider": "xueqiu_web", "status": "ok", "item_count": 1}
            ],
        }
        news_digest = build_news_digest(payload)
        sentiment_digest = build_sentiment_digest(payload)
        event_risks = build_event_risks(payload)
        self.assertEqual(news_digest["item_count"], 2)
        self.assertEqual(news_digest["unique_item_count"], 2)
        self.assertEqual(news_digest["mapped_item_count"], 2)
        self.assertIn("top_heat_items", news_digest)
        self.assertEqual(sentiment_digest["item_count"], 1)
        self.assertIn("text_sentiment", sentiment_digest)
        self.assertEqual(sentiment_digest["providers"][0]["provider"], "news_text_pool")
        self.assertEqual(event_risks[0]["fund_code"], "F1")

    def test_daily_report_related_news_tolerates_missing_impact(self):
        lines = related_news(
            {
                "F1": [
                    {
                        "title": "F1 social heat",
                        "url": "https://example.com/news",
                        "source_name": "xueqiu_web",
                        "published_at": "2026-05-11T10:00:00+08:00",
                        "sentiment_score": 0.3,
                    }
                ]
            },
            "F1",
        )
        self.assertIn("positive", lines[0])

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
            "db/long_memory/exports/all_memory.json",
            {
                "updated_at": "2026-03-11T21:00:00+08:00",
                "items": [
                    {
                        "memory_id": "lesson:test",
                        "memory_type": "semantic",
                        "domain": "fund",
                        "entity_key": "F1",
                        "title": "测试 lesson",
                        "text": "测试 lesson",
                        "status": "strategic",
                        "confidence": 0.68,
                        "valid_from": "2026-03-10",
                        "updated_at": "2026-03-11T21:00:00+08:00",
                    }
                ],
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
        upsert_memory_record(
            self.agent.root,
            {
                "memory_type": "semantic",
                "domain": "fund",
                "entity_key": "committee_process",
                "title": "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。",
                "text": "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。",
                "status": "strategic",
                "confidence": 0.68,
                "valid_from": "2026-03-10",
            },
        )
        review_batches = [
            json.loads((self.agent.root / "db" / "review_results" / "2026-03-10_T1.json").read_text(encoding="utf-8"))
        ]
        cycle_summary, ledger, memory = run_learning_sync(self.agent.root, "2026-03-11", review_batches)
        write_learning_artifacts(self.agent.root, "2026-03-11", cycle_summary, ledger, memory, review_batches)
        export_payload = json.loads((self.agent.root / "db" / "long_memory" / "exports" / "compat_review_memory.json").read_text(encoding="utf-8"))
        self.assertTrue(export_payload.get("updated_at"))
        self.assertTrue((self.agent.root / "db" / "long_memory" / "portfolio" / "learning_ledger.json").exists())
        self.assertTrue(any(item.get("title") == "近期部分调仓建议被市场验证，可保留多智能体+规则校验框架。" for item in json.loads((self.agent.root / "db" / "long_memory" / "exports" / "all_memory.json").read_text(encoding="utf-8")).get("items", [])))

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
            "db/execution_sync/actual_trades/2026-03-10.json",
            {
                "trade_date": "2026-03-10",
                "items": [{"trade_id": "legacy_f1_buy", "trade_date": "2026-03-10", "fund_code": "F1", "fund_name": "基金一", "operation_type": "buy", "amount": 100.0, "user_note": "执行"}],
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
        self.assertTrue(payload["primary_diagnostic"])
        self.assertTrue(payload["diagnostic_summary"])
        self.assertTrue(payload["items"][0]["diagnostic_label"])

    def test_load_state_prefers_selected_snapshot_and_selected_manifest(self):
        self.agent.write_json(
            "config/portfolio.json",
            {"portfolio_name": "测试组合", "as_of_date": "2026-03-11", "total_value": 999.0, "funds": []},
        )
        self.agent.write_json(
            "db/portfolio_state/current.json",
            {"portfolio_name": "测试组合", "as_of_date": "2026-03-11", "total_value": 999.0, "funds": []},
        )
        self.agent.write_json(
            "db/portfolio_state/snapshots/2026-03-09.json",
            {"portfolio_name": "测试组合", "as_of_date": "2026-03-09", "total_value": 456.0, "funds": []},
        )
        self.agent.write_json(
            "db/run_manifests/2026-03-09/daily_pipeline_test.json",
            {"mode": "intraday", "status": "ok", "current_step": "validated"},
        )
        self.agent.write_json(
            "db/realtime_monitor/2026-03-09.json",
            {"report_date": "2026-03-09", "generated_at": "2026-03-09T14:00:00+08:00", "items": []},
        )
        self.agent.write_json(
            "db/realtime_monitor/2026-03-11.json",
            {"report_date": "2026-03-11", "generated_at": "2026-03-11T14:00:00+08:00", "items": []},
        )
        state = load_state(self.agent.root, "2026-03-09")
        self.assertEqual(state["portfolio"]["total_value"], 456.0)
        self.assertEqual(state["portfolio_date"], "2026-03-09")
        self.assertEqual(state["intraday_manifest"]["status"], "ok")
        self.assertEqual(state["realtime_date"], "2026-03-09")
        self.assertEqual(state["live_realtime_date"], "2026-03-11")

    def test_review_advice_uses_period_return_for_multi_day_horizon(self):
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
            {"funds": [{"code": "F1", "name": "基金一", "category": "active_equity", "benchmark": "成长代理", "risk_level": "high"}]},
        )
        self.agent.write_json(
            "db/execution_sync/actual_trades/2026-03-10.json",
            {"trade_date": "2026-03-10", "items": [{"trade_id": "legacy_f1_buy", "trade_date": "2026-03-10", "fund_code": "F1", "fund_name": "基金一", "operation_type": "buy", "amount": 100.0, "user_note": "执行"}]},
        )
        self.agent.write_json(
            "raw/quotes/2026-03-11.json",
            {"funds": [{"code": "F1", "day_change_pct": 1.2, "week_change_pct": 2.5}]},
        )
        self.agent.write_json("db/estimated_nav/2026-03-10.json", {"items": [{"fund_code": "F1", "estimate_change_pct": 0.9}]})
        self.agent.write_json("db/intraday_proxies/2026-03-10.json", {"proxies": [{"proxy_fund_code": "F1", "change_pct": 1.0}]})
        self.agent.write_json(
            "db/fund_nav_history/F1.json",
            {
                "fund_code": "F1",
                "items": [
                    {"date": "2026-03-10", "nav": 2.0},
                    {"date": "2026-03-11", "nav": 1.6},
                ],
            },
        )
        self.agent.run_script("review_advice.py", "--base-date", "2026-03-10", "--review-date", "2026-03-11", "--source", "execution", "--horizon", "1")
        payload = json.loads((self.agent.root / "db" / "execution_reviews" / "2026-03-10_execution_T1.json").read_text(encoding="utf-8"))
        item = payload["items"][0]
        self.assertEqual(item["evaluation_basis"], "period_return")
        self.assertEqual(item["evaluation_return_pct"], -20.0)
        self.assertEqual(item["outcome"], "adverse")

    def test_build_memory_digest_prioritizes_relevant_items(self):
        portfolio = {
            "portfolio_name": "测试组合",
            "funds": [
                {"fund_code": "F1", "fund_name": "成长轮动", "role": "tactical", "style_group": "growth_rotation", "current_value": 300.0},
                {"fund_code": "F2", "fund_name": "标普", "role": "core_dca", "style_group": "sp500_core", "current_value": 300.0},
            ],
        }
        exposure = analyze_portfolio_exposure(portfolio, {})
        digest = build_memory_digest(
            {
                "_analysis_date": "2026-03-20",
                "updated_at": "2026-03-20T21:00:00+08:00",
                "lessons": [
                    {"base_date": "2026-03-19", "type": "signal", "text": "成长轮动方向要先看修复确认。", "applies_to": "growth_rotation"},
                    {"base_date": "2025-12-01", "type": "signal", "text": "过旧且不相关。", "applies_to": "commodity_hedge"},
                ],
                "review_history": [{"base_date": "2026-03-19", "source": "advice", "memory_summary": "growth_rotation 近期更适合等待确认。"}],
                "bias_adjustments": [
                    {"base_date": "2026-03-18", "scope": "tomorrow_open", "target": "growth_rotation", "adjustment": "先等确认", "reason": "最近修复不稳", "expires_on": "2026-03-25"},
                    {"base_date": "2026-03-18", "scope": "tomorrow_open", "target": "commodity_hedge", "adjustment": "忽略", "reason": "不相关", "expires_on": "2026-03-25"},
                ],
                "agent_feedback": [
                    {"base_date": "2026-03-18", "agent_name": "risk_manager", "bias": "slightly_cautious", "reason": "growth_rotation 上更保守"},
                ],
            },
            portfolio,
            exposure,
        )
        lesson_texts = [item.get("text", "") for item in digest["recent_lessons"]]
        self.assertIn("成长轮动方向要先看修复确认。", lesson_texts)
        self.assertNotIn("过旧且不相关。", lesson_texts)
        self.assertIn("growth_rotation", digest["retrieval_context_tags"])

if __name__ == "__main__":
    unittest.main()
