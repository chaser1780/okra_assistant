from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.providers.openai_web_search import fetch_web_search_news  # noqa: E402


class OpenAiWebSearchProviderTests(unittest.TestCase):
    def test_retries_next_tool_and_keeps_citation_normalization_boundary(self):
        tools: list[str] = []

        def build_payload(_config, _settings, _queries, _date, tool):
            return {"tool": tool}

        def call(_config, payload, **_kwargs):
            tools.append(payload["tool"])
            if payload["tool"] == "web_search_preview":
                raise RuntimeError("preview unavailable")
            return {"output_text": "[]", "citations": ["https://example.test/news"]}

        def dedupe(items, *, dedup_window_hours: int):
            return items, {"mapped_item_count": len(items), "unique_item_count": len(items), "duplicate_item_count": 0, "dedup_drop_count": 0}

        def health(**kwargs):
            return kwargs

        items, row = fetch_web_search_news(
            agent_home=None,
            config={},
            provider_settings={"enabled": True, "tool_types": ["web_search_preview"]},
            report_date="2026-05-20",
            query_plan={"direct_queries": [{"keyword": "基金"}], "theme_queries": [], "market_queries": []},
            build_payload=build_payload,
            call=call,
            parse_output=lambda _output: [{"url": "https://example.test/news"}],
            extract_citations=lambda _response: {"https://example.test/news"},
            normalize_item=lambda raw, **_kwargs: raw,
            dedupe_items=dedupe,
            build_health=health,
            should_stop_retry=lambda _exc: False,
        )

        self.assertEqual(["web_search_preview", "web_search"], tools)
        self.assertEqual(1, len(items))
        self.assertEqual("web_search", row["metrics"]["selected_tool"])
        self.assertEqual("warning", row["status"])


if __name__ == "__main__":
    unittest.main()
