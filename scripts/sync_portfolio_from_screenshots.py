from __future__ import annotations

import argparse
import base64
import difflib
import io
import json
import re
from copy import deepcopy
from pathlib import Path

import requests
from PIL import Image, ImageOps

from common import (
    dump_json,
    ensure_layout,
    load_llm_config,
    load_benchmark_mappings,
    load_portfolio,
    load_strategy,
    load_watchlist,
    portfolio_import_dir,
    portfolio_definition_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)
from multiagent_utils import describe_api_failure, extract_response_output_text, resolve_api_key
from portfolio_state import ensure_portfolio_definition, save_portfolio_state


SCREENSHOT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "provider": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "display_name": {"type": "string"},
                    "current_value": {"type": "number"},
                    "daily_pnl": {"type": ["number", "null"]},
                    "holding_pnl": {"type": ["number", "null"]},
                    "holding_return_pct": {"type": ["number", "null"]},
                    "page_index": {"type": "integer"},
                    "row_index": {"type": "integer"},
                },
                "required": [
                    "display_name",
                    "current_value",
                    "daily_pnl",
                    "holding_pnl",
                    "holding_return_pct",
                    "page_index",
                    "row_index",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["provider", "items", "warnings"],
}


def safe_float(value) -> float | None:
    try:
        if value in (None, "", "--"):
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def safe_portfolio_definition(agent_home: Path, portfolio: dict) -> dict:
    try:
        return ensure_portfolio_definition(agent_home)
    except Exception:
        return {
            "portfolio_name": portfolio.get("portfolio_name", ""),
            "base_as_of_date": portfolio.get("as_of_date", ""),
            "funds": [
                {
                    **{key: deepcopy(value) for key, value in fund.items() if key not in {"current_value", "holding_pnl", "holding_return_pct", "holding_units", "cost_basis_value", "last_valuation_nav", "last_valuation_date", "last_official_nav", "last_official_nav_date", "units_source"}},
                    "opening_state": {
                        "current_value": float(fund.get("current_value", 0.0) or 0.0),
                        "holding_pnl": float(fund.get("holding_pnl", 0.0) or 0.0),
                        "holding_return_pct": float(fund.get("holding_return_pct", 0.0) or 0.0),
                        "holding_units": float(fund.get("holding_units", 0.0) or 0.0),
                        "cost_basis_value": float(fund.get("cost_basis_value", 0.0) or 0.0),
                        "last_valuation_nav": fund.get("last_valuation_nav"),
                        "last_valuation_date": fund.get("last_valuation_date", ""),
                        "last_official_nav": fund.get("last_official_nav"),
                        "last_official_nav_date": fund.get("last_official_nav_date", ""),
                        "units_source": fund.get("units_source", ""),
                    },
                }
                for fund in portfolio.get("funds", []) or []
            ],
        }


def sanitize_timestamp(value: str) -> str:
    return value.replace(":", "-").replace("+", "_")


def preview_output_path(agent_home: Path, sync_date: str) -> Path:
    stamp = sanitize_timestamp(timestamp_now())
    return portfolio_import_dir(agent_home) / f"{sync_date}_{stamp}_preview.json"


def applied_output_path(agent_home: Path, sync_date: str) -> Path:
    stamp = sanitize_timestamp(timestamp_now())
    return portfolio_import_dir(agent_home) / f"{sync_date}_{stamp}_applied.json"


def normalize_fund_name(text: str) -> str:
    current = str(text or "").strip().lower()
    for token in ("发起式", "人民币", "基金份额", "基金", "混合型"):
        current = current.replace(token, "")
    current = (
        current.replace("（", "(")
        .replace("）", ")")
        .replace("－", "-")
        .replace("—", "-")
        .replace(" ", "")
    )
    current = re.sub(r"[\s\-_·,，.:：/]+", "", current)
    return current


def data_url_for_image(path: Path, *, max_side: int = 1600) -> str:
    image = Image.open(path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        scale = max_side / float(longest)
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def call_screenshot_vision(agent_home: Path, image_paths: list[Path], provider: str) -> dict:
    config = load_llm_config(agent_home)
    provider_cfg = config["model_providers"][config["model_provider"]]
    api_key = resolve_api_key(config)
    endpoint = provider_cfg["base_url"].rstrip("/") + "/responses"
    content = [
        {
            "type": "input_text",
            "text": (
                "请从这些支付宝基金持仓截图中抽取可见持仓列表。"
                "忽略顶部标题、时间、电量、tab、广告卡片、资讯推荐、底部导航。"
                "只抽取真正的基金持仓行。"
                "current_value 是中间的大金额。"
                "daily_pnl 是中间金额下方的红绿小数字。"
                "holding_pnl 和 holding_return_pct 是右侧红绿数字与百分比。"
                "page_index 按图片顺序从 1 开始，row_index 按每页从上到下从 1 开始。"
                "不要猜基金代码、份额、净值。"
                "若某字段看不清，填 null。"
                "若同一基金因截图重叠出现多次，只保留一次更完整的记录。"
            ),
        }
    ]
    for index, path in enumerate(image_paths, start=1):
        content.append({"type": "input_text", "text": f"第 {index} 张图片：{path.name}"})
        content.append({"type": "input_image", "image_url": data_url_for_image(path)})

    payload = {
        "model": config["model"],
        "stream": False,
        "store": False,
        "reasoning": {"effort": config.get("model_reasoning_effort", "medium")},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "你是支付宝基金持仓截图结构化抽取器。"
                            "你只做视觉抽取，不做投资分析。"
                            "只返回严格 JSON。"
                        ),
                    }
                ],
            },
            {"role": "user", "content": content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "portfolio_screenshot_extract",
                "schema": SCREENSHOT_SCHEMA,
                "strict": True,
            },
            "verbosity": "low",
        },
        "max_output_tokens": 2200,
    }

    last_error = None
    for transport_name, use_env_proxy in (("direct", False), ("env_proxy", True)):
        session = requests.Session()
        session.trust_env = use_env_proxy
        try:
            response = session.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(30, 300),
            )
            if response.status_code >= 400:
                raise RuntimeError(describe_api_failure(response.status_code, response.text[:800], "portfolio screenshot", transport_name))
            result = response.json()
            output_text = extract_response_output_text(result).strip()
            if not output_text:
                raise RuntimeError(f"Vision response did not contain output text ({transport_name}).")
            parsed = json.loads(output_text)
            parsed["_transport_name"] = transport_name
            return parsed
        except Exception as exc:
            last_error = exc
        finally:
            session.close()
    raise RuntimeError(f"Screenshot vision request failed: {last_error}")


def dedupe_detected_holdings(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in sorted(items or [], key=lambda row: (int(row.get("page_index", 0)), int(row.get("row_index", 0)))):
        key = normalize_fund_name(item.get("display_name", ""))
        if not key:
            continue
        current = dict(item)
        existing = merged.get(key)
        if existing is None:
            merged[key] = current
            continue
        existing_score = sum(existing.get(field) is not None for field in ("daily_pnl", "holding_pnl", "holding_return_pct"))
        current_score = sum(current.get(field) is not None for field in ("daily_pnl", "holding_pnl", "holding_return_pct"))
        if current_score > existing_score:
            merged[key] = current
    return list(merged.values())


def build_match_candidates(agent_home: Path) -> list[dict]:
    portfolio = load_portfolio(agent_home)
    try:
        definition = ensure_portfolio_definition(agent_home)
    except Exception:
        definition = {"funds": []}
    watchlist = load_watchlist(agent_home).get("funds", []) or []
    benchmark_mappings = (load_benchmark_mappings(agent_home).get("fund_benchmarks", {}) or {})
    candidates: list[dict] = []
    seen_codes: set[str] = set()

    for fund in portfolio.get("funds", []) or []:
        code = str(fund.get("fund_code", "")).strip()
        if not code:
            continue
        seen_codes.add(code)
        candidates.append(
            {
                "fund_code": code,
                "fund_name": fund.get("fund_name", ""),
                "source": "portfolio",
                "in_portfolio": True,
                "category": fund.get("category", ""),
                "benchmark": fund.get("benchmark", ""),
                "style_group": fund.get("style_group", ""),
                "role": fund.get("role", ""),
                "proxy_symbol": fund.get("proxy_symbol", ""),
                "proxy_name": fund.get("proxy_name", ""),
            }
        )

    for item in definition.get("funds", []) or []:
        code = str(item.get("fund_code", "")).strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidates.append(
            {
                "fund_code": code,
                "fund_name": item.get("fund_name", ""),
                "source": "definition",
                "in_portfolio": False,
                "category": item.get("category", ""),
                "benchmark": item.get("benchmark", ""),
                "style_group": item.get("style_group", ""),
                "role": item.get("role", ""),
                "proxy_symbol": item.get("proxy_symbol", ""),
                "proxy_name": item.get("proxy_name", ""),
                "definition_item": deepcopy(item),
            }
        )

    for item in watchlist:
        code = str(item.get("code", "")).strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        candidates.append(
            {
                "fund_code": code,
                "fund_name": item.get("name", ""),
                "source": "watchlist",
                "in_portfolio": False,
                "category": item.get("category", ""),
                "benchmark": item.get("benchmark", ""),
                "risk_level": item.get("risk_level", ""),
                "proxy_symbol": (benchmark_mappings.get(code, {}) or {}).get("proxy_symbol", ""),
                "proxy_name": (benchmark_mappings.get(code, {}) or {}).get("proxy_name", ""),
            }
        )
    return candidates


def infer_style_group_for_new_fund(name: str, benchmark: str, category: str) -> str:
    text = f"{name} {benchmark} {category}".lower()
    rules = [
        ("sp500_core", ("标普500", "sp500", "s&p500")),
        ("nasdaq_core", ("纳斯达克100", "nasdaq100", "nasdaq")),
        ("china_us_internet", ("中美互联网", "互联网", "internet")),
        ("ai", ("人工智能", "ai")),
        ("grid_equipment", ("电网设备",)),
        ("carbon_neutral", ("碳中和",)),
        ("high_end_equipment", ("高端装备", "装备")),
        ("growth_rotation", ("成长", "新动力")),
        ("tech_growth", ("��技",)),
        ("industrial_metal", ("有色", "工业有色")),
        ("precious_metals", ("黄金", "金银珠宝", "贵金属")),
        ("grain_agriculture", ("粮食", "农业")),
        ("chemical", ("化工",)),
        ("bond_anchor", ("债券", "中债")),
        ("cash_buffer", ("存单", "货币", "现金")),
    ]
    for style_group, keywords in rules:
        if any(keyword.lower() in text for keyword in keywords):
            return style_group
    if "qdii" in text:
        return "global_growth"
    if "bond" in text:
        return "bond_anchor"
    if "cash" in text:
        return "cash_buffer"
    return "unknown"


def infer_role_for_new_fund(category: str, style_group: str, portfolio: dict) -> str:
    current_roles = {str(item.get("role", "")).strip() for item in portfolio.get("funds", []) or []}
    category_text = str(category or "").lower()
    if style_group in {"sp500_core", "nasdaq_core"}:
        return "core_dca"
    if category_text == "bond":
        return "fixed_hold"
    if category_text == "cash_management" and "cash_hub" not in current_roles:
        return "cash_hub"
    if category_text == "cash_management":
        return "fixed_hold"
    return "tactical"


def build_new_fund_entry(candidate: dict, matched_item: dict, strategy: dict, portfolio: dict) -> dict:
    definition_item = deepcopy(candidate.get("definition_item", {}) or {})
    if definition_item:
        entry = {key: value for key, value in definition_item.items() if key != "opening_state"}
    else:
        style_group = candidate.get("style_group") or infer_style_group_for_new_fund(
            candidate.get("fund_name", ""),
            candidate.get("benchmark", ""),
            candidate.get("category", ""),
        )
        role = candidate.get("role") or infer_role_for_new_fund(candidate.get("category", ""), style_group, portfolio)
        entry = {
            "fund_code": candidate.get("fund_code", ""),
            "fund_name": candidate.get("fund_name", ""),
            "role": role,
            "style_group": style_group,
            "category": candidate.get("category", "unknown"),
            "benchmark": candidate.get("benchmark", ""),
            "allow_trade": role != "fixed_hold",
            "proxy_symbol": candidate.get("proxy_symbol", ""),
            "proxy_name": candidate.get("proxy_name", ""),
            "proxy_type": "etf" if candidate.get("proxy_symbol") else "",
        }
        if role == "tactical":
            entry["cap_value"] = float(strategy.get("tactical", {}).get("default_cap_value", 1000.0) or 1000.0)
        if role == "core_dca":
            entry["fixed_daily_buy_amount"] = float(strategy.get("core_dca", {}).get("amount_per_fund", 25.0) or 25.0)
            entry["allow_extra_buys"] = bool(strategy.get("core_dca", {}).get("extra_buy_allowed", False))
        if role == "cash_hub":
            entry["min_hold_days"] = 7
            entry["redeem_settlement_days"] = 1

    current_value = safe_float(matched_item.get("current_value")) or 0.0
    holding_pnl = safe_float(matched_item.get("holding_pnl")) or 0.0
    holding_return_pct = safe_float(matched_item.get("holding_return_pct")) or 0.0
    cost_basis = safe_float(matched_item.get("derived_cost_basis_value"))
    if cost_basis is None:
        cost_basis = round(max(0.0, current_value - holding_pnl), 2)
    opening_state = {
        "current_value": round(current_value, 2),
        "holding_pnl": round(holding_pnl, 2),
        "holding_return_pct": round(holding_return_pct, 2),
        "holding_units": 0.0,
        "cost_basis_value": round(max(0.0, cost_basis), 2),
        "last_valuation_nav": None,
        "last_valuation_date": "",
        "last_official_nav": None,
        "last_official_nav_date": "",
        "units_source": "screenshot_sync_value_only",
    }
    return {**entry, "opening_state": opening_state}


def match_detected_holding(display_name: str, candidates: list[dict]) -> dict | None:
    target = normalize_fund_name(display_name)
    if not target:
        return None
    best: dict | None = None
    best_score = 0.0
    for candidate in candidates:
        name = normalize_fund_name(candidate.get("fund_name", ""))
        if not name:
            continue
        score = difflib.SequenceMatcher(a=target, b=name).ratio()
        if target == name:
            score = 1.0
        elif target in name or name in target:
            score = max(score, 0.93)
        if score > best_score:
            best_score = score
            best = candidate
    if best is None or best_score < 0.72:
        return None
    return {**best, "match_score": round(best_score, 4)}


def derive_cost_basis(current_value: float | None, holding_pnl: float | None, holding_return_pct: float | None) -> tuple[float | None, float | None]:
    if current_value is None:
        return None, None
    if holding_pnl is not None:
        cost_basis = round(max(0.0, current_value - holding_pnl), 2)
        return cost_basis, round(holding_pnl, 2)
    if holding_return_pct is None:
        return None, None
    denominator = 1.0 + float(holding_return_pct) / 100.0
    if denominator <= 0:
        return None, None
    cost_basis = round(current_value / denominator, 2)
    holding_pnl = round(current_value - cost_basis, 2)
    return cost_basis, holding_pnl


def build_sync_preview(agent_home: Path, detected_items: list[dict], image_paths: list[Path], provider: str, sync_date: str) -> dict:
    portfolio = load_portfolio(agent_home)
    current_by_code = {item.get("fund_code", ""): item for item in portfolio.get("funds", []) or []}
    candidates = build_match_candidates(agent_home)
    matched_items = []
    unmatched_detected = []
    matched_codes: set[str] = set()
    warnings: list[str] = [
        "支付宝持仓截图通常不包含持有份额，本次同步会优先用市值/持仓收益回写，份额默认保留原值。",
    ]

    for row in dedupe_detected_holdings(detected_items):
        current_value = safe_float(row.get("current_value"))
        holding_pnl = safe_float(row.get("holding_pnl"))
        holding_return_pct = safe_float(row.get("holding_return_pct"))
        daily_pnl = safe_float(row.get("daily_pnl"))
        cost_basis, derived_pnl = derive_cost_basis(current_value, holding_pnl, holding_return_pct)
        if holding_pnl is None:
            holding_pnl = derived_pnl
        match = match_detected_holding(row.get("display_name", ""), candidates)
        if match is None:
            unmatched_detected.append(
                {
                    "display_name": row.get("display_name", ""),
                    "current_value": current_value,
                    "holding_pnl": holding_pnl,
                    "holding_return_pct": holding_return_pct,
                    "page_index": row.get("page_index"),
                    "row_index": row.get("row_index"),
                }
            )
            continue

        matched_code = match["fund_code"]
        matched_codes.add(matched_code)
        before = current_by_code.get(matched_code, {})
        match_status = "matched" if match["source"] == "portfolio" else "not_in_current_portfolio"
        if match["match_score"] < 0.86 and match_status == "matched":
            match_status = "fuzzy_matched"
        matched_items.append(
            {
                "display_name": row.get("display_name", ""),
                "matched_fund_code": matched_code,
                "matched_fund_name": match.get("fund_name", ""),
                "match_score": match.get("match_score", 0.0),
                "match_source": match.get("source", ""),
                "match_status": match_status,
                "category": match.get("category", ""),
                "benchmark": match.get("benchmark", ""),
                "style_group": match.get("style_group", ""),
                "role": match.get("role", ""),
                "proxy_symbol": match.get("proxy_symbol", ""),
                "proxy_name": match.get("proxy_name", ""),
                "definition_item": deepcopy(match.get("definition_item", {}) or {}),
                "current_value": current_value,
                "daily_pnl": daily_pnl,
                "holding_pnl": holding_pnl,
                "holding_return_pct": holding_return_pct,
                "derived_cost_basis_value": cost_basis,
                "page_index": row.get("page_index"),
                "row_index": row.get("row_index"),
                "before_current_value": safe_float(before.get("current_value")),
                "before_holding_pnl": safe_float(before.get("holding_pnl")),
                "before_holding_return_pct": safe_float(before.get("holding_return_pct")),
                "delta_current_value": round((current_value or 0.0) - (safe_float(before.get("current_value")) or 0.0), 2) if before else None,
                "delta_holding_pnl": round((holding_pnl or 0.0) - (safe_float(before.get("holding_pnl")) or 0.0), 2) if before and holding_pnl is not None else None,
            }
        )

    missing_portfolio_funds = []
    for code, fund in current_by_code.items():
        current_value = safe_float(fund.get("current_value")) or 0.0
        if current_value <= 0:
            continue
        if code not in matched_codes:
            missing_portfolio_funds.append(
                {
                    "fund_code": code,
                    "fund_name": fund.get("fund_name", ""),
                    "current_value": current_value,
                }
            )

    if unmatched_detected:
        warnings.append("有截图中的持仓未能和系统基金匹配，这些项目不会自动同步。")
    new_fund_candidates = [item for item in matched_items if item.get("match_status") == "not_in_current_portfolio"]
    if new_fund_candidates:
        warnings.append("有截图识别到了系统外候选基金，可在确认同步时选择自动加入组合。")
    if missing_portfolio_funds:
        warnings.append("有当前系统持仓未出现在截图中。确认同步时可选择是否将这些仓位归零。")

    apply_ready = not unmatched_detected and bool(matched_items)
    return {
        "provider": provider,
        "generated_at": timestamp_now(),
        "sync_date": sync_date,
        "image_count": len(image_paths),
        "images": [str(path) for path in image_paths],
        "detected_holdings": matched_items + unmatched_detected,
        "matched_items": matched_items,
        "unmatched_detected": unmatched_detected,
        "new_fund_candidates": new_fund_candidates,
        "missing_portfolio_funds": missing_portfolio_funds,
        "apply_ready": apply_ready,
        "warnings": warnings,
    }


def recalc_portfolio_totals(portfolio: dict) -> None:
    portfolio["total_value"] = round(sum(float(item.get("current_value", 0.0) or 0.0) for item in portfolio.get("funds", []) or []), 2)
    portfolio["holding_pnl"] = round(sum(float(item.get("holding_pnl", 0.0) or 0.0) for item in portfolio.get("funds", []) or []), 2)


def apply_sync_preview(agent_home: Path, preview: dict, *, sync_date: str, drop_missing: bool, auto_add_new: bool) -> dict:
    portfolio = deepcopy(load_portfolio(agent_home))
    current_by_code = {item.get("fund_code", ""): item for item in portfolio.get("funds", []) or []}
    strategy = load_strategy(agent_home)
    definition = safe_portfolio_definition(agent_home, portfolio)
    updated_codes: list[str] = []
    added_codes: list[str] = []

    for item in preview.get("matched_items", []) or []:
        fund = current_by_code.get(item.get("matched_fund_code", ""))
        if not fund and item.get("match_status") == "not_in_current_portfolio" and auto_add_new:
            candidate = {
                "fund_code": item.get("matched_fund_code", ""),
                "fund_name": item.get("matched_fund_name", ""),
                "source": item.get("match_source", ""),
                "category": item.get("category", ""),
                "benchmark": item.get("benchmark", ""),
                "style_group": item.get("style_group", ""),
                "role": item.get("role", ""),
                "proxy_symbol": item.get("proxy_symbol", ""),
                "proxy_name": item.get("proxy_name", ""),
                "definition_item": deepcopy(item.get("definition_item", {}) or {}),
            }
            fund_entry = build_new_fund_entry(candidate, item, strategy, portfolio)
            portfolio.setdefault("funds", []).append({key: value for key, value in fund_entry.items() if key != "opening_state"})
            current_by_code[item.get("matched_fund_code", "")] = portfolio["funds"][-1]
            definition.setdefault("funds", []).append(fund_entry)
            fund = current_by_code.get(item.get("matched_fund_code", ""))
            added_codes.append(item.get("matched_fund_code", ""))
        elif not fund and item.get("match_status") == "not_in_current_portfolio":
            continue
        if not fund:
            continue
        current_value = safe_float(item.get("current_value")) or 0.0
        holding_pnl = safe_float(item.get("holding_pnl"))
        holding_return_pct = safe_float(item.get("holding_return_pct"))
        cost_basis = safe_float(item.get("derived_cost_basis_value"))
        if holding_pnl is None and cost_basis is not None:
            holding_pnl = round(current_value - cost_basis, 2)
        if cost_basis is None and holding_pnl is not None:
            cost_basis = round(max(0.0, current_value - holding_pnl), 2)
        if holding_return_pct is None and cost_basis and cost_basis > 0 and holding_pnl is not None:
            holding_return_pct = round((holding_pnl / cost_basis) * 100.0, 2)

        fund["current_value"] = round(current_value, 2)
        if holding_pnl is not None:
            fund["holding_pnl"] = round(holding_pnl, 2)
        if holding_return_pct is not None:
            fund["holding_return_pct"] = round(holding_return_pct, 2)
        if cost_basis is not None:
            fund["cost_basis_value"] = round(max(0.0, cost_basis), 2)
        fund["last_valuation_date"] = sync_date
        fund["units_source"] = str(fund.get("units_source") or "screenshot_sync_value_only")
        updated_codes.append(fund.get("fund_code", ""))

    dropped_codes: list[str] = []
    if drop_missing:
        for item in preview.get("missing_portfolio_funds", []) or []:
            fund = current_by_code.get(item.get("fund_code", ""))
            if not fund:
                continue
            fund["current_value"] = 0.0
            fund["holding_pnl"] = 0.0
            fund["holding_return_pct"] = 0.0
            fund["cost_basis_value"] = 0.0
            fund["holding_units"] = 0.0
            fund["last_valuation_date"] = sync_date
            fund["units_source"] = "screenshot_sync_missing_zero"
            dropped_codes.append(fund.get("fund_code", ""))

    portfolio["as_of_date"] = sync_date
    portfolio["last_valuation_run_date"] = sync_date
    portfolio["last_valuation_generated_at"] = timestamp_now()
    recalc_portfolio_totals(portfolio)
    definition["updated_at"] = timestamp_now()
    dump_json(portfolio_definition_path(agent_home), definition)
    current_path, snapshot_path = save_portfolio_state(
        agent_home,
        portfolio,
        source="portfolio_screenshot_sync",
        event_date=sync_date,
        event_type="portfolio_screenshot_sync",
        extra_meta={
            "provider": preview.get("provider", "alipay"),
            "image_count": int(preview.get("image_count", 0) or 0),
            "updated_fund_codes": updated_codes,
            "added_fund_codes": added_codes,
            "dropped_missing_fund_codes": dropped_codes,
        },
    )
    summary = {
        "sync_date": sync_date,
        "provider": preview.get("provider", "alipay"),
        "image_count": int(preview.get("image_count", 0) or 0),
        "updated_fund_count": len(updated_codes),
        "updated_fund_codes": updated_codes,
        "added_fund_count": len(added_codes),
        "added_fund_codes": added_codes,
        "dropped_missing_count": len(dropped_codes),
        "dropped_missing_fund_codes": dropped_codes,
        "current_path": str(current_path),
        "snapshot_path": str(snapshot_path),
        "unmatched_detected_count": len(preview.get("unmatched_detected", []) or []),
    }
    dump_json(applied_output_path(agent_home, sync_date), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or apply portfolio sync from Alipay fund holding screenshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview_parser = subparsers.add_parser("preview", help="Extract holdings from screenshots and build a sync preview.")
    preview_parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    preview_parser.add_argument("--date", help="Sync date in YYYY-MM-DD format.")
    preview_parser.add_argument("--provider", default="alipay")
    preview_parser.add_argument("--images", nargs="+", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply a generated sync preview to portfolio state.")
    apply_parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    apply_parser.add_argument("--date", help="Sync date in YYYY-MM-DD format.")
    apply_parser.add_argument("--preview-path", required=True)
    apply_parser.add_argument("--drop-missing", action="store_true", help="Zero current holdings missing from screenshots.")
    apply_parser.add_argument("--auto-add-new", action="store_true", help="Auto-add matched watchlist/definition funds missing from current portfolio.")

    args = parser.parse_args()
    agent_home = resolve_agent_home(getattr(args, "agent_home", None))
    ensure_layout(agent_home)
    sync_date = resolve_date(getattr(args, "date", None))

    if args.command == "preview":
        image_paths = [Path(path).expanduser() for path in args.images]
        missing = [str(path) for path in image_paths if not path.exists()]
        if missing:
            raise SystemExit(f"Missing screenshot files: {', '.join(missing)}")
        extracted = call_screenshot_vision(agent_home, image_paths, args.provider)
        preview = build_sync_preview(agent_home, extracted.get("items", []), image_paths, args.provider, sync_date)
        preview["vision_warnings"] = extracted.get("warnings", [])
        preview["transport_name"] = extracted.get("_transport_name", "")
        path = dump_json(preview_output_path(agent_home, sync_date), preview)
        print(path)
        return

    preview = json.loads(Path(args.preview_path).read_text(encoding="utf-8"))
    summary = apply_sync_preview(
        agent_home,
        preview,
        sync_date=sync_date,
        drop_missing=bool(args.drop_missing),
        auto_add_new=bool(args.auto_add_new),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
