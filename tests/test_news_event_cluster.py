from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.event_cluster import cluster_news_items, event_id_for  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
