from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.providers.eastmoney import fetch_query_news  # noqa: E402


class EastmoneyQueryProviderTests(unittest.TestCase):
    def test_bucket_limits_and_health_metrics_are_preserved(self):
        calls: list[str] = []

        def search(keyword: str, *, page_size: int, timeout_seconds: int):
            calls.append(keyword)
            return {"items": [{"title": keyword, "url": f"https://example.test/{keyword}"}]}

        def normalize(item, query, *, source_role: str, report_date: str):
            return [{"provider": "eastmoney_search_api", "title": item["title"], "url": item["url"], "source_role": source_role, "stale": False}]

        def dedupe(rows, *, dedup_window_hours: int):
            return rows, {"unique_item_count": len(rows), "mapped_item_count": len(rows), "duplicate_item_count": 0, "dedup_drop_count": 0}

        def health(**kwargs):
            return kwargs

        items, row = fetch_query_news(
            {"enabled": True, "max_queries": 2, "max_queries_per_bucket": 1, "results_per_query": 1},
            "2026-05-20",
            {"direct_queries": [{"keyword": "基金"}], "theme_queries": [{"keyword": "科技"}], "market_queries": [{"keyword": "市场"}]},
            default_timeout_seconds=15,
            search=search,
            extract_items=lambda payload: payload["items"],
            query_matches=lambda keyword, item: keyword in item["title"],
            normalize_item=normalize,
            dedupe_items=dedupe,
            build_health=health,
        )

        self.assertEqual(["基金", "科技"], calls)
        self.assertEqual(2, len(items))
        self.assertEqual(2, row["metrics"]["queries_used"])
        self.assertEqual("ok", row["status"])


if __name__ == "__main__":
    unittest.main()
