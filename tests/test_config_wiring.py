from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_realtime_profit import apply_realtime_policy
from common import load_agents_config, load_realtime_valuation_config, load_settings, resolve_agent_home
from cleanup_retention import load_retention_config
from preflight_check import perform_preflight
from run_multiagent_research import configured_orders, configured_workers

from helpers import TempAgentHome


class ConfigWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent_home = resolve_agent_home(r"F:\okra_assistant")

    def test_agents_config_is_loaded_into_runtime_orders(self):
        analysts, researchers, managers, _config = configured_orders(self.agent_home)
        self.assertIn("market_analyst", analysts)
        self.assertIn("bull_researcher", researchers)
        self.assertIn("risk_manager", managers)

    def test_agents_parallel_workers_follow_config(self):
        config = load_agents_config(self.agent_home)
        workers = configured_workers(config)
        self.assertEqual(workers["analyst"], 6)
        self.assertEqual(workers["researcher"], 2)

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
        rss_providers = {feed.get("provider") for feed in rss.get("feeds", [])}
        regulatory_providers = {feed.get("provider") for feed in regulatory.get("feeds", [])}

        self.assertTrue(rss.get("enabled"))
        self.assertIn("rss:chinanews_finance", rss_providers)
        self.assertIn("rss:xinhuanet_fortune", rss_providers)
        self.assertTrue(regulatory.get("enabled"))
        self.assertIn("reg:szse_inquiry", regulatory_providers)
        self.assertIn("reg:szse_supervision_measure", regulatory_providers)
        self.assertIn("reg:szse_disciplinary_action", regulatory_providers)

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
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
