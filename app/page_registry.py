from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageSpec:
    key: str
    nav_label: str
    legacy_titles: tuple[str, ...] = ()
    show_in_nav: bool = True


PRIMARY_PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec("dash", "总览", ("首页", "今天")),
    PageSpec("portfolio", "配置", ("组合", "组合策略")),
    PageSpec("holdings", "持仓走势"),
    PageSpec("research", "研究", ("建议", "研究建议", "今日动作", "动作")),
    PageSpec("trade", "交易", ("交易执行",)),
    PageSpec("review", "Learning", ("复盘记忆", "复盘")),
    PageSpec("rt", "实时", ("实时监控",)),
    PageSpec("agents", "Agents", ("智能体",)),
    PageSpec("runtime", "运行"),
    PageSpec("settings", "设置", ("设置数据",)),
)

HIDDEN_PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec("fund_detail", "基金详情", show_in_nav=False),
)

PAGE_SPECS = PRIMARY_PAGE_SPECS + HIDDEN_PAGE_SPECS
PAGE_SPEC_BY_KEY = {spec.key: spec for spec in PAGE_SPECS}


def hidden_page_keys() -> list[str]:
    return [spec.key for spec in HIDDEN_PAGE_SPECS]


def qt_nav_items() -> list[tuple[str, str]]:
    return [(spec.key, spec.nav_label) for spec in PRIMARY_PAGE_SPECS if spec.show_in_nav]


def legacy_page_key_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for spec in PAGE_SPECS:
        mapping[spec.key] = spec.key
        mapping[spec.nav_label] = spec.key
        for title in spec.legacy_titles:
            mapping[title] = spec.key
    return mapping


def normalize_page_key(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return legacy_page_key_map().get(text, text)
