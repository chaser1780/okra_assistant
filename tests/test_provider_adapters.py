from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_adapters import attach_provider_metadata, build_provider_payload, build_provider_result, resolve_provider_config, stale_fallback_from_recent_snapshot, stale_fallback_payload, summarize_provider_attempts

from helpers import TempAgentHome


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

    def test_build_provider_result_adds_unified_metadata(self):
        payload = build_provider_result(build_provider_payload("2026-03-11", "demo_provider", "items", [{"a": 1}]), provider_name="demo_provider")
        metadata = payload["provider_metadata"]
        self.assertEqual(metadata["provider_name"], "demo_provider")
        self.assertEqual(metadata["freshness_status"], "fresh")
        self.assertEqual(metadata["confidence"], "high")
        self.assertEqual(metadata["normalized_schema_version"], 1)

    def test_attach_provider_metadata_marks_fallback(self):
        payload = attach_provider_metadata(
            {"report_date": "2026-03-11", "provider": "stale_snapshot", "fallback_reason": "network"},
            selected_provider="stale_snapshot",
            provider_chain=["eastmoney", "stale_snapshot"],
            provider_attempts=[],
            fallback_kind="stale_snapshot",
        )
        summary = summarize_provider_attempts(payload)
        self.assertEqual(summary["freshness_status"], "fallback")
        self.assertEqual(summary["confidence"], "medium")

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

    def test_stale_fallback_from_recent_snapshot_uses_previous_date(self):
        agent = TempAgentHome()
        try:
            target_path = agent.root / "raw" / "quotes" / "2026-03-11.json"
            agent.write_json(
                "raw/quotes/2026-03-10.json",
                {
                    "report_date": "2026-03-10",
                    "provider": "eastmoney_nav_api",
                    "funds": [{"code": "F1", "stale": False}],
                },
            )
            payload = stale_fallback_from_recent_snapshot(target_path, "2026-03-11", "stale_snapshot", "funds", "network error")
            self.assertIsNotNone(payload)
            self.assertEqual(payload["report_date"], "2026-03-11")
            self.assertEqual(payload["source_report_date"], "2026-03-10")
            self.assertEqual(payload["fallback_source_date"], "2026-03-10")
            self.assertTrue(payload["funds"][0]["stale"])
        finally:
            agent.cleanup()


if __name__ == "__main__":
    unittest.main()
