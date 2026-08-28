from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.event_cluster import cluster_news_items, event_id_for  # noqa: E402
from news.repository import build_news_repository_payload  # noqa: E402


class NewsEventClusterTests(unittest.TestCase):
    def test_same_article_mapped_to_multiple_funds_forms_one_event(self):
        first = {
            "title": "政策推动新能源设备更新",
            "summary": "政策推动新能源设备更新",
            "canonical_url": "https://example.com/article?a=1&utm_source=test",
            "published_at": "2026-08-27T10:10:00+08:00",
            "code": "F1",
            "provider": "official",
            "source_tier": "official_policy",
            "risk_level": "medium",
            "sentiment_score": 0.4,
            "heat_score": 0.7,
            "freshness_status": "fresh",
        }
        second = {**first, "code": "F2", "provider": "media", "source_tier": "financial_media"}
        mapped, events, summary = cluster_news_items([first, second])
        self.assertEqual(1, len(events))
        self.assertEqual(2, len(mapped))
        self.assertEqual(mapped[0]["event_id"], mapped[1]["event_id"])
        self.assertEqual(["F1", "F2"], events[0]["fund_codes"])
        self.assertEqual(2, events[0]["source_count"])
        self.assertEqual(1, summary["multi_fund_event_count"])

    def test_event_identity_is_stable_without_url(self):
        first = {"title": "市场风险提示", "published_at": "2026-08-27T10:10:00+08:00"}
        second = {"title": " 市场风险提示 ", "published_at": "2026-08-27T11:20:00+08:00"}
        self.assertEqual(event_id_for(first), event_id_for(second))

    def test_repository_payload_keeps_items_and_exposes_provider_contract(self):
        payload = build_news_repository_payload(
            report_date="2026-08-27",
            provider_name="demo",
            provider_chain=["demo"],
            items=[{"title": "事件", "published_at": "2026-08-27T10:00:00+08:00", "code": "F1", "source_tier": "official_policy"}],
            source_health=[],
            query_plan={},
            sentiment_queries=[],
            dedup_summary={},
            global_dedup_summary={},
            classification_summary={},
        )
        self.assertEqual(1, len(payload["items"]))
        self.assertEqual(1, payload["event_summary"]["event_count"])
        self.assertEqual("news:demo", payload["providerResults"][0]["sourceKey"])

    def test_repository_emits_one_provider_result_for_each_source_health_record(self):
        payload = build_news_repository_payload(
            report_date="2026-08-27",
            provider_name="eastmoney_notice_and_articles",
            provider_chain=["eastmoney_notice_and_articles"],
            items=[
                {"title": "A", "published_at": "2026-08-27T10:00:00+08:00", "code": "F1", "provider": "rss:test", "stale": False},
                {"title": "B", "published_at": "2026-08-27T11:00:00+08:00", "code": "F1", "provider": "reg:test", "stale": True},
            ],
            source_health=[
                {"provider": "rss:test", "source_key": "rss_news:rss:test", "source_role": "theme_news", "status": "ok", "metrics": {"mapped_item_count": 1}},
                {"provider": "reg:test", "source_key": "regulatory_news:reg:test", "source_role": "regulatory_news", "status": "warning", "notes": ["timeout"], "metrics": {"retry_count": 1, "latency_ms": 42}},
            ],
            query_plan={},
            sentiment_queries=[],
            dedup_summary={},
            global_dedup_summary={},
            classification_summary={},
        )

        results = {item["provider"]: item for item in payload["providerResults"]}
        self.assertEqual("fresh", results["rss:test"]["freshness"])
        self.assertEqual("stale", results["reg:test"]["freshness"])
        self.assertEqual(1, results["reg:test"]["retryCount"])
        self.assertEqual(42, results["reg:test"]["latencyMs"])
        self.assertEqual(["timeout"], results["reg:test"]["warnings"])


if __name__ == "__main__":
    unittest.main()
