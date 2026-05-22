from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TempAgentHome
from rag_config import rag_agent_shadow_settings
from rag_index_store import upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument
from rag_eval import run_eval


class RagEvalTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _seed_context(self):
        self.agent.write_json(
            "db/llm_context/2026-05-20.json",
            {
                "analysis_date": "2026-05-20",
                "generated_at": "2026-05-20T15:00:00+08:00",
                "funds": [{"fund_code": "F1", "fund_name": "Fund One", "role": "tactical", "style_group": "growth"}],
                "evidence_items": [
                    {
                        "evidence_id": "ev-1",
                        "entity_type": "fund",
                        "entity_id": "F1",
                        "evidence_type": "quote_snapshot",
                        "source_role": "fund_news",
                        "source_tier": "daily_evidence",
                        "summary": "F1 risk is valuation pressure.",
                        "as_of": "2026-05-20",
                        "retrieved_at": "2026-05-20T15:00:00+08:00",
                    }
                ],
                "fund_evidence_map": {"F1": [{"evidence_id": "ev-1"}]},
            },
        )
        self.agent.run_script("build_evidence_index.py", "--date", "2026-05-20")

    def _seed_rag(self):
        doc = RagDocument(
            doc_id="rag-f1",
            source_kind="evidence_item",
            source_path="db/llm_context/2026-05-20.json",
            source_record_id="ev-1",
            title="F1 valuation risk",
            summary="F1 risk is valuation pressure.",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="fund",
            source_tier="daily_evidence",
            visibility="default",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
            payload={"evidence_id": "ev-1", "risk": "valuation"},
        )
        chunk = RagChunk(
            chunk_id="rag-f1:chunk:0",
            doc_id="rag-f1",
            chunk_index=0,
            text_for_embedding="F1 valuation pressure risk",
            text_for_llm="F1 risk is valuation pressure.",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])

    def test_agent_shadow_defaults_to_disabled(self):
        settings = rag_agent_shadow_settings(self.agent.root)
        self.assertFalse(settings["enabled"])
        self.assertFalse(settings["inject_into_prompt"])
        self.assertTrue(settings["compare_legacy"])

    def test_rag_eval_writes_legacy_comparison_artifact(self):
        self._seed_context()
        self._seed_rag()
        payload = run_eval(self.agent.root, "2026-05-20", compare_legacy=True, write_trace=False)
        output_path = Path(payload["output_path"])
        self.assertTrue(output_path.exists())
        written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertTrue(written["legacy"]["available"])
        self.assertIn("market_analyst", written["agents"])
        first_query = written["agents"]["market_analyst"]["queries"][0]
        self.assertIn("trace_id", first_query)
        self.assertEqual(0, written["metrics"].get("no_future_violation_count", 0))


if __name__ == "__main__":
    unittest.main()
