from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import agent_output_dir, agent_snapshot_root, dump_json, ensure_layout, evidence_index_path, llm_context_path, load_agents_config, load_json, resolve_agent_home, resolve_date, timestamp_now
from evidence_index import build_evidence_index_payload, retrieve_agent_evidence
from multiagent_utils import call_json_agent

DEFAULT_ANALYST_ORDER = [
    "market_analyst",
    "theme_analyst",
    "fund_structure_analyst",
    "fund_quality_analyst",
    "news_analyst",
    "sentiment_analyst",
]
DEFAULT_RESEARCHER_ORDER = ["bull_researcher", "bear_researcher"]
DEFAULT_MANAGER_ORDER = ["research_manager", "risk_manager", "portfolio_trader"]


def compose_prompt(role: str, mission: list[str], input_focus: list[str], method: list[str], output_rules: list[str], do_not: list[str]) -> str:
    lines = [
        "你是基金组合研究系统中的专业岗位智能体，不是泛泛而谈的聊天助手。",
        "输出必须服务于下游投研决策，不能编造输入中不存在的数据。",
        "自然语言字段使用简体中文；JSON key 与枚举值保持英文。",
        "如果证据不足、数据陈旧或冲突很大，必须降低 confidence，必要时 abstain=true。",
        "若复盘记忆显示某类信号近期失效，必须在结论中体现更高谨慎度。",
        "禁止输出收尾套话、重复总结、空白填充或'完成/结束/以下补充'类无信息句。",
        "返回严格 JSON，不要 markdown，不要额外解释。",
        "每个 fund_view 或 card 若引用证据，必须包含 evidence_refs；证据不足时必须降低 confidence。",
        "",
        f"Role:\n- {role}",
        "Mission:",
        *[f"- {item}" for item in mission],
        "Input Focus:",
        *[f"- {item}" for item in input_focus],
        "Method:",
        *[f"- {item}" for item in method],
        "Output Rules:",
        *[f"- {item}" for item in output_rules],
        "Do Not:",
        *[f"- {item}" for item in do_not],
    ]
    return "\n".join(lines)


AGENT_PROMPTS = {
    "market_analyst": compose_prompt(
        role="market_regime_analyst，负责判断当前交易日的跨市场风险偏好与市场环境。",
        mission=[
            "识别今天更适合进攻、均衡还是防守。",
            "评估这种环境如何影响当前基金组合，而不是单点评价个别基金。",
        ],
        input_focus=[
            "组合摘要与风险偏好。",
            "A 股、港股、美股、QDII 相关代理行情与实时估值。",
            "盘中数据是否 stale。",
        ],
        method=[
            "先判断 regime：risk_on / mixed / risk_off。",
            "再判断这种 regime 对风格与主题的映射。",
            "最后只输出与组合强相关的基金结论。",
        ],
        output_rules=[
            "必须输出 portfolio_view.regime、risk_bias、portfolio_implications。",
            "如果盘中代理或实时估值大面积 stale，必须明确降级判断。",
            "fund_views 中只保留高相关基金，不要平均分配注意力。",
        ],
        do_not=[
            "不要直接输出最终交易金额。",
            "不要把板块热度当成整体市场环境本身。",
        ],
    ),
    "theme_analyst": compose_prompt(
        role="theme_rotation_analyst，负责主题和行业轮动判断。",
        mission=[
            "围绕有色、粮食农业、化工、电网设备、碳中和、AI、中概互联、科技成长等主题判断相对吸引力。",
            "区分趋势延续、短线过热和左侧修复。",
        ],
        input_focus=[
            "tactical 基金及其 style_group。",
            "盘中代理、实时估值、相关新闻。",
            "external_reference 中的 manual_biases 与手工主题参考开关。",
        ],
        method=[
            "判断主题强弱与持续性。",
            "识别是否存在同主题拥挤或风格堆叠。",
            "给出相对排序，而不是只复述涨跌幅。",
        ],
        output_rules=[
            "fund_views 必须体现相对吸引力与 action_bias。",
            "必须区分回撤低吸、趋势持有、过热观望。",
        ],
        do_not=[
            "不要仅根据单日涨跌推导中期结论。",
            "不要忽略组合已有主题拥挤。",
        ],
    ),
    "fund_structure_analyst": compose_prompt(
        role="fund_structure_analyst，负责组合结构、角色定位、风格重叠与约束映射。",
        mission=[
            "识别角色混乱、风格重叠、上限占用不合理和现金仓调拨风险。",
            "判断某只基金继续增配是否提高组合效率。",
        ],
        input_focus=[
            "fund role、style_group、current_value、cap_value、locked_amount。",
            "核心定投、固定持有、现金仓等约束。",
        ],
        method=[
            "先识别结构冲突与替代关系。",
            "再判断继续增减仓对组合的边际影响。",
        ],
        output_rules=[
            "fund_views 必须写清 portfolio_impact，并把重叠风险、容量约束写进 comment。",
            "对高重叠基金要显式写出替代关系和拥挤风险。",
        ],
        do_not=[
            "不要把短线涨跌当作结构结论。",
            "不要越权讨论新闻催化强弱。",
        ],
    ),
    "fund_quality_analyst": compose_prompt(
        role="fund_quality_analyst，负责基金慢变量质量与角色适配分析。",
        mission=[
            "基于基金角色、风格稳定性、主题纯度和当前可用结构信息，给出中期可信度判断。",
            "避免系统只盯短线波动。",
        ],
        input_focus=[
            "基金角色、style_group、历史收益分布、新闻摘要。",
            "当前缺失的慢变量信息也要明确指出。",
        ],
        method=[
            "先判断基金是否适合作为当前角色。",
            "再判断短线强势是否值得扩仓，还是只适合战术持有。",
        ],
        output_rules=[
            "必须在 comment 中明确长期质量是高 / 中 / 低。",
            "如果缺少长期质量数据，missing_info 中必须点出。",
        ],
        do_not=[
            "不要因为短线强势就直接给出高质量结论。",
        ],
    ),
    "news_analyst": compose_prompt(
        role="event_news_analyst，负责新闻、公告、政策与事件催化分析。",
        mission=[
            "识别哪些新闻是真正新增信息，哪些只是噪音。",
            "判断事件影响窗口是 intraday、1-5d 还是 1-4w。",
        ],
        input_focus=[
            "基金相关新闻、发布时间、来源、影响标签。",
            "主题相关政策或产业事件。",
        ],
        method=[
            "区分新增信息、已反映预期与纯噪音。",
            "将事件映射到具体基金，而不是停留在宏观层。",
        ],
        output_rules=[
            "必须在 comment 中说明是增量信息、已反映预期还是噪音。",
            "如果新闻旧、重复或无法映射到基金，允许 abstain=true。",
        ],
        do_not=[
            "不要只复述标题。",
            "不要把旧闻当作新增催化。",
        ],
    ),
    "sentiment_analyst": compose_prompt(
        role="sentiment_flow_analyst，负责情绪、拥挤度、板块热度与交易层风险。",
        mission=[
            "识别哪些方向虽然强但可能已经拥挤，哪些方向虽然弱但可能出现修复。",
            "结合复盘记忆评估追涨和抄底是否值得。",
        ],
        input_focus=[
            "manual_biases、手工主题参考开关、盘中代理、实时估值。",
            "复盘记忆中的近期失误模式。",
        ],
        method=[
            "判断 crowding_level 与 reversal_potential。",
            "区分强者恒强和短线过热。",
        ],
        output_rules=[
            "必须在 comment 中说明拥挤度与反身性修复概率。",
            "对高热主题默认提高谨慎等级，除非证据极强。",
        ],
        do_not=[
            "不要把情绪判断包装成基本面结论。",
        ],
    ),
    "bull_researcher": compose_prompt(
        role="bull_researcher，负责构造最强看多论证。",
        mission=[
            "只挑最值得继续持有或小幅加仓的 2-4 个候选。",
            "主动回应主要反对意见。",
        ],
        input_focus=[
            "全部 analyst outputs。",
            "tactical 基金与复盘记忆。",
        ],
        method=[
            "优先找具备趋势延续或风险收益改善的基金。",
            "明确说明为什么是现在，而不是以后。",
        ],
        output_rules=[
            "必须在 comment 中回应主要反对意见。",
            "没有足够强候选时，可以只输出 0-1 个 add 候选。",
        ],
        do_not=[
            "不要把所有基金都写成 bullish。",
        ],
    ),
    "bear_researcher": compose_prompt(
        role="bear_researcher，负责构造最强看空、减仓或换基论证。",
        mission=[
            "识别今天最值得减仓、切换或至少停止追高的基金。",
            "区分结构性问题、时点问题和噪音。",
        ],
        input_focus=[
            "全部 analyst outputs。",
            "重叠、拥挤、陈旧数据与事件风险。",
        ],
        method=[
            "只挑最脆弱的 2-4 个候选。",
            "区分 reduce / avoid_chasing / switch_preferred。",
        ],
        output_rules=[
            "必须在 comment 中说明最关键的失败风险。",
            "如果主要问题只是过热，不能夸大成长期看空。",
        ],
        do_not=[
            "不要机械看空所有高收益基金。",
        ],
    ),
    "research_manager": compose_prompt(
        role="research_manager，相当于投资委员会研究负责人。",
        mission=[
            "综合 analyst 与 bull/bear researcher 的意见，形成候选动作清单。",
            "先找共识，再识别分歧。",
        ],
        input_focus=[
            "全部前置 agent outputs。",
            "组合约束与复盘记忆。",
        ],
        method=[
            "逐只基金判断 committee_preference。",
            "输出少量高质量候选动作，而不是面面俱到。",
        ],
        output_rules=[
            "fund_views 必须用 action_bias 表达委员会倾向，用 comment 写共识、分歧和建议力度。",
            "必须在 comment 或 response_to_bear_case 中回应未采纳的反方意见。",
            "必须给出 no_trade_list 对应的观察理由。",
        ],
        do_not=[
            "不要把所有有效信号都转成动作。",
        ],
    ),
    "risk_manager": compose_prompt(
        role="risk_manager，相当于组合风控负责人。",
        mission=[
            "对研究经理候选动作做挑战、降级或否决，保护组合免于过度交易与主题拥挤。",
            "在 manager 与 risk 冲突时，你的意见默认优先级更高。",
        ],
        input_focus=[
            "research_manager 输出。",
            "原始 analyst outputs、组合约束与复盘记忆。",
        ],
        method=[
            "逐项审查候选动作。",
            "识别追涨、左侧抄底、证据不足、数据陈旧、过度集中等问题。",
        ],
        output_rules=[
            "必须用 action_bias 表达风控后的倾向，用 comment 写 approve / modify / reject 及原因。",
            "hard veto 必须写入 risk_decision=reject 或 downgrade_reason，供 validator 作为硬约束读取。",
            "如果要降级或否决，必须在 comment 中写清替代动作。",
        ],
        do_not=[
            "不要为了保守而保守。",
        ],
    ),
    "portfolio_trader": compose_prompt(
        role="portfolio_trader，负责把委员会结论转成可执行但仍受约束的建议草案。",
        mission=[
            "严格依赖 research_manager 与 risk_manager 的输出，不得脱离委员会结论自由发挥。",
            "将研究意见压缩成最终候选动作的草案。",
        ],
        input_focus=[
            "research_manager、risk_manager、compact raw context。",
            "全部硬约束。",
        ],
        method=[
            "一致意见优先，冲突时默认采用更保守方案。",
            "suggest_amount 只使用 bucket：0 / 100 / 200 / 300 / full_exit_candidate。",
        ],
        output_rules=[
            "必须用 action_bias 表达最终执行偏向，用 comment 写建议力度，例如 add_small / reduce_200 / hold_no_chase。",
            "没有高质量机会时，应当明确多数基金 hold。",
        ],
        do_not=[
            "不要忽略 risk_manager 的反对意见。",
            "不要生成超出约束的动作强度。",
        ],
    ),
}

AGENT_ATTEMPTS = {
    "market_analyst": 2,
    "theme_analyst": 2,
    "fund_structure_analyst": 2,
    "fund_quality_analyst": 2,
    "news_analyst": 2,
    "sentiment_analyst": 2,
    "bull_researcher": 4,
    "bear_researcher": 2,
    "research_manager": 4,
    "risk_manager": 4,
    "portfolio_trader": 4,
}
AGENT_EFFORTS = {
    "market_analyst": "medium",
    "theme_analyst": "medium",
    "fund_structure_analyst": "medium",
    "fund_quality_analyst": "medium",
    "news_analyst": "medium",
    "sentiment_analyst": "medium",
    "bull_researcher": "high",
    "bear_researcher": "high",
    "research_manager": "high",
    "risk_manager": "high",
    "portfolio_trader": "high",
}
AGENT_VERBOSITY = {
    "research_manager": "low",
    "risk_manager": "low",
    "portfolio_trader": "low",
}
AGENT_MAX_OUTPUT_TOKENS = {
    "research_manager": 3200,
    "risk_manager": 2800,
    "portfolio_trader": 2200,
}
GROUP_MAX_WORKERS = {
    "analyst": 3,
    "researcher": 2,
}

STAGE_METADATA = {
    "analyst": {
        "label": "Analyst Team",
        "description": "拆分市场、主题、结构、质量、新闻与情绪信号。",
    },
    "researcher": {
        "label": "Research Debate",
        "description": "围绕 analyst 结论构造最强看多与看空论证。",
    },
    "manager": {
        "label": "Committee Decision",
        "description": "由研究经理、风险经理和组合交易员收敛成最终动作。",
    },
}

WORKFLOW_VERSION = "2026-04-19.workflow-v2"
AGENT_INPUT_CONTRACT_VERSION = "2026-04-19.input-v2"
PROMPT_BUNDLE_VERSION = "2026-04-19.prompt-v2"


def stable_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def prompt_bundle_metadata(agent_names: list[str]) -> dict:
    prompts = {name: AGENT_PROMPTS[name] for name in agent_names}
    execution_config = {
        name: {
            "attempts": AGENT_ATTEMPTS.get(name, 3),
            "reasoning_effort": AGENT_EFFORTS.get(name, "medium"),
            "text_verbosity": AGENT_VERBOSITY.get(name),
            "max_output_tokens": AGENT_MAX_OUTPUT_TOKENS.get(name),
        }
        for name in agent_names
    }
    bundle = {
        "version": PROMPT_BUNDLE_VERSION,
        "prompts": prompts,
        "execution_config": execution_config,
    }
    return {
        "version": PROMPT_BUNDLE_VERSION,
        "digest": stable_digest(bundle),
        "execution_config": execution_config,
    }


def retrieval_summary(agent_input: dict) -> dict:
    retrieval = agent_input.get("retrieved_evidence", {}) or {}
    portfolio_items = list(retrieval.get("portfolio", []) or [])
    fund_items = retrieval.get("funds", {}) or {}
    fund_counts = {fund_code: len(items or []) for fund_code, items in fund_items.items()}
    stale_count = sum(1 for item in portfolio_items if bool(item.get("stale", False)))
    stale_count += sum(1 for items in fund_items.values() for item in (items or []) if bool(item.get("stale", False)))
    return {
        "portfolio_item_count": len(portfolio_items),
        "fund_item_count": sum(fund_counts.values()),
        "fund_counts": fund_counts,
        "stale_item_count": stale_count,
    }


def workflow_definition(
    *,
    ordered_agents: list[str],
    agent_roles: dict[str, str],
    agent_groups: dict[str, list[str]],
    agent_dependencies: dict[str, list[str]],
    worker_caps: dict[str, int],
    use_existing: bool,
    use_mock: bool,
    snapshot_enabled: bool,
    evidence_index_source: str,
) -> dict:
    prompt_bundle = prompt_bundle_metadata(ordered_agents)
    return {
        "workflow_version": WORKFLOW_VERSION,
        "agent_input_contract_version": AGENT_INPUT_CONTRACT_VERSION,
        "ordered_agents": ordered_agents,
        "agent_roles": agent_roles,
        "agent_groups": agent_groups,
        "agent_dependencies": agent_dependencies,
        "research_flow": build_stage_flow(agent_groups),
        "worker_caps": worker_caps,
        "use_existing": bool(use_existing),
        "use_mock": bool(use_mock),
        "snapshot_enabled": bool(snapshot_enabled),
        "evidence_index_source": evidence_index_source,
        "prompt_bundle": prompt_bundle,
    }


def trace_from_existing(agent_name: str, record: dict, stage: str, dependencies: list[str]) -> dict:
    output = dict(record.get("output", {}) or {})
    return {
        "agent_name": agent_name,
        "stage": stage,
        "status": "reused",
        "reused_existing": True,
        "dependencies": list(dependencies),
        "output_sha256": stable_digest(output),
        "retrieval_summary": {"portfolio_item_count": 0, "fund_item_count": 0, "fund_counts": {}, "stale_item_count": 0},
        "prompt_sha256": stable_digest(AGENT_PROMPTS.get(agent_name, "")),
        "agent_input_sha256": "",
        "user_prompt_sha256": "",
        "elapsed_seconds": 0.0,
        "started_at": timestamp_now(),
        "finished_at": timestamp_now(),
    }


def build_agent_roles(analyst_order: list[str], researcher_order: list[str], manager_order: list[str], ordered_agents: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for name in analyst_order:
        if name in ordered_agents:
            roles[name] = "analyst"
    for name in researcher_order:
        if name in ordered_agents:
            roles[name] = "researcher"
    for name in manager_order:
        if name in ordered_agents:
            roles[name] = "manager"
    return roles


def build_agent_dependencies(
    ordered_agents: list[str],
    analyst_order: list[str],
    researcher_order: list[str],
    manager_order: list[str],
) -> dict[str, list[str]]:
    enabled_analysts = [name for name in analyst_order if name in ordered_agents]
    enabled_researchers = [name for name in researcher_order if name in ordered_agents]
    enabled_managers = [name for name in manager_order if name in ordered_agents]
    dependencies: dict[str, list[str]] = {}

    for name in enabled_analysts:
        dependencies[name] = []
    for name in enabled_researchers:
        dependencies[name] = enabled_analysts.copy()
    if "research_manager" in enabled_managers:
        dependencies["research_manager"] = enabled_analysts + enabled_researchers
    if "risk_manager" in enabled_managers:
        upstream = enabled_analysts + enabled_researchers
        if "research_manager" in enabled_managers:
            upstream.append("research_manager")
        dependencies["risk_manager"] = upstream
    if "portfolio_trader" in enabled_managers:
        upstream = []
        for candidate in ("research_manager", "risk_manager"):
            if candidate in enabled_managers:
                upstream.append(candidate)
        dependencies["portfolio_trader"] = upstream

    for name in ordered_agents:
        dependencies.setdefault(name, [])
    return dependencies


def build_stage_flow(stage_agents: dict[str, list[str]]) -> list[dict]:
    flow: list[dict] = []
    for stage in ("analyst", "researcher", "manager"):
        meta = STAGE_METADATA[stage]
        flow.append(
            {
                "stage": stage,
                "label": meta["label"],
                "description": meta["description"],
                "agents": stage_agents.get(stage, []),
            }
        )
    return flow


def build_stage_status(aggregate: dict) -> dict[str, dict]:
    statuses: dict[str, dict] = {}
    stage_agents = aggregate.get("agent_groups", {}) or {}
    agents = aggregate.get("agents", {}) or {}
    for stage, names in stage_agents.items():
        ok = 0
        failed = 0
        pending = 0
        degraded = 0
        for name in names:
            status = str(agents.get(name, {}).get("status", "pending") or "pending").lower()
            if status in {"ok", "success"}:
                ok += 1
            elif status == "failed":
                failed += 1
            elif status == "degraded":
                degraded += 1
            else:
                pending += 1
        statuses[stage] = {
            "label": STAGE_METADATA.get(stage, {}).get("label", stage),
            "total": len(names),
            "ok": ok,
            "failed": failed,
            "degraded": degraded,
            "pending": pending,
        }
    return statuses


def next_snapshot_dir(agent_home: Path, report_date: str) -> Path:
    base = agent_snapshot_root(agent_home, report_date)
    base.mkdir(parents=True, exist_ok=True)
    versions = sorted(path for path in base.iterdir() if path.is_dir() and path.name.startswith("v"))
    target = base / f"v{len(versions) + 1:03d}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def empty_fund_view(fund_code: str) -> dict:
    return {
        "fund_code": fund_code,
        "direction": "neutral",
        "horizon": "1-5d",
        "thesis": "",
        "catalysts": [],
        "risks": [],
        "invalidation": "",
        "portfolio_impact": "",
        "action_bias": "hold",
        "overlap_risk": "",
        "capacity_limit": "",
        "event_incrementality": "",
        "crowding_level": "",
        "committee_preference": "",
        "main_supporting_agents": [],
        "main_conflicts": [],
        "preferred_action": "hold",
        "preferred_size_bucket": "0",
        "risk_decision": "",
        "downgrade_reason": "",
        "alternative_action": "",
        "counterarguments": [],
        "response_to_bear_case": [],
        "what_can_go_wrong": [],
        "structural_quality": "",
        "comment": "",
    }


def build_mock_output(agent_name: str, context: dict) -> dict:
    fund_views = []
    for fund in context.get("funds", [])[:4]:
        view = empty_fund_view(fund["fund_code"])
        view.update(
            {
                "direction": "mixed",
                "thesis": f"{agent_name} mock 认为 {fund['fund_name']} 暂时没有足够强的新增信号。",
                "catalysts": ["mock 数据验证流程"],
                "risks": ["仅用于调试，不代表真实观点"],
                "invalidation": "真实数据接入后重新判断。",
                "portfolio_impact": "对组合影响有限。",
                "action_bias": "hold",
                "comment": f"{agent_name} mock view",
            }
        )
        fund_views.append(view)
    return {
        "agent_name": agent_name,
        "mode": context.get("mode", "intraday"),
        "summary": f"{agent_name} mock 输出：当前以观望为主。",
        "confidence": 55,
        "evidence_strength": "low",
        "data_freshness": "mixed",
        "abstain": False,
        "missing_info": [],
        "key_points": ["mock 流程验证", "输出结构已升级"],
        "portfolio_view": {
            "regime": "mixed",
            "risk_bias": "balanced",
            "key_drivers": ["mock 流程验证"],
            "portfolio_implications": ["先验证链路，再使用真实数据运行。"],
        },
        "fund_views": fund_views,
        "watchouts": ["mock 模式不应用于真实决策。"],
    }


def compact_fund_view(fund: dict) -> dict:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund.get("role"),
        "style_group": fund.get("style_group"),
        "current_value": fund.get("current_value"),
        "holding_pnl": fund.get("holding_pnl"),
        "holding_return_pct": fund.get("holding_return_pct"),
        "cap_value": fund.get("cap_value"),
        "locked_amount": fund.get("locked_amount"),
        "allow_trade": fund.get("allow_trade"),
        "fixed_daily_buy_amount": fund.get("fixed_daily_buy_amount"),
        "quote": {
            "day_change_pct": fund.get("quote", {}).get("day_change_pct"),
            "week_change_pct": fund.get("quote", {}).get("week_change_pct"),
            "month_change_pct": fund.get("quote", {}).get("month_change_pct"),
        },
        "intraday_proxy": {
            "change_pct": fund.get("intraday_proxy", {}).get("change_pct"),
            "stale": fund.get("intraday_proxy", {}).get("stale"),
            "proxy_name": fund.get("intraday_proxy", {}).get("proxy_name") or fund.get("intraday_proxy", {}).get("name"),
        },
        "estimated_nav": {
            "estimate_change_pct": fund.get("estimated_nav", {}).get("estimate_change_pct"),
            "confidence": fund.get("estimated_nav", {}).get("confidence"),
            "stale": fund.get("estimated_nav", {}).get("stale"),
        },
        "fund_profile": {
            "inception_date": fund.get("fund_profile", {}).get("inception_date"),
            "fund_age_years": fund.get("fund_profile", {}).get("fund_age_years"),
            "fund_manager": fund.get("fund_profile", {}).get("fund_manager"),
            "fund_type": fund.get("fund_profile", {}).get("fund_type"),
            "management_company": fund.get("fund_profile", {}).get("management_company"),
            "fund_scale_billion": fund.get("fund_profile", {}).get("fund_scale_billion"),
            "management_fee_rate": fund.get("fund_profile", {}).get("management_fee_rate"),
            "custody_fee_rate": fund.get("fund_profile", {}).get("custody_fee_rate"),
            "status": fund.get("fund_profile", {}).get("status"),
        },
        "recent_news": fund.get("recent_news", [])[:3],
    }


def compact_decision_fund_view(fund: dict) -> dict:
    return {
        "fund_code": fund["fund_code"],
        "fund_name": fund["fund_name"],
        "role": fund.get("role"),
        "style_group": fund.get("style_group"),
        "current_value": fund.get("current_value"),
        "holding_pnl": fund.get("holding_pnl"),
        "holding_return_pct": fund.get("holding_return_pct"),
        "cap_value": fund.get("cap_value"),
        "locked_amount": fund.get("locked_amount"),
        "allow_trade": fund.get("allow_trade"),
        "fixed_daily_buy_amount": fund.get("fixed_daily_buy_amount"),
        "quote": {
            "day_change_pct": fund.get("quote", {}).get("day_change_pct"),
            "week_change_pct": fund.get("quote", {}).get("week_change_pct"),
            "month_change_pct": fund.get("quote", {}).get("month_change_pct"),
        },
        "intraday_proxy": {
            "change_pct": fund.get("intraday_proxy", {}).get("change_pct"),
            "stale": fund.get("intraday_proxy", {}).get("stale"),
        },
        "estimated_nav": {
            "estimate_change_pct": fund.get("estimated_nav", {}).get("estimate_change_pct"),
            "confidence": fund.get("estimated_nav", {}).get("confidence"),
            "stale": fund.get("estimated_nav", {}).get("stale"),
        },
        "fund_profile": {
            "fund_age_years": fund.get("fund_profile", {}).get("fund_age_years"),
            "fund_type": fund.get("fund_profile", {}).get("fund_type"),
            "fund_scale_billion": fund.get("fund_profile", {}).get("fund_scale_billion"),
            "status": fund.get("fund_profile", {}).get("status"),
        },
    }


def successful_outputs(prior_outputs: dict, names: list[str] | None = None) -> dict:
    pool = names or list(prior_outputs.keys())
    return {key: prior_outputs[key]["output"] for key in pool if key in prior_outputs and prior_outputs[key]["status"] == "ok"}


def compact_agent_output(output: dict) -> dict:
    return {
        "agent_name": output.get("agent_name"),
        "mode": output.get("mode"),
        "summary": output.get("summary"),
        "confidence": output.get("confidence"),
        "evidence_strength": output.get("evidence_strength"),
        "data_freshness": output.get("data_freshness"),
        "abstain": output.get("abstain"),
        "key_points": (output.get("key_points") or [])[:6],
        "missing_info": (output.get("missing_info") or [])[:4],
        "watchouts": (output.get("watchouts") or [])[:4],
        "portfolio_view": {
            "regime": output.get("portfolio_view", {}).get("regime"),
            "risk_bias": output.get("portfolio_view", {}).get("risk_bias"),
            "key_drivers": (output.get("portfolio_view", {}).get("key_drivers") or [])[:4],
            "portfolio_implications": (output.get("portfolio_view", {}).get("portfolio_implications") or [])[:4],
        },
        "fund_views": [
            {
                "fund_code": item.get("fund_code"),
                "direction": item.get("direction"),
                "horizon": item.get("horizon"),
                "thesis": item.get("thesis"),
                "action_bias": item.get("action_bias"),
                "comment": item.get("comment"),
                "risks": (item.get("risks") or [])[:2],
            }
            for item in (output.get("fund_views") or [])[:6]
        ],
        "signal_cards": [
            {
                "signal_id": item.get("signal_id"),
                "fund_code": item.get("fund_code"),
                "signal_type": item.get("signal_type"),
                "direction": item.get("direction"),
                "action_bias": item.get("action_bias"),
                "confidence": item.get("confidence"),
                "supporting_evidence_ids": (item.get("supporting_evidence_ids") or [])[:4],
            }
            for item in (output.get("signal_cards") or [])[:8]
        ],
        "decision_cards": [
            {
                "decision_id": item.get("decision_id"),
                "fund_code": item.get("fund_code"),
                "proposed_action": item.get("proposed_action"),
                "size_bucket": item.get("size_bucket"),
                "risk_decision": item.get("risk_decision"),
                "supporting_signal_ids": (item.get("supporting_signal_ids") or [])[:4],
                "opposing_signal_ids": (item.get("opposing_signal_ids") or [])[:4],
            }
            for item in (output.get("decision_cards") or [])[:8]
        ],
    }


def stable_card_id(prefix: str, agent_name: str, fund_code: str, ordinal: int) -> str:
    digest = hashlib.sha1(f"{prefix}|{agent_name}|{fund_code}|{ordinal}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{agent_name}:{fund_code}:{digest}"


def signal_cards_from_views(agent_name: str, fund_views: list[dict], prior_outputs: dict) -> list[dict]:
    cards = []
    evidence_lookup = (prior_outputs or {}).get("_context_evidence_map", {}) if isinstance(prior_outputs, dict) else {}
    for index, item in enumerate(fund_views or [], start=1):
        fund_code = str(item.get("fund_code", "") or "").strip()
        if not fund_code:
            continue
        evidence_refs = evidence_lookup.get(fund_code, []) if isinstance(evidence_lookup, dict) else []
        cards.append(
            {
                "signal_id": item.get("signal_id") or stable_card_id("signal", agent_name, fund_code, index),
                "agent_name": agent_name,
                "signal_type": agent_name,
                "fund_code": fund_code,
                "direction": item.get("direction", ""),
                "horizon": item.get("horizon", ""),
                "thesis": item.get("thesis", ""),
                "catalysts": item.get("catalysts", []),
                "risks": item.get("risks", []),
                "invalidation": item.get("invalidation", ""),
                "portfolio_impact": item.get("portfolio_impact", ""),
                "action_bias": item.get("action_bias", ""),
                "supporting_evidence_ids": [ref.get("evidence_id", "") for ref in evidence_refs[:5] if ref.get("evidence_id")],
                "opposing_evidence_ids": [],
                "sentiment_relevance": float(item.get("sentiment_relevance", 0.0) or 0.0),
                "novelty_relevance": float(item.get("novelty_relevance", 0.0) or 0.0),
                "crowding_signal": item.get("crowding_signal", ""),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "comment": item.get("comment", ""),
                "abstain_reason": item.get("abstain_reason", ""),
            }
        )
    return cards


def decision_cards_from_views(agent_name: str, fund_views: list[dict], signal_cards: list[dict]) -> list[dict]:
    cards = []
    signal_map = {item.get("fund_code", ""): item.get("signal_id", "") for item in signal_cards or [] if item.get("fund_code")}
    for index, item in enumerate(fund_views or [], start=1):
        fund_code = str(item.get("fund_code", "") or "").strip()
        if not fund_code:
            continue
        size_bucket = item.get("preferred_size_bucket") or item.get("size_bucket") or (
            "100" if "100" in str(item.get("comment", "")) else "200" if "200" in str(item.get("comment", "")) else "0"
        )
        cards.append(
            {
                "decision_id": item.get("decision_id") or stable_card_id("decision", agent_name, fund_code, index),
                "agent_name": agent_name,
                "fund_code": fund_code,
                "proposed_action": item.get("preferred_action") or item.get("action_bias", "hold"),
                "size_bucket": size_bucket,
                "supporting_signal_ids": [signal_map[fund_code]] if signal_map.get(fund_code) else [],
                "opposing_signal_ids": [],
                "why_now": item.get("thesis") or item.get("comment", ""),
                "why_not_more": item.get("comment", ""),
                "invalidate_when": item.get("invalidation", ""),
                "risk_decision": item.get("risk_decision", ""),
                "manager_notes": item.get("comment", ""),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "priority": index,
            }
        )
    return cards


NOISE_STRINGS = {
    "完成。",
    "结束。",
    "以下no_trade_list为补充。",
    "已包含对应观察理由。",
    "这符合岗位职责要求。",
}

NOISE_PREFIXES = (
    "no_trade_list如下",
    "请特别注意其中",
    "当前更重视避免错误",
    "委员会对此保持一致",
    "因此今天的候选动作清单很短",
)


def normalize_text_line(value: str) -> str:
    return " ".join(str(value).replace("\u3000", " ").split()).strip()


def is_noise_line(value: str) -> bool:
    text = normalize_text_line(value)
    if not text:
        return True
    if text in NOISE_STRINGS:
        return True
    return any(text.startswith(prefix) for prefix in NOISE_PREFIXES)


def sanitize_string_list(values, limit: int | None = None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        text = normalize_text_line(item)
        if is_noise_line(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if limit is not None and len(cleaned) >= limit:
            break
    return cleaned


def sanitize_agent_output(output: dict) -> dict:
    cleaned = dict(output or {})
    cleaned["summary"] = normalize_text_line(cleaned.get("summary", ""))
    cleaned["key_points"] = sanitize_string_list(cleaned.get("key_points", []), limit=6)
    cleaned["missing_info"] = sanitize_string_list(cleaned.get("missing_info", []), limit=5)
    cleaned["watchouts"] = sanitize_string_list(cleaned.get("watchouts", []), limit=5)

    portfolio_view = dict(cleaned.get("portfolio_view", {}) or {})
    portfolio_view["key_drivers"] = sanitize_string_list(portfolio_view.get("key_drivers", []), limit=5)
    portfolio_view["portfolio_implications"] = sanitize_string_list(portfolio_view.get("portfolio_implications", []), limit=5)
    cleaned["portfolio_view"] = portfolio_view

    sanitized_views = []
    for item in cleaned.get("fund_views", []) or []:
        view = dict(item or {})
        for key in ("thesis", "invalidation", "portfolio_impact", "action_bias", "comment", "direction", "horizon"):
            if key in view and isinstance(view.get(key), str):
                view[key] = normalize_text_line(view.get(key, ""))
        for key, limit in {
            "catalysts": 4,
            "risks": 4,
            "counterarguments": 3,
            "response_to_bear_case": 3,
            "what_can_go_wrong": 3,
            "main_conflicts": 3,
            "main_supporting_agents": 4,
        }.items():
            if key in view:
                view[key] = sanitize_string_list(view.get(key, []), limit=limit)
        sanitized_views.append(view)
    cleaned["fund_views"] = sanitized_views
    cleaned["signal_cards"] = [
        {
            **dict(item or {}),
            "supporting_evidence_ids": sanitize_string_list((item or {}).get("supporting_evidence_ids", []), limit=6),
            "opposing_evidence_ids": sanitize_string_list((item or {}).get("opposing_evidence_ids", []), limit=6),
        }
        for item in (cleaned.get("signal_cards") or [])
    ]
    cleaned["decision_cards"] = [
        {
            **dict(item or {}),
            "supporting_signal_ids": sanitize_string_list((item or {}).get("supporting_signal_ids", []), limit=6),
            "opposing_signal_ids": sanitize_string_list((item or {}).get("opposing_signal_ids", []), limit=6),
        }
        for item in (cleaned.get("decision_cards") or [])
    ]
    if not cleaned["signal_cards"] and cleaned["fund_views"]:
        cleaned["signal_cards"] = signal_cards_from_views(str(cleaned.get("agent_name", "")), cleaned["fund_views"], {})
    if not cleaned["decision_cards"] and cleaned["fund_views"] and str(cleaned.get("agent_name", "") or "") in {"research_manager", "risk_manager", "portfolio_trader"}:
        cleaned["decision_cards"] = decision_cards_from_views(str(cleaned.get("agent_name", "")), cleaned["fund_views"], cleaned["signal_cards"])
    return cleaned


def compact_successful_outputs(prior_outputs: dict, names: list[str] | None = None) -> dict:
    return {name: compact_agent_output(output) for name, output in successful_outputs(prior_outputs, names).items()}


def attach_retrieved_evidence(agent_name: str, context: dict, base: dict, funds_payload: list[dict], source_funds: list[dict]) -> dict:
    retrieval = retrieve_agent_evidence(
        agent_name,
        context,
        index_payload=context.get("_evidence_index_payload"),
        relevant_funds=source_funds,
    )
    base["retrieved_evidence"] = retrieval
    base["evidence_items"] = retrieval.get("portfolio", [])
    base["fund_evidence_map"] = {
        fund_code: [
            {
                "evidence_id": item.get("evidence_id", ""),
                "fund_code": fund_code,
                "role": "retrieved",
                "relevance_score": item.get("retrieval_score", 0.0),
                "mapping_mode": item.get("mapping_mode", ""),
                "source_tier": item.get("source_tier", ""),
                "evidence_type": item.get("evidence_type", ""),
            }
            for item in items
        ]
        for fund_code, items in (retrieval.get("funds", {}) or {}).items()
    }
    enriched_funds = []
    retrieved_by_fund = retrieval.get("funds", {}) or {}
    for item in funds_payload:
        enriched = dict(item)
        fund_code = str(item.get("fund_code", "") or "").strip()
        if fund_code:
            enriched["retrieved_evidence"] = retrieved_by_fund.get(fund_code, [])
        enriched_funds.append(enriched)
    base["funds"] = enriched_funds
    return base


def build_agent_input(agent_name: str, context: dict, prior_outputs: dict) -> dict:
    base = {
        "analysis_date": context.get("analysis_date"),
        "mode": context.get("mode"),
        "portfolio_summary": context.get("portfolio_summary", {}),
        "constraints": context.get("constraints", {}),
        "memory_digest": context.get("memory_digest", {}),
        "source_health_summary": context.get("source_health_summary", []),
    }
    funds = context.get("funds", [])
    tactical_funds = [compact_fund_view(fund) for fund in funds if fund.get("role") == "tactical"]
    tactical_decision_funds = [compact_decision_fund_view(fund) for fund in funds if fund.get("role") == "tactical"]
    analyst_outputs = compact_successful_outputs(prior_outputs, DEFAULT_ANALYST_ORDER)

    if agent_name == "market_analyst":
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "intraday_proxy": compact_fund_view(fund)["intraday_proxy"],
                "estimated_nav": compact_fund_view(fund)["estimated_nav"],
                "quote": compact_fund_view(fund)["quote"],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "theme_analyst":
        base["external_reference"] = context.get("external_reference", {})
        return attach_retrieved_evidence(agent_name, context, base, tactical_funds, [fund for fund in funds if fund.get("role") == "tactical"])

    if agent_name == "fund_structure_analyst":
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "current_value": fund.get("current_value"),
                "cap_value": fund.get("cap_value"),
                "locked_amount": fund.get("locked_amount"),
                "allow_trade": fund.get("allow_trade"),
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "fund_quality_analyst":
        fund_payload = tactical_funds + [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "role": fund["role"],
                "style_group": fund.get("style_group"),
                "quote": compact_fund_view(fund)["quote"],
                "recent_news": fund.get("recent_news", [])[:2],
            }
            for fund in funds
            if fund.get("role") in {"core_dca", "fixed_hold"}
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "news_analyst":
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "recent_news": fund.get("recent_news", [])[:5],
                "evidence_refs": fund.get("evidence_refs", [])[:8],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name == "sentiment_analyst":
        base["external_reference"] = context.get("external_reference", {})
        fund_payload = [
            {
                "fund_code": fund["fund_code"],
                "fund_name": fund["fund_name"],
                "style_group": fund.get("style_group"),
                "intraday_proxy": compact_fund_view(fund)["intraday_proxy"],
                "estimated_nav": compact_fund_view(fund)["estimated_nav"],
                "quote": compact_fund_view(fund)["quote"],
                "recent_news": fund.get("recent_news", [])[:4],
                "evidence_refs": fund.get("evidence_refs", [])[:8],
            }
            for fund in funds
        ]
        return attach_retrieved_evidence(agent_name, context, base, fund_payload, funds)

    if agent_name in {"bull_researcher", "bear_researcher"}:
        base["analyst_outputs"] = analyst_outputs
        return attach_retrieved_evidence(agent_name, context, base, tactical_decision_funds, [fund for fund in funds if fund.get("role") == "tactical"])

    if agent_name == "research_manager":
        base["analyst_outputs"] = analyst_outputs
        base["researcher_outputs"] = compact_successful_outputs(prior_outputs, DEFAULT_RESEARCHER_ORDER)
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    if agent_name == "risk_manager":
        base["analyst_outputs"] = analyst_outputs
        base["researcher_outputs"] = compact_successful_outputs(prior_outputs, DEFAULT_RESEARCHER_ORDER)
        base["research_manager_output"] = compact_successful_outputs(prior_outputs, ["research_manager"]).get("research_manager", {})
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    if agent_name == "portfolio_trader":
        base["research_manager_output"] = compact_successful_outputs(prior_outputs, ["research_manager"]).get("research_manager", {})
        base["risk_manager_output"] = compact_successful_outputs(prior_outputs, ["risk_manager"]).get("risk_manager", {})
        return attach_retrieved_evidence(agent_name, context, base, [compact_decision_fund_view(fund) for fund in funds], funds)

    base["prior_outputs"] = compact_successful_outputs(prior_outputs)
    return attach_retrieved_evidence(agent_name, context, base, [compact_fund_view(fund) for fund in funds], funds)


def build_user_prompt(agent_name: str, agent_input: dict) -> str:
    return (
        f"岗位代号：{agent_name}\n"
        "请严格根据岗位职责分析输入 JSON。\n"
        "要求：\n"
        "1. 只基于输入给出结论，不要想象未提供的数据。\n"
        "2. 对每只基金写清为什么成立、主要风险、什么情况下失效。\n"
        "3. 若数据陈旧或证据不足，请明确降置信度或 abstain。\n"
        "4. fund_views 只保留真正重要的基金，宁缺毋滥。\n"
        "5. 不要输出'完成''结束''以下补充'等收尾句，不要用空白字符串填充列表。\n"
        "6. 返回严格 JSON。\n\n"
        "INPUT_JSON\n"
        + json.dumps(agent_input, ensure_ascii=False, indent=2)
    )


def write_issue_report(agent_home: Path, report_date: str, aggregate: dict, failures: list[dict]) -> Path:
    path = agent_home / "reports" / "daily" / f"{report_date}_agent_issues.md"
    lines = [
        f"# 多智能体问题报告 - {report_date}",
        "",
        f"- 生成时间：{aggregate['generated_at']}",
        f"- 失败智能体数量：{len(failures)}",
        "",
        "## 失败清单",
    ]
    for item in failures:
        lines.append(f"- `{item['agent_name']}`：{item['error']}")
    lines.extend(
        [
            "",
            "## 处理建议",
            "- 优先检查对应智能体 prompt 是否过长、是否引用了未提供字段。",
            "- 若失败发生在模型接口层，请检查上游网络波动与 SSE 返回是否完整。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def failed_record(agent_name: str, error: str, mode: str) -> dict:
    return {
        "status": "failed",
        "error": error,
        "output": {
            "agent_name": agent_name,
            "mode": mode,
            "summary": f"{agent_name} 执行失败。",
            "confidence": 0,
            "evidence_strength": "low",
            "data_freshness": "stale",
            "abstain": True,
            "missing_info": [error],
            "key_points": [],
            "portfolio_view": {
                "regime": "unknown",
                "risk_bias": "unknown",
                "key_drivers": [],
                "portfolio_implications": [],
            },
            "fund_views": [],
            "signal_cards": [],
            "decision_cards": [],
            "watchouts": [error],
        },
    }


def is_infrastructure_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    return any(
        token in text
        for token in (
            "http 502",
            "http 503",
            "http 504",
            "service temporarily unavailable",
            "upstream request failed",
            "sslcertverificationerror",
            "certificate verify failed",
            "connectionpool",
            "read timed out",
            "connecttimeout",
            "proxyerror",
        )
    )


def degraded_mock_record(agent_name: str, context: dict, error: str) -> dict:
    output = sanitize_agent_output(build_mock_output(agent_name, context))
    output["summary"] = f"{agent_name} 已因模型接口故障降级为 mock fallback。"
    output["missing_info"] = sanitize_string_list((output.get("missing_info") or []) + [error], limit=6)
    output["watchouts"] = sanitize_string_list((output.get("watchouts") or []) + [f"transport degraded: {error}"], limit=6)
    output["fallback_mode"] = "transport_degraded_mock"
    output["fallback_reason"] = error
    if output.get("fund_views"):
        if not output.get("signal_cards"):
            output["signal_cards"] = signal_cards_from_views(agent_name, output.get("fund_views", []), {"_context_evidence_map": context.get("fund_evidence_map", {})})
        if agent_name in {"research_manager", "risk_manager", "portfolio_trader"} and not output.get("decision_cards"):
            output["decision_cards"] = decision_cards_from_views(agent_name, output.get("fund_views", []), output.get("signal_cards", []))
    return {"status": "degraded", "output": output}


def configured_orders(agent_home: Path) -> tuple[list[str], list[str], list[str], dict]:
    config = load_agents_config(agent_home)
    agent_settings = config.get("agents", {})

    def enabled(names: list[str]) -> list[str]:
        items = []
        for name in names:
            if agent_settings.get(name, {}).get("enabled", True):
                items.append(name)
        return items

    analyst_order = enabled(DEFAULT_ANALYST_ORDER)
    researcher_order = enabled(DEFAULT_RESEARCHER_ORDER)
    manager_order = enabled(DEFAULT_MANAGER_ORDER)
    return analyst_order, researcher_order, manager_order, config


def configured_workers(config: dict) -> dict[str, int]:
    orchestrator = config.get("orchestrator", {})
    global_cap = int(orchestrator.get("max_parallel_agents", 3))
    analyst_cap = int(orchestrator.get("max_parallel_analysts", GROUP_MAX_WORKERS["analyst"]))
    researcher_cap = int(orchestrator.get("max_parallel_researchers", GROUP_MAX_WORKERS["researcher"]))
    return {
        "analyst": max(1, min(analyst_cap, global_cap)),
        "researcher": max(1, min(researcher_cap, global_cap)),
    }


def degradation_summary(aggregate: dict, manager_order: list[str]) -> dict:
    failed_names = [item.get("agent_name", "") for item in aggregate.get("failed_agents", []) if item.get("agent_name")]
    degraded_names = list(aggregate.get("degraded_agent_names", []) or [])
    blocking_failures = [name for name in manager_order if name in failed_names]
    committee_ready = all(str(aggregate.get("agents", {}).get(name, {}).get("status", "")).lower() in {"ok", "degraded"} for name in manager_order)
    degraded_ok = bool(failed_names or degraded_names) and committee_ready and not blocking_failures
    return {
        "failed_agent_names": failed_names,
        "degraded_agent_names": degraded_names,
        "blocking_failures": blocking_failures,
        "committee_ready": committee_ready,
        "degraded_ok": degraded_ok,
    }


def _agent_output(aggregate: dict, agent_name: str) -> dict:
    return aggregate.get("agents", {}).get(agent_name, {}).get("output", {}) or {}


def _case_items(output: dict, *, limit: int = 6) -> list[dict]:
    items: list[dict] = []
    for card in output.get("decision_cards", []) or []:
        items.append(
            {
                "fund_code": card.get("fund_code", ""),
                "action_bias": card.get("action_bias", ""),
                "thesis": card.get("thesis", card.get("comment", "")),
                "evidence_refs": card.get("evidence_refs", []) or card.get("supporting_signal_ids", []),
            }
        )
    for view in output.get("fund_views", []) or []:
        if len(items) >= limit:
            break
        items.append(
            {
                "fund_code": view.get("fund_code", ""),
                "action_bias": view.get("action_bias", ""),
                "thesis": view.get("thesis", view.get("comment", "")),
                "evidence_refs": view.get("evidence_refs", []),
            }
        )
    return items[:limit]


def build_committee_summary(aggregate: dict) -> dict:
    bull = _agent_output(aggregate, "bull_researcher")
    bear = _agent_output(aggregate, "bear_researcher")
    manager = _agent_output(aggregate, "research_manager")
    risk = _agent_output(aggregate, "risk_manager")
    failed = aggregate.get("failed_agent_names", []) or [item.get("agent_name", "") for item in aggregate.get("failed_agents", [])]
    risk_vetoes = []
    for card in risk.get("decision_cards", []) or []:
        risk_decision = str(card.get("risk_decision", "") or "").lower()
        action_bias = str(card.get("action_bias", "") or "").lower()
        if risk_decision in {"reject", "veto"} or action_bias in {"reject", "avoid", "reduce"} or card.get("downgrade_reason"):
            risk_vetoes.append(
                {
                    "fund_code": card.get("fund_code", ""),
                    "risk_decision": card.get("risk_decision", ""),
                    "action_bias": card.get("action_bias", ""),
                    "reason": card.get("downgrade_reason") or card.get("comment") or card.get("thesis", ""),
                    "evidence_refs": card.get("evidence_refs", []) or card.get("opposing_signal_ids", []),
                }
            )
    confidence = "high" if aggregate.get("committee_ready") and not failed else "medium" if aggregate.get("degraded_ok") else "low"
    decision_source = "fallback" if failed and not aggregate.get("committee_ready") else "risk_constrained" if risk_vetoes else "manager_consensus"
    return {
        "schema_version": 1,
        "debate_summary": [item for item in [bull.get("summary", ""), bear.get("summary", ""), manager.get("summary", ""), risk.get("summary", "")] if item][:6],
        "bull_case": _case_items(bull),
        "bear_case": _case_items(bear),
        "risk_vetoes": risk_vetoes,
        "manager_decision": {
            "summary": manager.get("summary", ""),
            "portfolio_view": manager.get("portfolio_view", {}),
            "decision_cards": (manager.get("decision_cards", []) or [])[:8],
        },
        "manager_responses": manager.get("response_to_bear_case", []) or manager.get("key_points", [])[:6],
        "unresolved_conflicts": bear.get("key_points", [])[:3] if risk_vetoes or failed else [],
        "committee_confidence": confidence,
        "decision_source": decision_source,
    }


def execute_agent(agent_home: Path, context: dict, prior_outputs: dict, agent_name: str, use_mock: bool, agent_roles: dict[str, str], agent_dependencies: dict[str, list[str]]) -> tuple[str, dict, dict | None, dict]:
    started_at = time.perf_counter()
    started_at_text = timestamp_now()
    print(f">>> AGENT_START {agent_name}", flush=True)
    agent_input = build_agent_input(agent_name, context, prior_outputs)
    user_prompt = build_user_prompt(agent_name, agent_input)
    trace = {
        "agent_name": agent_name,
        "stage": agent_roles.get(agent_name, "unknown"),
        "status": "running",
        "reused_existing": False,
        "dependencies": list(agent_dependencies.get(agent_name, [])),
        "dependency_statuses": {
            name: str(prior_outputs.get(name, {}).get("status", "missing") or "missing")
            for name in agent_dependencies.get(agent_name, [])
        },
        "prompt_sha256": stable_digest(AGENT_PROMPTS.get(agent_name, "")),
        "user_prompt_sha256": stable_digest(user_prompt),
        "agent_input_sha256": stable_digest(agent_input),
        "retrieval_summary": retrieval_summary(agent_input),
        "started_at": started_at_text,
        "finished_at": "",
        "elapsed_seconds": 0.0,
        "use_mock": bool(use_mock),
    }
    try:
        if use_mock:
            output = build_mock_output(agent_name, context)
        else:
            result = call_json_agent(
                agent_home,
                AGENT_PROMPTS[agent_name],
                user_prompt,
                max_attempts=AGENT_ATTEMPTS.get(agent_name, 3),
                reasoning_effort=AGENT_EFFORTS.get(agent_name, "medium"),
                request_name=agent_name,
                text_verbosity=AGENT_VERBOSITY.get(agent_name),
                max_output_tokens=AGENT_MAX_OUTPUT_TOKENS.get(agent_name),
                fallback_defaults={"agent_name": agent_name, "mode": context.get("mode", "intraday")},
            )
            output = sanitize_agent_output(result["response_json"])
        if use_mock:
            output = sanitize_agent_output(output)
        if output.get("fund_views"):
            if not output.get("signal_cards"):
                output["signal_cards"] = signal_cards_from_views(agent_name, output.get("fund_views", []), {"_context_evidence_map": context.get("fund_evidence_map", {})})
            if agent_name in {"research_manager", "risk_manager", "portfolio_trader"} and not output.get("decision_cards"):
                output["decision_cards"] = decision_cards_from_views(agent_name, output.get("fund_views", []), output.get("signal_cards", []))
        elapsed = time.perf_counter() - started_at
        trace.update(
            {
                "status": "ok",
                "finished_at": timestamp_now(),
                "elapsed_seconds": round(elapsed, 3),
                "output_sha256": stable_digest(output),
            }
        )
        print(f">>> AGENT_DONE {agent_name} ({elapsed:.1f}s)", flush=True)
        return agent_name, {"status": "ok", "output": output}, None, trace
    except Exception as exc:
        error_text = str(exc)
        if not use_mock and is_infrastructure_error(error_text):
            record = degraded_mock_record(agent_name, context, error_text)
            elapsed = time.perf_counter() - started_at
            trace.update(
                {
                    "status": "degraded",
                    "finished_at": timestamp_now(),
                    "elapsed_seconds": round(elapsed, 3),
                    "error": error_text,
                    "fallback_mode": "transport_degraded_mock",
                    "output_sha256": stable_digest(record.get("output", {})),
                }
            )
            print(f">>> AGENT_DEGRADED {agent_name} ({elapsed:.1f}s) {error_text}", flush=True)
            return agent_name, record, None, trace
        failure = {"agent_name": agent_name, "error": str(exc)}
        record = failed_record(agent_name, str(exc), context.get("mode", "intraday"))
        elapsed = time.perf_counter() - started_at
        trace.update(
            {
                "status": "failed",
                "finished_at": timestamp_now(),
                "elapsed_seconds": round(elapsed, 3),
                "error": error_text,
                "output_sha256": stable_digest(record.get("output", {})),
            }
        )
        print(f">>> AGENT_FAIL {agent_name} ({elapsed:.1f}s) {exc}", flush=True)
        return agent_name, record, failure, trace


def save_agent_record(output_dir: Path, snapshot_dir: Path | None, agent_name: str, record: dict) -> None:
    dump_json(output_dir / f"{agent_name}.json", record)
    if snapshot_dir is not None:
        dump_json(snapshot_dir / f"{agent_name}.json", record)


def merge_agent_result(aggregate: dict, output_dir: Path, snapshot_dir: Path | None, agent_name: str, record: dict, failure: dict | None, trace: dict | None = None) -> None:
    aggregate["agents"][agent_name] = record
    save_agent_record(output_dir, snapshot_dir, agent_name, record)
    if trace is not None:
        aggregate.setdefault("workflow_trace", {})[agent_name] = trace
    if str(record.get("status", "")).lower() == "degraded":
        aggregate["all_agents_ok"] = False
        aggregate.setdefault("degraded_agent_names", []).append(agent_name)
    if failure is not None:
        aggregate["all_agents_ok"] = False
        aggregate["failed_agents"].append(failure)


def run_agent_group(
    agent_home: Path,
    context: dict,
    aggregate: dict,
    output_dir: Path,
    snapshot_dir: Path | None,
    agent_names: list[str],
    use_mock: bool,
    max_workers: int,
) -> None:
    if not agent_names:
        return
    prior_outputs = dict(aggregate["agents"])
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(agent_names)))) as executor:
        futures = {
            executor.submit(execute_agent, agent_home, context, prior_outputs, agent_name, use_mock, aggregate.get("agent_roles", {}), aggregate.get("agent_dependencies", {})): agent_name
            for agent_name in agent_names
        }
        for future in as_completed(futures):
            agent_name, record, failure, trace = future.result()
            merge_agent_result(aggregate, output_dir, snapshot_dir, agent_name, record, failure, trace)


def write_workflow_artifacts(output_dir: Path, snapshot_dir: Path | None, workflow_meta: dict, workflow_trace: dict) -> None:
    trace_payload = {
        "generated_at": timestamp_now(),
        "workflow": workflow_meta,
        "agents": workflow_trace,
    }
    dump_json(output_dir / "workflow_definition.json", workflow_meta)
    dump_json(output_dir / "workflow_trace.json", trace_payload)
    if snapshot_dir is not None:
        dump_json(snapshot_dir / "workflow_definition.json", workflow_meta)
        dump_json(snapshot_dir / "workflow_trace.json", trace_payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-agent research layer and save outputs.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock outputs for all agents.")
    parser.add_argument("--only", nargs="*", help="Run only the specified agents.")
    parser.add_argument("--use-existing", action="store_true", help="Reuse existing successful agent outputs when present.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    context = load_json(llm_context_path(agent_home, report_date))
    evidence_path = evidence_index_path(agent_home, report_date)
    evidence_index_source = "disk"
    if evidence_path.exists():
        context["_evidence_index_payload"] = load_json(evidence_path)
    else:
        context["_evidence_index_payload"] = build_evidence_index_payload(context)
        evidence_index_source = "rebuilt_in_process"
    analyst_order, researcher_order, manager_order, agents_config = configured_orders(agent_home)
    worker_caps = configured_workers(agents_config)
    snapshot_enabled = bool(agents_config.get("orchestrator", {}).get("snapshot_enabled", True))

    output_dir = agent_output_dir(agent_home, report_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = next_snapshot_dir(agent_home, report_date) if snapshot_enabled else None

    ordered_agents = analyst_order + researcher_order + manager_order
    if args.only:
        ordered_agents = [name for name in ordered_agents if name in set(args.only)]
    agent_roles = build_agent_roles(analyst_order, researcher_order, manager_order, ordered_agents)
    agent_groups = {
        "analyst": [name for name in analyst_order if name in ordered_agents],
        "researcher": [name for name in researcher_order if name in ordered_agents],
        "manager": [name for name in manager_order if name in ordered_agents],
    }
    agent_dependencies = build_agent_dependencies(ordered_agents, analyst_order, researcher_order, manager_order)
    workflow_meta = workflow_definition(
        ordered_agents=ordered_agents,
        agent_roles=agent_roles,
        agent_groups=agent_groups,
        agent_dependencies=agent_dependencies,
        worker_caps=worker_caps,
        use_existing=bool(args.use_existing),
        use_mock=bool(args.mock),
        snapshot_enabled=snapshot_enabled,
        evidence_index_source=evidence_index_source,
    )

    aggregate = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "workflow_version": WORKFLOW_VERSION,
        "agent_input_contract_version": AGENT_INPUT_CONTRACT_VERSION,
        "prompt_bundle_version": workflow_meta["prompt_bundle"]["version"],
        "prompt_bundle_sha256": workflow_meta["prompt_bundle"]["digest"],
        "all_agents_ok": True,
        "failed_agents": [],
        "degraded_agent_names": [],
        "failed_agent_names": [],
        "blocking_failures": [],
        "degraded_ok": False,
        "committee_ready": False,
        "ordered_agents": ordered_agents,
        "required_committee_agents": [name for name in manager_order if name in ordered_agents],
        "agent_roles": agent_roles,
        "agent_groups": agent_groups,
        "agent_dependencies": agent_dependencies,
        "research_flow": build_stage_flow(agent_groups),
        "workflow_meta": workflow_meta,
        "workflow_trace": {},
        "agents": {},
    }
    if snapshot_dir is not None:
        dump_json(snapshot_dir / "context.json", context)
    write_workflow_artifacts(output_dir, snapshot_dir, workflow_meta, aggregate["workflow_trace"])

    if args.use_existing:
        for path in sorted(output_dir.glob("*.json")):
            if path.name in {"aggregate.json", "workflow_definition.json", "workflow_trace.json"}:
                continue
            try:
                existing = load_json(path)
            except Exception:
                continue
            if existing.get("status") == "ok":
                aggregate["agents"][path.stem] = existing

    for agent_name in ordered_agents:
        existing_path = output_dir / f"{agent_name}.json"
        if args.use_existing and existing_path.exists():
            existing = load_json(existing_path)
            if existing.get("status") == "ok":
                aggregate["agents"][agent_name] = existing
                aggregate["workflow_trace"][agent_name] = trace_from_existing(
                    agent_name,
                    existing,
                    agent_roles.get(agent_name, "unknown"),
                    agent_dependencies.get(agent_name, []),
                )
                if snapshot_dir is not None:
                    dump_json(snapshot_dir / f"{agent_name}.json", existing)

    def pending(group: list[str]) -> list[str]:
        return [name for name in group if name in ordered_agents and aggregate["agents"].get(name, {}).get("status") != "ok"]

    run_agent_group(
        agent_home,
        context,
        aggregate,
        output_dir,
        snapshot_dir,
        pending(analyst_order),
        args.mock,
        worker_caps["analyst"],
    )
    run_agent_group(
        agent_home,
        context,
        aggregate,
        output_dir,
        snapshot_dir,
        pending(researcher_order),
        args.mock,
        worker_caps["researcher"],
    )
    for agent_name in [name for name in manager_order if name in ordered_agents]:
        if aggregate["agents"].get(agent_name, {}).get("status") == "ok":
            continue
        name, record, failure, trace = execute_agent(
            agent_home,
            context,
            dict(aggregate["agents"]),
            agent_name,
            args.mock,
            aggregate.get("agent_roles", {}),
            aggregate.get("agent_dependencies", {}),
        )
        merge_agent_result(aggregate, output_dir, snapshot_dir, name, record, failure, trace)

    write_workflow_artifacts(output_dir, snapshot_dir, workflow_meta, aggregate["workflow_trace"])
    dump_json(output_dir / "aggregate.json", aggregate)
    if snapshot_dir is not None:
        dump_json(snapshot_dir / "aggregate.json", aggregate)

    summary = degradation_summary(aggregate, [name for name in manager_order if name in ordered_agents])
    aggregate.update(summary)
    aggregate["stage_status"] = build_stage_status(aggregate)
    aggregate["committee"] = build_committee_summary(aggregate)
    write_workflow_artifacts(output_dir, snapshot_dir, workflow_meta, aggregate["workflow_trace"])
    issue_path = None
    if aggregate["failed_agents"] and not args.mock:
        issue_path = write_issue_report(agent_home, report_date, aggregate, aggregate["failed_agents"])
        aggregate["issue_report_path"] = str(issue_path)
        dump_json(output_dir / "aggregate.json", aggregate)
        if snapshot_dir is not None:
            dump_json(snapshot_dir / "aggregate.json", aggregate)
        failed_names = ", ".join(summary["failed_agent_names"])
        if summary["blocking_failures"]:
            blocking_text = ", ".join(summary["blocking_failures"])
            raise SystemExit(f"多智能体执行未完整成功，阻塞角色：{blocking_text}。全部失败角色：{failed_names}。问题报告：{issue_path}")
        print(f">>> AGENT_DEGRADED committee_ready=true failed={failed_names}", flush=True)

    if issue_path is None:
        dump_json(output_dir / "aggregate.json", aggregate)
        if snapshot_dir is not None:
            dump_json(snapshot_dir / "aggregate.json", aggregate)
    print(output_dir / "aggregate.json")


if __name__ == "__main__":
    main()
