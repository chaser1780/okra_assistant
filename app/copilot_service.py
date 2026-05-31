from __future__ import annotations

import json
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None

from common import load_llm_config
from multiagent_utils import build_llm_session, consume_sse_response, describe_api_failure, extract_response_output_text, resolve_api_key, responses_endpoint, responses_headers


def _conversation_history(evidence: dict) -> list[dict[str, str]]:
    raw_messages = evidence.get("conversationMessages", []) if isinstance(evidence, dict) else []
    if not isinstance(raw_messages, list):
        return []
    messages: list[dict[str, str]] = []
    for item in raw_messages[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content[:4000]})
    return messages


def call_copilot_llm(home: Path, context: str, question: str, evidence: dict) -> str:
    if requests is None:
        raise RuntimeError("requests is not installed")
    config = load_llm_config(home)
    provider = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config, home)
    is_rag_pack = isinstance(evidence, dict) and evidence.get("kind") == "copilot_rag_pack"
    is_general_chat = isinstance(evidence, dict) and evidence.get("kind") == "general_chat"
    history = _conversation_history(evidence)
    history_text = json.dumps(history, ensure_ascii=False, indent=2) if history else "[]"
    system_prompt = (
        "你是 OKRA 智能问答助手。默认作为通用大模型自然回答用户问题，可以使用你的通用知识、推理能力和对话上下文。"
        "当提供 OKRA 本地证据、RAG evidence pack 或页面数据时，说明它们只代表用户本地工作台信息；涉及具体持仓、基金、交易、系统建议或历史决策时必须优先依据这些证据。"
        "如果问题只是概念解释、方法讨论、普通聊天或通用知识，不要强行绑定 OKRA 数据。"
        "涉及具体投资判断时，不要编造净值、收益、新闻、持仓、交易状态或执行结论；证据不足就说明缺口，并可以给通用分析框架。"
        "回答要自然、直接，不要输出 JSON，不要写泛泛免责声明。"
    )
    user_prompt = (
        f"当前页面上下文：{context}\n"
        f"最近对话历史：\n{history_text}\n"
        f"用户当前问题：{question}\n\n"
        "可用上下文数据：\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )
    if is_general_chat:
        user_prompt = (
            f"当前页面上下文：{context}\n"
            f"最近对话历史：\n{history_text}\n"
            f"用户当前问题：{question}\n\n"
            "本轮没有触发 OKRA RAG 检索。请按通用智能助手方式回答；只有用户明确要求 OKRA、基金、持仓、交易或本地决策数据时，才提示需要查询本地证据。"
        )
    if is_rag_pack:
        system_prompt = (
            "你是 OKRA 智能问答助手。用中文自然对话回答用户，不要表现得像固定模板。"
            "优先使用提供的 RAG evidence pack 和 structuredFacts；引用证据时使用 [C1]、[C2]。"
            "如果 RAG 缺少 validated advice、portfolio state、market/news evidence 或同日数据，要明确指出缺口。"
            "stale 证据必须标明过期或延迟；archived/rejected memory 只能作为历史反例。"
            "不要编造净值、收益、新闻、持仓、交易状态或执行结论。"
            "回答要先给可执行结论，再说明依据、风险和下一步。不要输出 JSON。"
        )
    request_payload = {
        "model": config["model"],
        "stream": True,
        "store": False,
        "reasoning": {"effort": config.get("model_reasoning_effort", "high")},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {"verbosity": "medium"},
        "max_output_tokens": 1400,
    }
    last_error = None
    for transport_name, use_env_proxy in (("direct", False), ("env_proxy", True)):
        session = build_llm_session(use_env_proxy=use_env_proxy)
        try:
            with session.post(
                responses_endpoint(provider),
                headers=responses_headers(api_key, stream=True),
                json=request_payload,
                timeout=(10, 45),
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(describe_api_failure(response.status_code, response.text[:800], "copilot", transport_name))
                parsed = consume_sse_response(response)
            completed = parsed.get("completed_event") or {}
            if isinstance(completed, dict) and completed.get("response"):
                text = extract_response_output_text(completed["response"]).strip()
            else:
                text = extract_response_output_text(completed).strip()
            if not text:
                text = str(parsed.get("output_text", "") or "").strip()
            if text:
                return text
            failed_event = parsed.get("failed_event") or parsed.get("error_event")
            raise RuntimeError(json.dumps(failed_event, ensure_ascii=False) if failed_event else "LLM response did not contain output text.")
        except Exception as exc:
            last_error = exc
        finally:
            session.close()
    raise RuntimeError(f"助手 LLM 请求失败：{last_error}")


def local_copilot_answer(context: str, question: str, evidence: dict, error: str) -> str:
    if isinstance(evidence, dict) and evidence.get("kind") == "general_chat":
        return "\n".join(
            [
                "这次没有成功连接 LLM，且本轮问题没有触发 OKRA 本地 RAG 检索。",
                "",
                f"问题：{question}",
                "",
                "请稍后重试；如果你问的是具体基金、持仓、交易或系统决策，我会在可用时结合本地证据回答。",
                "",
                f"LLM 调用失败原因：{error[:500]}",
            ]
        )

    if isinstance(evidence, dict) and evidence.get("kind") == "copilot_rag_pack":
        citations = list(evidence.get("citations", []) or [])
        retrieval = evidence.get("retrieval", {}) if isinstance(evidence.get("retrieval"), dict) else {}
        source_date = evidence.get("sourceDate", "")
        lines = [
            "已检索到 RAG 证据，但这次没有成功连接 LLM。以下是本地证据摘要。",
            "",
            f"页面：{context}",
            f"日期：{source_date or '未知'}",
            f"问题：{question}",
            f"Trace：{evidence.get('traceId', '') or '未知'}",
            "",
            "检索：",
            f"- 命中数：{retrieval.get('hitCount', len(citations))}",
        ]
        missing = retrieval.get("missingData") or evidence.get("missingData") or []
        if missing:
            lines.append(f"- 缺失数据：{json.dumps(missing, ensure_ascii=False)[:500]}")
        lines.extend(["", "证据："])
        for item in citations[:5]:
            if not isinstance(item, dict):
                continue
            stale = " (stale)" if item.get("stale") else ""
            lines.append(
                f"- [{item.get('id', '')}] {item.get('title', '')}{stale} "
                f"{item.get('sourceKind', '')} {item.get('asOfDate', '')}: {item.get('summary', '')}"
            )
        if not citations:
            lines.append("- 没有可用证据。")
        lines.extend(["", f"LLM 调用失败原因：{error[:500]}"])
        return "\n".join(lines)

    page_data = evidence.get("pageData", {}) if isinstance(evidence, dict) else {}
    summary = evidence.get("summary", {}) if isinstance(evidence, dict) else {}
    metrics = page_data.get("metrics", []) if isinstance(page_data, dict) else []
    metric_lines = []
    for item in metrics[:4]:
        if isinstance(item, dict):
            metric_lines.append(f"- {item.get('title', '')}: {item.get('value', '')} {item.get('body', '')}".strip())
    if not metric_lines and isinstance(page_data, dict):
        for key in ("focus_text", "summary_text", "detail_text", "committee_text"):
            value = str(page_data.get(key, "") or "").strip()
            if value:
                metric_lines.append(f"- {value[:160]}")
    source_date = evidence.get("selectedDate", "")
    lines = [
        "我已经读取了当前页面的本地数据，但这次没有成功连接 LLM，所以先给出本地证据摘要。",
        "",
        f"页面：{context}",
        f"日期：{source_date or '暂无'}",
        f"问题：{question}",
        "",
        "当前可见证据：",
        *(metric_lines or ["- 当前页面没有足够的结构化摘要。"]),
    ]
    if summary:
        lines.extend(["", f"状态摘要：{json.dumps(summary, ensure_ascii=False)[:500]}"])
    lines.extend(["", f"LLM 调用失败原因：{error[:500]}"])
    return "\n".join(lines)
