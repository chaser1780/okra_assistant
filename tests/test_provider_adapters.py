from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provider_adapters import build_provider_payload, resolve_provider_config, stale_fallback_payload


class ProviderAdaptersTests(unittest.TestCase):
    def test_resolve_provider_config(self):
        settings = {
            "providers": {
                "quotes": {"name": "eastmoney_nav_api", "timeout_seconds": 15},
            }
        }
        config = resolve_provider_config(settings, "quotes", None)
        self.assertEqual(config.name, "eastmoney_nav_api")
        self.assertEqual(config.timeout_seconds, 15)

    def test_build_provider_payload(self):
        payload = build_provider_payload("2026-03-11", "demo_provider", "items", [{"a": 1}], enabled=True)
        self.assertEqual(payload["report_date"], "2026-03-11")
        self.assertEqual(payload["provider"], "demo_provider")
        self.assertEqual(payload["items"][0]["a"], 1)
        self.assertTrue(payload["enabled"])

    def test_stale_fallback_payload_marks_items(self):
        payload = stale_fallback_payload(
            {"report_date": "2026-03-11", "proxies": [{"symbol": "x", "stale": False}]},
            "proxy_fallback",
            "proxies",
            "network error",
        )
        self.assertEqual(payload["provider"], "proxy_fallback")
        self.assertTrue(payload["proxies"][0]["stale"])
        self.assertEqual(payload["proxies"][0]["fallback_reason"], "network error")


if __name__ == "__main__":
    unittest.main()
