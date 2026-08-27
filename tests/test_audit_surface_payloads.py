from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import OkraWebApi  # noqa: E402
from helpers import TempAgentHome  # noqa: E402
from long_memory_store import upsert_memory_record  # noqa: E402
from strategy_simulation import create_experiment, record_action  # noqa: E402


class AuditSurfacePayloadTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def test_review_page_exposes_redacted_decision_trace_summary(self):
        report_date = "2026-05-20"
        self.agent.write_json(
            f"db/decision_traces/{report_date}.json",
            {
                "traceId": "decision-test",
                "reportDate": report_date,
                "generatedAt": "2026-05-20T15:00:00+08:00",
                "decisionSource": "action_debate_promoted",
                "formalTrack": "user_simulation",
                "simulationOnly": True,
                "executionEligible": True,
                "evidenceSnapshot": {"itemCount": 4},
                "modelRuns": [{"modelRunId": "run-1"}],
                "sourceArtifacts": {"validatedAdvice": {"exists": True}, "rawPrompt": {"exists": False}},
                "decisions": [
                    {
                        "fundCode": "F1",
                        "fundName": "Fund 1",
                        "action": "add",
                        "amount": 100,
                        "confidence": 0.7,
                        "executionEligible": True,
                        "section": "tactical_actions",
                        "decisionCutoff": "2026-05-20T14:55:00+08:00",
                        "modelRunScope": "pipeline",
                        "evidenceRefs": [{"kind": "news", "path": "raw/news/2026-05-20.json"}],
                        "supportingSignals": ["signal-a"],
                        "opposingSignals": ["signal-b"],
                        "policyHits": ["cash_floor"],
                        "constraintResults": ["pass"],
                        "executionState": "simulated_advice",
                    }
                ],
            },
        )

        page = OkraWebApi(self.agent.root).review_page(report_date)
        trace = page["review"]["decisionTrace"]

        self.assertTrue(trace["available"])
        self.assertEqual("action_debate_promoted", trace["source"])
        self.assertEqual(1, trace["decisionCount"])
        self.assertEqual(4, trace["evidenceCount"])
        self.assertEqual(1, trace["availableArtifactCount"])
        self.assertNotIn("sourceArtifacts", trace)
        visible = trace["decisions"][0]
        self.assertEqual("2026-05-20T14:55:00+08:00", visible["decisionCutoff"])
        self.assertEqual(["signal-a"], visible["supportingSignals"])
        self.assertEqual("raw/news/2026-05-20.json", visible["evidenceRefs"][0]["path"])

    def test_shadow_review_exposes_isolated_experiment_snapshot(self):
        initial = {
            "as_of_date": "2026-05-20",
            "total_value": 1000.0,
            "holding_pnl": 0.0,
            "funds": [
                {"fund_code": "CASH", "fund_name": "Cash", "role": "cash_hub", "current_value": 500.0, "cost_basis_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0},
                {"fund_code": "F1", "fund_name": "Fund 1", "role": "tactical", "current_value": 500.0, "cost_basis_value": 500.0, "holding_units": 500.0, "last_valuation_nav": 1.0},
            ],
        }
        create_experiment(self.agent.root, {"experimentId": "audit-exp", "label": "审计实验", "initialPortfolio": initial})
        record_action(self.agent.root, {"experimentId": "audit-exp", "actionId": "audit-buy", "action": "buy", "fundCode": "F1", "amount": 100})

        page = OkraWebApi(self.agent.root).shadow_review_page("2026-05-20")
        experiment = page["strategyExperiments"][0]

        self.assertEqual("audit-exp", experiment["experimentId"])
        self.assertEqual(1, experiment["actionCount"])
        self.assertEqual({"buy": 1}, experiment["actionCounts"])
        self.assertEqual(1000.0, experiment["totalValue"])
        self.assertEqual(0.0, experiment["valueDelta"])
        self.assertTrue(page["guardrails"]["nonExecutable"])
        self.assertFalse(page["guardrails"]["affectsPortfolio"])

    def test_review_quality_uses_outcomes_and_keeps_missing_metrics_explicit(self):
        report_date = "2026-05-20"
        self.agent.write_json(
            f"db/outcome_events/{report_date}__T_1.json",
            {
                "events": [
                    {"scoring_status": "scored", "outcome_label": "helped"},
                    {"scoring_status": "scored", "outcome_label": "hurt"},
                    {"scoring_status": "pending", "outcome_label": "not_scored"},
                ]
            },
        )
        self.agent.write_json(
            f"db/decision_traces/{report_date}.json",
            {"decisions": [{"abstentionReason": "证据不足"}, {"abstentionReason": ""}]},
        )
        upsert_memory_record(
            self.agent.root,
            {
                "memory_id": "quality-memory",
                "memory_type": "portfolio_policy_memory",
                "domain": "portfolio",
                "entity_key": "quality",
                "title": "Quality rule",
                "text": "Tracks a counterexample.",
                "status": "experimental_active",
                "contradiction_count": 2,
                "source": "replay_experiment",
                "metadata": {"experimentId": "quality-exp"},
            },
        )

        quality = OkraWebApi(self.agent.root).review_page(report_date)["review"]["quality"]

        self.assertEqual(2, quality["adviceQuality"]["scoredEventCount"])
        self.assertEqual(50.0, quality["adviceQuality"]["directionalAccuracyPct"])
        self.assertEqual(1, quality["adviceQuality"]["abstention"]["count"])
        self.assertFalse(quality["adviceQuality"]["confidenceCalibration"]["available"])
        self.assertEqual("user_simulation", quality["simulationQuality"]["track"])
        self.assertFalse(quality["simulationQuality"]["twr"].get("available", False))
        self.assertEqual("not_configured", quality["simulationQuality"]["benchmark"]["status"])
        self.assertEqual(2, quality["memoryQuality"]["contradictionCount"])
        self.assertEqual(1, quality["memoryQuality"]["sourceTrackCounts"]["strategy_simulation"])


if __name__ == "__main__":
    unittest.main()
