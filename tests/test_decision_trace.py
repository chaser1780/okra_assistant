from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from decision_trace import build_decision_trace, write_decision_trace  # noqa: E402
from model_run_store import list_model_runs, write_model_run  # noqa: E402


class DecisionTraceTests(unittest.TestCase):
    def test_model_run_is_redacted_and_trace_links_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report_date = "2026-08-27"
            (home / "db" / "validated_advice").mkdir(parents=True)
            (home / "db" / "llm_context").mkdir(parents=True)
            (home / "db" / "llm_raw").mkdir(parents=True)
            (home / "db" / "action_tickets").mkdir(parents=True)
            (home / "db" / "retrieval_packs").mkdir(parents=True)
            (home / "db" / "action_debates").mkdir(parents=True)
            (home / "db" / "validated_advice" / f"{report_date}.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-08-27T15:00:00+08:00",
                        "decision_cutoff": "2026-08-27T14:55:00+08:00",
                        "decision_source": "action_debate_promoted",
                        "execution_eligible": True,
                        "tactical_actions": [
                            {
                                "suggestion_id": "decision-1",
                                "fund_code": "F1",
                                "fund_name": "Fund 1",
                                "validated_action": "add",
                                "validated_amount": 100,
                                "evidence": ["signal-a"],
                                "risks": ["risk-a"],
                                "policy_rule_hits": ["cash_floor"],
                            }
                        ],
                        "dca_actions": [],
                        "hold_actions": [],
                    }
                ),
                encoding="utf-8",
            )
            for name in ("llm_context", "llm_raw", "action_tickets", "retrieval_packs", "action_debates"):
                (home / "db" / name / f"{report_date}.json").write_text("{}", encoding="utf-8")
            run = write_model_run(
                home,
                config={"model_provider": "OpenAI", "model_providers": {"OpenAI": {"wire_api": "responses"}}, "model": "test-model"},
                request_name="agent_test",
                request_payload={"model": "test-model", "input": [{"role": "user", "content": "private prompt"}]},
                status="ok",
                latency_ms=12,
                output_text="private answer",
                report_date=report_date,
            )
            trace_path = write_decision_trace(home, report_date)
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            stored_runs = list_model_runs(home, report_date)

        self.assertTrue(run["inputSnapshotHash"])
        self.assertNotIn("private prompt", json.dumps(run, ensure_ascii=False))
        self.assertEqual(1, len(stored_runs))
        self.assertEqual("user_simulation", trace["formalTrack"])
        self.assertEqual("decision-1", trace["decisions"][0]["decisionId"])
        self.assertTrue(trace["sourceArtifacts"]["validatedAdvice"]["exists"])
        self.assertEqual("2026-08-27T14:55:00+08:00", trace["decisionCutoff"])
        self.assertEqual("2026-08-27T14:55:00+08:00", trace["decisions"][0]["decisionCutoff"])
        self.assertEqual("unavailable", trace["decisions"][0]["modelRunScope"])

    def test_missing_artifacts_remain_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = build_decision_trace(Path(tmp), "2026-08-27")
        self.assertEqual([], trace["decisions"])
        self.assertFalse(trace["sourceArtifacts"]["validatedAdvice"]["exists"])


if __name__ == "__main__":
    unittest.main()
