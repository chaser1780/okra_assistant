from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from news.providers.regulatory import fetch_regulatory_news  # noqa: E402


class RegulatoryProviderAdapterTests(unittest.TestCase):
    def test_szse_source_uses_official_json_endpoint_and_preserves_health(self):
        calls: list[str] = []

        def fetch_json(url: str, *, timeout_seconds: int, referer: str):
            calls.append(url)
            return "[]"

        def normalize_item(raw, **kwargs):
            return {"provider": kwargs["provider_name"], "title": raw["title"]}

        def health(**kwargs):
            return kwargs

        items, rows = fetch_regulatory_news(
            {"enabled": True, "feeds": [{"name": "inquiry", "url": "https://example.test/inquiry", "provider": "reg:szse_inquiry"}]},
            "2026-05-20",
            fetch_html=lambda *_args, **_kwargs: "",
            fetch_json=fetch_json,
            parse_sse=lambda *_args: [],
            parse_amac=lambda *_args: [],
            parse_szse_page=lambda *_args: [],
            parse_szse_report=lambda *_args: [{"title": "问询函"}],
            normalize_item=normalize_item,
            build_health=health,
        )

        self.assertEqual(1, len(items))
        self.assertIn("CATALOGID=main_wxhj", calls[0])
        self.assertEqual(1, rows[0]["metrics"]["normalized_count"])
        self.assertEqual("ok", rows[0]["status"])


if __name__ == "__main__":
    unittest.main()
