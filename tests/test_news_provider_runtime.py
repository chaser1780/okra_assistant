from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome  # noqa: E402
from news.provider_runtime import DEFAULT_FAILURE_THRESHOLD, NewsProviderRuntime, runtime_path  # noqa: E402


class NewsProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _health(self, *, errors: int = 0):
        return {
            "source_key": "rss_news:rss:test",
            "source_role": "theme_news",
            "provider": "rss:test",
            "status": "warning" if errors else "ok",
            "error_count": errors,
            "warning_count": 0,
            "notes": [],
            "metrics": {},
        }

    def test_repeated_failures_open_circuit_and_success_resets_it(self):
        runtime = NewsProviderRuntime(self.agent.root)
        for _ in range(DEFAULT_FAILURE_THRESHOLD):
            health = runtime.record(self._health(errors=1))
        runtime.save()

        allowed, reason = NewsProviderRuntime(self.agent.root).allow("rss_news:rss:test")

        self.assertFalse(allowed)
        self.assertTrue(reason.startswith("circuit_open_until="))
        self.assertTrue(health["runtime"]["circuit_open"])
        self.assertTrue(runtime_path(self.agent.root).exists())

        with patch("news.provider_runtime._now", return_value=__import__("datetime").datetime.fromisoformat(health["runtime"]["circuit_open_until"]) + __import__("datetime").timedelta(seconds=1)):
            recovered = NewsProviderRuntime(self.agent.root)
            allowed, _reason = recovered.allow("rss_news:rss:test")
            self.assertTrue(allowed)
            success = recovered.record(self._health(errors=0))
            self.assertEqual(0, success["runtime"]["consecutive_failures"])

    def test_skipped_source_is_explicitly_visible_as_warning_health(self):
        runtime = NewsProviderRuntime(self.agent.root)
        health = runtime.skipped_health(
            source_key="regulatory_news:reg:test",
            source_role="regulatory_news",
            provider="reg:test",
            reason="circuit_open_until=2026-08-28T10:00:00+08:00",
        )

        self.assertEqual("warning", health["status"])
        self.assertEqual(1, health["metrics"]["request_skipped"])
        self.assertTrue(health["runtime"]["circuit_open"])

    def test_demo_news_run_preserves_news_payload_and_writes_runtime_ledger(self):
        self.agent.run_script("fetch_fund_news.py", "--date", "2026-05-20", "--demo")

        payload = json.loads((self.agent.root / "raw" / "news" / "2026-05-20.json").read_text(encoding="utf-8"))
        runtime = json.loads(runtime_path(self.agent.root).read_text(encoding="utf-8"))

        self.assertIn("items", payload)
        self.assertIn("source_health", payload)
        self.assertIn("providerResults", payload)
        self.assertTrue(runtime["providers"])


if __name__ == "__main__":
    unittest.main()
