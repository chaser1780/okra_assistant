from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_realtime_profit import apply_realtime_policy
from common import load_realtime_valuation_config, load_settings, project_path, resolve_agent_home
from cleanup_retention import load_retention_config
from preflight_check import perform_preflight
from multiagent_utils import resolve_api_key

from helpers import TempAgentHome

PROJECT_API_KEY_FILE = "config/" + "openai_api_key.txt"
REMOVED_WINDOWS_ACK_KEY = "windows_" + "wsl_setup_acknowledged"


class ConfigWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent_home = resolve_agent_home(str(Path(__file__).resolve().parents[1]))

    def test_realtime_policy_prefers_proxy_for_qdii(self):
        config = load_realtime_valuation_config(self.agent_home)
        estimate_allowed, proxy_allowed, note = apply_realtime_policy(
            "qdii_index",
            {"confidence": 0.38, "stale": True},
            config,
        )
        self.assertFalse(estimate_allowed)
        self.assertTrue(proxy_allowed)
        self.assertIn("代理行情", note)

    def test_realtime_policy_allows_high_confidence_equity_estimate(self):
        config = load_realtime_valuation_config(self.agent_home)
        estimate_allowed, proxy_allowed, note = apply_realtime_policy(
            "active_equity",
            {"confidence": 0.72, "stale": False},
            config,
        )
        self.assertTrue(estimate_allowed)
        self.assertTrue(proxy_allowed)
        self.assertEqual(note, "")

    def test_phase2_news_sources_are_configured(self):
        settings = load_settings(self.agent_home)
        providers = settings.get("providers", {})
        rss = providers.get("rss_news", {})
        regulatory = providers.get("regulatory_news", {})
        web_search = providers.get("openai_web_search_news", {})
        rss_providers = {feed.get("provider") for feed in rss.get("feeds", [])}
        regulatory_providers = {feed.get("provider") for feed in regulatory.get("feeds", [])}

        self.assertTrue(rss.get("enabled"))
        self.assertIn("rss:chinanews_finance", rss_providers)
        self.assertIn("rss:xinhuanet_fortune", rss_providers)
        self.assertTrue(regulatory.get("enabled"))
        self.assertIn("reg:szse_inquiry", regulatory_providers)
        self.assertIn("reg:szse_supervision_measure", regulatory_providers)
        self.assertIn("reg:szse_disciplinary_action", regulatory_providers)
        self.assertTrue(web_search.get("enabled"))
        self.assertIn("web_search", web_search.get("tool_types", []))

    def test_retention_config_protects_permanent_state(self):
        config = load_retention_config(self.agent_home)
        protected = set(config.get("protected_paths", []))
        rules = {rule.get("name"): rule for rule in config.get("rules", [])}

        self.assertIn("db/long_memory", protected)
        self.assertIn("db/execution_sync", protected)
        self.assertIn("db/portfolio_state", protected)
        self.assertIn("db/validated_advice", protected)
        self.assertEqual("archive", rules["raw_news"]["action"])
        self.assertEqual("db/llm_context/{date}.json", rules["raw_news"]["require_existing"])
        self.assertEqual(60, rules["raw_news"]["retention_days"])

    def test_project_config_uses_portable_relative_paths(self):
        llm_config = (self.agent_home / "config" / "llm.toml").read_text(encoding="utf-8")
        settings = load_settings(self.agent_home)
        portfolio = (self.agent_home / "config" / "portfolio.json").read_text(encoding="utf-8")
        definition = (self.agent_home / "config" / "portfolio_definition.json").read_text(encoding="utf-8")

        self.assertNotRegex(llm_config + portfolio + definition, r"[A-Za-z]:\\")
        sentiment = settings["providers"]["sentiment_news"]
        self.assertNotIn(f'api_key_file = "{PROJECT_API_KEY_FILE}"', llm_config)
        self.assertNotIn(REMOVED_WINDOWS_ACK_KEY, llm_config)
        self.assertEqual(self.agent_home / "config" / "xueqiu_cookie.txt", project_path(self.agent_home, sentiment["xueqiu_cookie_file"]))
        self.assertEqual(self.agent_home / "config" / "douyin_cookie.txt", project_path(self.agent_home, sentiment["douyin_cookie_file"]))

    def test_preflight_check_writes_result_without_network_probe(self):
        temp = TempAgentHome()
        try:
            os.environ["OPENAI_API_KEY"] = "test-key"
            result = perform_preflight(temp.root, "intraday", probe_llm=False)
            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue((temp.root / "db" / "preflight" / "latest.json").exists())
            check_names = {item["name"] for item in result["checks"]}
            self.assertIn("schedule:intraday", check_names)
            self.assertIn("llm:probe", check_names)
            python_check = next(item for item in result["checks"] if item["name"] == "python_config")
            self.assertEqual("ok", python_check["status"])
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            temp.cleanup()

    def test_preflight_blocks_live_pipeline_when_llm_probe_fails(self):
        temp = TempAgentHome()
        try:
            os.environ["OPENAI_API_KEY"] = "test-key"
            with patch(
                "preflight_check.probe_llm_model",
                return_value={
                    "status": "error",
                    "detail": "HTTP 404 model_not_found",
                    "retryable": False,
                    "attempts": [{"status_code": 404, "retryable": False}],
                },
            ):
                result = perform_preflight(temp.root, "intraday", probe_llm=True)

            self.assertEqual(result["status"], "failed")
            probe = next(item for item in result["checks"] if item["name"] == "llm:probe")
            self.assertEqual(probe["status"], "error")
            self.assertFalse(probe["retryable"])
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            temp.cleanup()

    def test_resolve_api_key_uses_ignored_local_openai_key_file_as_fallback(self):
        temp = TempAgentHome()
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            temp.write_text("config/openai_api_key.txt", "local-key")
            config = {
                "model_provider": "OpenAI",
                "api_key_env": "OPENAI_API_KEY",
                "api_key_file": "",
            }

            self.assertEqual("local-key", resolve_api_key(config, temp.root))
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
