from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_realtime_profit import apply_realtime_policy
from common import load_agents_config, load_realtime_valuation_config, resolve_agent_home
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
