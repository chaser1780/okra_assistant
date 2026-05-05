from __future__ import annotations

import json
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None

from common import load_llm_config
from multiagent_utils import build_llm_session, consume_sse_response, describe_api_failure, extract_response_output_text, resolve_api_key


def call_copilot_llm(home: Path, context: str, question: str, evidence: dict) -> str:
    if requests is None:
        raise RuntimeError("requests is not installed")
    config = load_llm_config(home)
    provider = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config)
    system_prompt = (
        "你是 OKRA 长期记忆投资工作台的右侧智能助手。"
        "你的任务是基于本地页面数据、基金详情、长期记忆和证据链，用中文回答用户问题。"
        "只解释已有数据，不编造未提供的行情、净值、新闻或交易结论。"
        "如果证据不足，要直接说明缺少哪些数据。"
        "回答要面向实际投研工作流：先给结论，再给原因、风险、证据和下一步动作。"
        "不要输出 JSON，不要写免责声明套话，不要建议用户离开工作台查询。"
    )
    user_prompt = f"页面上下文：{context}\n用户问题：{question}\n\n本地证据数据：\n" + json.dumps(evidence, ensure_ascii=False, indent=2)
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
                provider["base_url"].rstrip("/") + "/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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
