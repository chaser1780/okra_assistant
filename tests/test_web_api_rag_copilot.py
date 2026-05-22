from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.web_api import OkraWebApi
from helpers import TempAgentHome
from rag_index_store import upsert_chunks, upsert_documents
from rag_models import RagChunk, RagDocument


RAG_ENABLED_TOML = """[rag]
enabled = true
default_profile = "copilot_qa"
trace_enabled = true
fallback_to_legacy = true

[rag.sources]
long_memory = true
portfolio_state = true
llm_context = true
evidence_index = true
validated_advice = true
committee_bundle = true
agent_outputs = false
execution_sync = false
raw_news = false
"""

RAG_ENABLED_WITH_EXECUTION_TOML = """[rag]
enabled = true
default_profile = "copilot_qa"
trace_enabled = true
fallback_to_legacy = true

[rag.sources]
long_memory = true
portfolio_state = true
llm_context = true
evidence_index = true
validated_advice = true
committee_bundle = true
agent_outputs = false
execution_sync = true
raw_news = false
"""


class WebApiRagCopilotTests(unittest.TestCase):
    def setUp(self):
        self.agent = TempAgentHome()

    def tearDown(self):
        self.agent.cleanup()

    def _insert_rag_doc(self, *, doc_id: str = "doc-f1", source_kind: str = "validated_advice") -> None:
        doc = RagDocument(
            doc_id=doc_id,
            source_kind=source_kind,
            source_path="db/validated_advice/2026-05-20.json",
            source_record_id="tactical_actions:F1",
            title="F1 validated action",
            summary="F1 risk comes from valuation pressure and weak same-day signal.",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="fund",
            source_tier="decision_trace",
            visibility="default",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
            payload={"fund_code": "F1", "validated_action": "hold", "risk_score": 0.72},
            metadata={"section": "tactical_actions", "confidence": 0.8},
        )
        chunk = RagChunk(
            chunk_id=f"{doc.doc_id}:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding="F1 risk valuation weak signal",
            text_for_llm="F1 risk comes from valuation pressure and weak same-day signal.",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])

    def _insert_execution_doc(self) -> None:
        doc = RagDocument(
            doc_id="exec-doc-f1",
            source_kind="execution_sync",
            source_path="db/execution_sync/actual_trades/2026-05-20.json",
            source_record_id="actual_trade:trade-1",
            title="Execution actual trade F1",
            summary="F1 actual trade is pending confirmation.",
            as_of_date="2026-05-20",
            available_from="2026-05-20T15:00:00+08:00",
            domain="execution",
            source_tier="execution_structured_summary",
            visibility="execution_only",
            entity_type="fund",
            entity_id="F1",
            fund_codes=["F1"],
            learning_scope="execution_only",
            payload={"trade_id": "trade-1", "fund_code": "F1", "status": "submitted"},
            metadata={"source_kind": "execution_sync", "execution_record_kind": "actual_trade"},
        )
        chunk = RagChunk(
            chunk_id="exec-doc-f1:chunk:0",
            doc_id=doc.doc_id,
            chunk_index=0,
            text_for_embedding="F1 actual trade pending confirmation",
            text_for_llm="F1 actual trade is pending confirmation.",
        )
        upsert_documents(self.agent.root, [doc])
        upsert_chunks(self.agent.root, [chunk])

    def test_rag_disabled_keeps_legacy_copilot_path(self):
        api = OkraWebApi(self.agent.root)
        with patch.object(api, "_call_copilot_llm", return_value="legacy answer") as call_llm:
            result = api.explain({"context": "today", "question": "F1 今天有什么风险？", "page": "today", "selectedDate": "2026-05-20"})
        self.assertEqual("llm", result["mode"])
        self.assertEqual("legacy answer", result["answer"])
        evidence = call_llm.call_args.args[2]
        self.assertNotEqual("copilot_rag_pack", evidence.get("kind"))
        self.assertIn("pageData", evidence)

    def test_general_chat_does_not_force_rag_when_rag_enabled(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with (
            patch.object(api, "_build_copilot_rag_pack") as build_rag,
            patch.object(api, "_call_copilot_llm", return_value="general answer") as call_llm,
        ):
            result = api.explain(
                {
                    "context": "当前页面：今日。查看日期：2026-05-20",
                    "question": "你能简单解释一下什么是夏普比率吗？",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                }
            )

        build_rag.assert_not_called()
        self.assertEqual("llm", result["mode"])
        self.assertEqual("general_chat", result["retrieval"]["intent"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("general_chat", evidence["kind"])

    def test_general_investment_concept_does_not_force_rag(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with (
            patch.object(api, "_build_copilot_rag_pack") as build_rag,
            patch.object(api, "_call_copilot_llm", return_value="concept answer") as call_llm,
        ):
            result = api.explain(
                {
                    "context": "当前页面：今日。查看日期：2026-05-20",
                    "question": "红利基金和成长基金有什么区别？",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                }
            )

        build_rag.assert_not_called()
        self.assertEqual("llm", result["mode"])
        self.assertEqual("general_chat", result["retrieval"]["intent"])
        self.assertEqual("general_chat", call_llm.call_args.args[2]["kind"])

    def test_fund_detail_page_general_question_does_not_force_rag(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with (
            patch.object(api, "_build_copilot_rag_pack") as build_rag,
            patch.object(api, "_call_copilot_llm", return_value="concept answer") as call_llm,
        ):
            result = api.explain(
                {
                    "context": "当前页面：基金详情。查看日期：2026-05-20",
                    "question": "什么是最大回撤？",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )

        build_rag.assert_not_called()
        self.assertEqual("llm", result["mode"])
        self.assertEqual("general_chat", result["retrieval"]["intent"])
        self.assertEqual("general_chat", call_llm.call_args.args[2]["kind"])

    def test_fund_detail_contextual_question_uses_current_fund_rag(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)

        with patch.object(api, "_call_copilot_llm", return_value="current fund answer [C1]") as call_llm:
            result = api.explain(
                {
                    "context": "当前页面：基金详情。查看日期：2026-05-20",
                    "question": "这只基金今天有什么风险？",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )

        self.assertEqual("rag_llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("copilot_rag_pack", evidence["kind"])
        self.assertEqual(["F1"], evidence["query_plan"]["fund_codes"])

    def test_okra_question_triggers_rag_when_rag_enabled(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)

        with patch.object(api, "_call_copilot_llm", return_value="okra answer [C1]") as call_llm:
            result = api.explain(
                {
                    "context": "当前页面：今日。查看日期：2026-05-20",
                    "question": "OKRA 里 F1 这只基金今天有什么风险？",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                }
            )

        self.assertEqual("rag_llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("copilot_rag_pack", evidence["kind"])

    def test_explicit_fund_code_triggers_rag(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)

        with patch.object(api, "_call_copilot_llm", return_value="F1 answer [C1]") as call_llm:
            result = api.explain(
                {
                    "context": "当前页面：今日。查看日期：2026-05-20",
                    "question": "F1 今天怎么看？",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                }
            )

        self.assertEqual("rag_llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("copilot_rag_pack", evidence["kind"])

    def test_use_rag_flag_can_force_general_question_into_rag(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)

        with patch.object(api, "_call_copilot_llm", return_value="forced rag [C1]") as call_llm:
            result = api.explain(
                {
                    "context": "today",
                    "question": "请结合本地资料回答这个问题",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                    "useRag": True,
                }
            )

        self.assertEqual("rag_llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("copilot_rag_pack", evidence["kind"])

    def test_rag_enabled_returns_trace_citations_and_retrieval(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)

        def fake_llm(context: str, question: str, evidence: dict) -> str:
            self.assertEqual("copilot_rag_pack", evidence["kind"])
            self.assertEqual("F1", evidence["query_plan"]["fund_codes"][0])
            self.assertEqual("C1", evidence["citations"][0]["id"])
            return "RAG answer [C1]"

        with patch.object(api, "_call_copilot_llm", side_effect=fake_llm):
            result = api.explain(
                {
                    "context": "fund detail",
                    "question": "F1 risk?",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                    "messages": [
                        {"role": "user", "content": "前一问"},
                        {"role": "assistant", "content": "前一答"},
                        {"role": "user", "content": "F1 risk?"},
                    ],
                }
            )
        self.assertEqual("rag_llm", result["mode"])
        self.assertEqual("RAG answer [C1]", result["answer"])
        self.assertTrue(result["traceId"].startswith("ragq_"))
        self.assertEqual("C1", result["citations"][0]["id"])
        self.assertEqual("fund_explain", result["retrieval"]["intent"])
        self.assertEqual(1, result["retrieval"]["hitCount"])
        self.assertEqual([], result["retrieval"]["missingData"])

    def test_rag_build_failure_falls_back_to_legacy_evidence(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with (
            patch.object(api, "_build_copilot_rag_pack", side_effect=RuntimeError("rag broke")),
            patch.object(api, "_call_copilot_llm", return_value="legacy after rag failure") as call_llm,
        ):
            result = api.explain({"context": "today", "question": "OKRA 里 F1 今天有什么风险？", "page": "today", "selectedDate": "2026-05-20"})
        self.assertEqual("llm", result["mode"])
        self.assertEqual("legacy after rag failure", result["answer"])
        self.assertEqual("rag broke", result["ragFallbackReason"])
        evidence = call_llm.call_args.args[2]
        self.assertIn("pageData", evidence)

    def test_conversation_messages_are_passed_to_rag_llm(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        messages = [
            {"role": "user", "content": "先看 F1"},
            {"role": "assistant", "content": "F1 主要看估值压力。"},
            {"role": "user", "content": "继续说风险"},
        ]

        with patch.object(api, "_call_copilot_llm", return_value="RAG chat answer") as call_llm:
            result = api.explain(
                {
                    "context": "fund detail",
                    "question": "继续说风险",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                    "messages": messages,
                }
            )

        self.assertEqual("rag_llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertEqual("copilot_rag_pack", evidence["kind"])
        self.assertEqual(messages, evidence["conversationMessages"])

    def test_conversation_messages_are_passed_to_legacy_fallback(self):
        api = OkraWebApi(self.agent.root)
        messages = [
            {"role": "user", "content": "前一问"},
            {"role": "assistant", "content": "前一答"},
            {"role": "user", "content": "继续"},
        ]

        with patch.object(api, "_call_copilot_llm", return_value="legacy chat answer") as call_llm:
            result = api.explain(
                {
                    "context": "today",
                    "question": "继续",
                    "page": "today",
                    "selectedDate": "2026-05-20",
                    "messages": messages,
                }
            )

        self.assertEqual("llm", result["mode"])
        evidence = call_llm.call_args.args[2]
        self.assertNotEqual("copilot_rag_pack", evidence.get("kind"))
        self.assertEqual(messages, evidence["conversationMessages"])

    def test_rag_llm_failure_returns_local_summary_with_trace(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        self._insert_rag_doc()
        api = OkraWebApi(self.agent.root)
        with patch.object(api, "_call_copilot_llm", side_effect=RuntimeError("llm offline")):
            result = api.explain(
                {
                    "context": "fund detail",
                    "question": "F1 risk?",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )
        self.assertEqual("local_fallback", result["mode"])
        self.assertTrue(result["traceId"].startswith("ragq_"))
        self.assertIn("[C1]", result["answer"])
        self.assertEqual(1, result["retrieval"]["hitCount"])

    def test_normal_copilot_query_excludes_execution_even_when_source_enabled(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_WITH_EXECUTION_TOML)
        self._insert_execution_doc()
        api = OkraWebApi(self.agent.root)
        with patch.object(api, "_call_copilot_llm", return_value="no execution") as call_llm:
            result = api.explain(
                {
                    "context": "fund detail",
                    "question": "F1 的真实交易和实际执行风险是什么？",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )
        self.assertEqual("llm", result["mode"])
        self.assertEqual("hit_count_below_min", result["ragFallbackReason"])
        evidence = call_llm.call_args.args[2]
        self.assertNotEqual("copilot_rag_pack", evidence.get("kind"))
        self.assertIn("pageData", evidence)

    def test_rag_zero_hits_falls_back_to_legacy_evidence(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with patch.object(api, "_call_copilot_llm", return_value="legacy zero hit") as call_llm:
            result = api.explain(
                {
                    "context": "fund detail",
                    "question": "F1 risk?",
                    "page": "fundDetail",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )
        self.assertEqual("llm", result["mode"])
        self.assertEqual("hit_count_below_min", result["ragFallbackReason"])
        evidence = call_llm.call_args.args[2]
        self.assertIn("pageData", evidence)
        self.assertNotEqual("copilot_rag_pack", evidence.get("kind"))

    def test_empty_question_is_rejected_in_legacy_path(self):
        api = OkraWebApi(self.agent.root)
        with self.assertRaisesRegex(ValueError, "question is required"):
            api.explain({"context": "today", "question": "", "page": "today", "selectedDate": "2026-05-20"})

    def test_empty_question_is_rejected_before_rag_fallback(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_TOML)
        api = OkraWebApi(self.agent.root)
        with self.assertRaisesRegex(ValueError, "question is required"):
            api.explain({"context": "today", "question": "", "page": "today", "selectedDate": "2026-05-20", "fundCode": "F1"})

    def test_execution_copilot_query_uses_execution_profile(self):
        self.agent.write_text("config/rag.toml", RAG_ENABLED_WITH_EXECUTION_TOML)
        self._insert_execution_doc()
        api = OkraWebApi(self.agent.root)

        def fake_llm(context: str, question: str, evidence: dict) -> str:
            self.assertTrue(evidence["query_plan"]["include_execution"])
            self.assertEqual("execution", evidence["query_plan"]["retrieval_profile"])
            self.assertEqual("pending_confirmation", evidence["query_plan"]["intent"])
            self.assertEqual(["execution"], evidence["query_plan"]["domains"])
            self.assertEqual("execution_sync", evidence["citations"][0]["sourceKind"])
            return "execution answer [C1]"

        with patch.object(api, "_call_copilot_llm", side_effect=fake_llm):
            result = api.explain(
                {
                    "context": "execution",
                    "question": "F1 待确认交易为什么还没确认？",
                    "page": "execution",
                    "selectedDate": "2026-05-20",
                    "fundCode": "F1",
                }
            )
        self.assertEqual("rag_llm", result["mode"])
        self.assertEqual("pending_confirmation", result["retrieval"]["intent"])
        self.assertEqual(1, result["retrieval"]["hitCount"])


if __name__ == "__main__":
    unittest.main()
