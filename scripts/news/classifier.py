from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .normalizer import DEFAULT_CLASSIFIER_VERSION, impact_from_classification


NEGATIVE_KEYWORDS = ("风险", "下调", "离任", "清盘", "终止", "停牌", "处罚", "违约", "预警", "大幅回撤", "限制")
POSITIVE_KEYWORDS = ("分红", "增持", "上调", "获批", "成立", "开放", "扩募", "利好")
HIGH_RISK_KEYWORDS = ("风险", "清盘", "停牌", "处罚", "违约", "预警", "暂停", "排查", "调查", "减持", "离任")
POLICY_KEYWORDS = ("证监会", "发改委", "工信部", "财政部", "政策", "监管", "制度", "指引", "改革")
HYPE_KEYWORDS = ("热议", "热度", "爆了", "揭秘", "直播", "视频", "#", "短视频", "新声计划", "创作浪潮")

NEWS_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "index": {"type": "integer"}, "sentiment_label": {"type": "string", "enum": ["positive", "neutral", "negative", "mixed"]},
        "sentiment_score": {"type": "number"}, "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "risk_tags": {"type": "array", "items": {"type": "string"}}, "topic_tags": {"type": "array", "items": {"type": "string"}},
        "is_policy_signal": {"type": "boolean"}, "is_hype_signal": {"type": "boolean"}, "reason_short": {"type": "string"},
        "classification_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }, "required": ["index", "sentiment_label", "sentiment_score", "risk_level", "risk_tags", "topic_tags", "is_policy_signal", "is_hype_signal", "reason_short"]}}},
    "required": ["items"],
}


def rule_classify_news_item(item: dict[str, Any], *, classifier_version: str = DEFAULT_CLASSIFIER_VERSION) -> dict[str, Any]:
    title = str(item.get("title", "") or "")
    summary = str(item.get("summary", "") or "")
    source_name = str(item.get("source_name", "") or "")
    evidence_type = str(item.get("evidence_type", "") or "")
    joined = f"{title} {summary}"
    sentiment_label = "neutral"
    sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
    if any(keyword in joined for keyword in NEGATIVE_KEYWORDS):
        sentiment_label, sentiment_score = "negative", min(sentiment_score, -0.45) if sentiment_score else -0.45
    elif any(keyword in joined for keyword in POSITIVE_KEYWORDS):
        sentiment_label, sentiment_score = "positive", max(sentiment_score, 0.45) if sentiment_score else 0.45
    risk_level = "high" if any(keyword in joined for keyword in HIGH_RISK_KEYWORDS) or evidence_type == "official_notice" else "low"
    if risk_level != "high" and any(keyword in joined for keyword in POLICY_KEYWORDS):
        risk_level = "medium"
    risk_tags = ["event_risk"] if risk_level == "high" else []
    if any(keyword in joined for keyword in POLICY_KEYWORDS):
        risk_tags.append("policy")
    topic_tags = list({keyword for keyword in (item.get("matched_keywords", []) or []) if keyword})
    is_policy_signal = any(keyword in joined for keyword in POLICY_KEYWORDS)
    is_hype_signal = any(keyword in joined for keyword in HYPE_KEYWORDS)
    if is_hype_signal and risk_level == "low":
        risk_level = "medium"
    if source_name == "eastmoney_notice" and risk_level == "low":
        risk_level = "medium"
    return {
        "sentiment_label": sentiment_label, "sentiment_score": round(max(-1.0, min(1.0, sentiment_score)), 4),
        "risk_level": risk_level, "risk_tags": risk_tags, "topic_tags": topic_tags,
        "is_policy_signal": is_policy_signal, "is_hype_signal": is_hype_signal, "reason_short": "rule fallback",
        "classification_confidence": None, "classifier": "rule", "classifier_version": classifier_version,
        "classification_status": "rule_fallback", "impact": impact_from_classification(sentiment_label, risk_level),
    }


def build_classification_prompts(batch: list[dict[str, Any]]) -> tuple[str, str]:
    system_prompt = (
        "You classify Chinese finance news into structured portfolio-research signals. "
        "Return strict JSON only. Use title and summary only. Be conservative on positive sentiment. "
        "High risk is for enforcement, liquidation, suspension, termination, manager departure, major policy shock, or severe warning."
    )
    lines = [json.dumps({"index": index, "title": item.get("title", ""), "summary": item.get("summary", ""), "source_name": item.get("source_name", ""), "source_role": item.get("source_role", ""), "published_at": item.get("published_at", ""), "matched_keywords": item.get("matched_keywords", [])}, ensure_ascii=False) for index, item in enumerate(batch)]
    return system_prompt, "Classify each item. topic_tags and risk_tags should be short identifiers. Return one result per input index.\n" + "\n".join(lines)


def classify_news_with_llm(
    agent_home: Path,
    settings: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    report_date: str,
    call_json_agent: Callable[..., dict[str, Any]],
    provider_error_type: type[Exception],
    classifier_version: str = DEFAULT_CLASSIFIER_VERSION,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cfg = settings.get("providers", {}).get("news_classification", {}) or {}
    if not bool(cfg.get("enabled", True)) or not items:
        return items, {"enabled": bool(cfg.get("enabled", True)), "mode": "disabled", "status": "disabled", "llm_batches": 0, "fallback_batches": 0}
    batch_size, timeout_seconds = int(cfg.get("batch_size", 20) or 20), int(cfg.get("timeout_seconds", 45) or 45)
    model_override = str(cfg.get("model", "") or "").strip()
    llm_batches = fallback_batches = 0
    circuit_error = ""
    classified = [dict(item) for item in items]
    for start in range(0, len(classified), batch_size):
        batch = classified[start : start + batch_size]
        if circuit_error:
            fallback_batches += 1
            for item in batch: item.update(rule_classify_news_item(item, classifier_version=classifier_version))
            continue
        system_prompt, user_prompt = build_classification_prompts(batch)
        try:
            response = call_json_agent(agent_home, system_prompt, user_prompt, schema=NEWS_CLASSIFICATION_SCHEMA, max_attempts=1, reasoning_effort="medium", request_name="news_batch_classifier", text_verbosity="low", temperature=0.1, timeout=(10, timeout_seconds), model=model_override or None, report_date=report_date)
            result_items = {int(item.get("index", -1)): item for item in (response.get("response_json", {}) or {}).get("items", []) or []}
            model_run = response.get("model_run") or {}
            llm_batches += 1
            for index, item in enumerate(batch):
                parsed = result_items.get(index)
                if not parsed:
                    parsed = rule_classify_news_item(item, classifier_version=classifier_version)
                else:
                    parsed = {**parsed, "classifier": model_override or "llm", "classifier_version": classifier_version, "classification_status": "llm", "classifier_model_run_id": str(model_run.get("modelRunId") or ""), "classifier_prompt_version": str(model_run.get("promptVersion") or ""), "impact": impact_from_classification(str(parsed.get("sentiment_label", "neutral")), str(parsed.get("risk_level", "low")))}
                item.update(parsed)
        except Exception as exc:
            if isinstance(exc, provider_error_type) and not getattr(exc, "retryable", False): circuit_error = str(exc)
            fallback_batches += 1
            for item in batch: item.update(rule_classify_news_item(item, classifier_version=classifier_version))
    confidences = [float(item["classification_confidence"]) for item in classified if item.get("classification_confidence") not in (None, "")]
    model_run_ids = sorted({str(item.get("classifier_model_run_id") or "") for item in classified if str(item.get("classifier_model_run_id") or "")})
    return classified, {"enabled": True, "mode": str(cfg.get("mode", "llm_first") or "llm_first"), "status": "ok" if llm_batches and not fallback_batches else ("mixed" if llm_batches else "fallback_only"), "llm_batches": llm_batches, "fallback_batches": fallback_batches, "batch_size": batch_size, "model": model_override or "default", "circuit_open": bool(circuit_error), "error": circuit_error, "model_run_ids": model_run_ids, "reported_confidence_count": len(confidences), "mean_reported_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None}
