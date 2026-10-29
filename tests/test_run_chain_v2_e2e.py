from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from helpers import TempAgentHome  # noqa: E402
from run_promoted_advice_chain import run_chain  # noqa: E402


DATE = "2026-06-01"


def _llm_response(agent_home, system_prompt, user_payload, **kwargs):
    # 真实签名：call_json_agent(agent_home, system_prompt, user_payload_json_str, schema=...)
    # 返回 {"response_json": {"items": [...]}}，每个 ticket 合法枚举、无绝对金额。
    node = "action_former" if "action_former" in (kwargs.get("request_name") or "") else "other"
    payload = json.loads(user_payload)
    ids = payload.get("required_ticket_ids", [])
    items = []
    for tid in ids:
        code = tid.split(":")[-2] if tid.count(":") >= 3 else ""
        base = {
            "ticket_id": tid, "stance": "bull", "strength": "medium", "summary": "synthetic",
            "verdict": "support_shadow_ticket", "uncertainty": "low",
            "target_status": "shadow_only", "confidence_delta": 0.0, "reason": "synthetic",
            "non_executable": True,
        }
        if node == "action_former":
            base.update({
                "action": "add" if code == "TADD" else "hold",
                "size_tier": "medium" if code == "TADD" else "none",
                "horizon": "unspecified", "evidence_quality": "medium",
            })
        items.append(base)
    return {"response_json": {"items": items}}


class RunChainV2EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def write_inputs(self):
        self.agent.write_json("config/benchmark_mappings.json", {"fund_benchmarks": {}})
        for s in ("action_debate_graph.py", "build_action_ticket_shadow.py", "build_layered_retrieval_pack.py"):
            self.agent.write_text(f"scripts/{s}", f"# {s} fixture\n")
        portfolio = {
            "portfolio_name": "t", "as_of_date": DATE, "total_value": 1000.0,
            "funds": [
                {"fund_code": "DCA1", "fund_name": "Core", "role": "core_dca", "style_group": "core",
                 "current_value": 100.0, "allow_trade": True, "fixed_daily_buy_amount": 25.0,
                 "holding_units": 100.0, "last_valuation_nav": 1.0, "units_source": "stored"},
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub", "style_group": "cash",
                 "current_value": 500.0, "allow_trade": True, "holding_units": 500.0,
                 "last_valuation_nav": 1.0, "units_source": "stored"},
                {"fund_code": "TADD", "fund_name": "Add", "role": "tactical", "style_group": "growth",
                 "current_value": 200.0, "cap_value": 100000.0, "allow_trade": True,
                 "holding_units": 100.0, "last_valuation_nav": 2.0, "units_source": "stored"},
            ],
        }
        self.agent.write_json("db/portfolio_state/current.json", portfolio)
        self.agent.write_json(f"db/portfolio_state/snapshots/{DATE}.json", portfolio)
        self.agent.write_json(f"db/daily_scores/{DATE}.json", {
            "report_date": DATE, "funds": [
                {"code": "TADD", "name": "Add", "score": 88.0, "action": "add", "confidence": 0.8, "reasons": ["s"], "risk_flags": []},
            ]})
        self.agent.write_json(f"db/llm_context/{DATE}.json", {
            "analysis_date": DATE,
            "funds": [
                {"fund_code": "DCA1", "fund_name": "Core", "role": "core_dca"},
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub"},
                {"fund_code": "TADD", "fund_name": "Add", "role": "tactical",
                 "quote": {"day_change_pct": 1.0, "as_of_date": "2026-05-29"},
                 "recent_news": [{"title": "p", "summary": "p", "impact": "positive", "published_at": f"{DATE}T10:00:00+08:00"}],
                 "intraday_proxy": {"change_pct": 1.0, "trade_date": DATE}},
            ], "evidence_items": []})
        self.agent.write_json(f"db/evidence_index/{DATE}.json", {"items": []})
        self.agent.write_json(f"db/validated_advice/{DATE}.json", {
            "report_date": DATE, "tactical_actions": [], "dca_actions": [], "hold_actions": [],
            "market_view": {"summary": "base"}})

    def test_run_chain_llm_mode_emits_v2_tier_amount_metadata(self):
        self.write_inputs()
        with patch("action_debate_graph.call_json_agent", side_effect=_llm_response):
            path, status = run_chain(self.agent.root, DATE, generated_at=f"{DATE}T14:30:00+08:00", debate_mode="llm")
        self.assertTrue(path.exists())
        validated = json.loads((self.agent.root / "db" / "validated_advice" / f"{DATE}.json").read_text(encoding="utf-8"))
        # basis 起点冻结
        basis = json.loads((self.agent.root / "db" / "decision_basis" / f"{DATE}.json").read_text(encoding="utf-8"))
        self.assertEqual(f"{DATE}T14:30:00+08:00", basis["decision_at"])
        # 所有动作都带 v2 元数据（tactical + hold）
        all_actions = validated.get("tactical_actions", []) + validated.get("hold_actions", [])
        self.assertTrue(all_actions)
        for act in all_actions:
            self.assertEqual("simulation_v2", act.get("schema_version"), act.get("fund_code"))
            self.assertIn("size_tier", act)
            self.assertIn("size_ratio", act)
            self.assertIn("basis_position_value", act)
            self.assertIn("basis_snapshot_sha256", act)
            self.assertIn("decision_at", act)
            self.assertIn("evidence_quality", act)
            self.assertIn("horizon", act)
        # tactical add 金额 = 冻结 basis × tier（medium=25%）
        tactical = {a["fund_code"]: a for a in validated.get("tactical_actions", [])}
        if "TADD" in tactical:
            self.assertEqual("medium", tactical["TADD"]["size_tier"])
            self.assertAlmostEqual(200.0 * 0.25, tactical["TADD"]["validated_amount"], places=2)

    def test_same_day_manual_change_reuses_frozen_basis(self):
        self.write_inputs()
        with patch("action_debate_graph.call_json_agent", side_effect=_llm_response):
            run_chain(self.agent.root, DATE, generated_at=f"{DATE}T14:30:00+08:00", debate_mode="llm")
        # 中途手动改组合仓位（漂移），再次运行应复用原 basis，不重取复利
        cur = self.agent.root / "db" / "portfolio_state" / "current.json"
        pf = json.loads(cur.read_text(encoding="utf-8"))
        pf["funds"][2]["current_value"] = 99999.0  # TADD 漂移
        cur.write_text(json.dumps(pf, ensure_ascii=False), encoding="utf-8")
        with patch("action_debate_graph.call_json_agent", side_effect=_llm_response):
            run_chain(self.agent.root, DATE, generated_at=f"{DATE}T15:30:00+08:00", debate_mode="llm")
        basis = json.loads((self.agent.root / "db" / "decision_basis" / f"{DATE}.json").read_text(encoding="utf-8"))
        self.assertEqual(200.0, basis["funds"]["TADD"])  # 仍冻结首值


if __name__ == "__main__":
    unittest.main()
