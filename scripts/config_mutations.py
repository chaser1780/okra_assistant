from __future__ import annotations

import json
from pathlib import Path
import tomllib

from common import load_portfolio, load_watchlist, portfolio_definition_path, timestamp_now
from portfolio_state import save_portfolio_state


def toml_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.1f}" if value == int(value) else str(value)
    if isinstance(value, list):
        inner = ", ".join(toml_literal(item) for item in value)
        return f"[{inner}]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def dump_toml(path: Path, payload: dict) -> Path:
    lines: list[str] = []
    root_scalars = {key: value for key, value in payload.items() if not isinstance(value, dict)}
    for key, value in root_scalars.items():
        lines.append(f"{key} = {toml_literal(value)}")
    if root_scalars:
        lines.append("")

    def emit_section(prefix: str, data: dict) -> None:
        section_scalars = {key: value for key, value in data.items() if not isinstance(value, dict)}
        lines.append(f"[{prefix}]")
        for key, value in section_scalars.items():
            lines.append(f"{key} = {toml_literal(value)}")
        lines.append("")
        for key, value in data.items():
            if isinstance(value, dict):
                emit_section(f"{prefix}.{key}", value)

    for key, value in payload.items():
        if isinstance(value, dict):
            emit_section(key, value)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def update_strategy_controls(
    agent_home: Path,
    *,
    risk_profile: str,
    cash_hub_floor: float,
    gross_trade_limit: float,
    net_buy_limit: float,
    dca_amount: float,
    report_mode: str,
    core_target_pct: float | None = None,
    satellite_target_pct: float | None = None,
    tactical_target_pct: float | None = None,
    defense_target_pct: float | None = None,
    rebalance_band_pct: float | None = None,
) -> Path:
    path = agent_home / "config" / "strategy.toml"
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("portfolio", {})
    payload.setdefault("core_dca", {})
    payload.setdefault("schedule", {})
    payload.setdefault("allocation", {})
    payload["allocation"].setdefault("targets", {})
    payload["portfolio"]["risk_profile"] = risk_profile
    payload["portfolio"]["cash_hub_floor"] = round(float(cash_hub_floor), 2)
    payload["portfolio"]["daily_max_trade_amount"] = round(float(gross_trade_limit), 2)
    payload["portfolio"]["daily_max_gross_trade_amount"] = round(float(gross_trade_limit), 2)
    payload["portfolio"]["daily_max_net_buy_amount"] = round(float(net_buy_limit), 2)
    payload["core_dca"]["amount_per_fund"] = round(float(dca_amount), 2)
    payload["schedule"]["report_mode"] = report_mode
    if core_target_pct is not None:
        payload["allocation"]["targets"]["core_long_term"] = round(float(core_target_pct), 2)
    if satellite_target_pct is not None:
        payload["allocation"]["targets"]["satellite_mid_term"] = round(float(satellite_target_pct), 2)
    if tactical_target_pct is not None:
        payload["allocation"]["targets"]["tactical_short_term"] = round(float(tactical_target_pct), 2)
    if defense_target_pct is not None:
        payload["allocation"]["targets"]["cash_defense"] = round(float(defense_target_pct), 2)
    if rebalance_band_pct is not None:
        payload["allocation"]["rebalance_band_pct"] = round(float(rebalance_band_pct), 2)
    return dump_toml(path, payload)


def update_fund_cap_value(agent_home: Path, fund_code: str, cap_value: float) -> tuple[Path, Path]:
    definition_path = portfolio_definition_path(agent_home)
    if not definition_path.exists():
        load_portfolio(agent_home)
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    for item in definition.get("funds", []):
        if item.get("fund_code") == fund_code:
            item["cap_value"] = round(float(cap_value), 2)
            break
    definition["updated_at"] = timestamp_now()
    definition_path.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")

    portfolio = load_portfolio(agent_home)
    for fund in portfolio.get("funds", []):
        if fund.get("fund_code") == fund_code:
            fund["cap_value"] = round(float(cap_value), 2)
            break
    current_path, _snapshot = save_portfolio_state(
        agent_home,
        portfolio,
        source="config_update",
        event_date=portfolio.get("as_of_date", "") or "unknown",
        event_type="config_update",
    )
    return definition_path, current_path


def update_fund_dca_settings(
    agent_home: Path,
    fund_code: str,
    *,
    enabled: bool,
    daily_amount: float,
    allow_extra_buys: bool,
) -> tuple[Path, Path]:
    definition_path = portfolio_definition_path(agent_home)
    if not definition_path.exists():
        load_portfolio(agent_home)
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    portfolio = load_portfolio(agent_home)

    definition_item = next((item for item in definition.get("funds", []) if item.get("fund_code") == fund_code), None)
    current_item = next((item for item in portfolio.get("funds", []) if item.get("fund_code") == fund_code), None)
    if definition_item is None or current_item is None:
        raise RuntimeError(f"Fund code not found: {fund_code}")

    current_role = str(current_item.get("role", "") or definition_item.get("role", "")).strip()
    if enabled and current_role not in {"tactical", "core_dca"}:
        raise RuntimeError("Only tactical or existing core_dca funds can be configured for daily DCA.")
    amount = round(float(daily_amount), 2)
    if enabled and amount <= 0:
        raise RuntimeError("Daily DCA amount must be greater than 0 when enabled.")

    def apply_to_record(record: dict) -> None:
        role = str(record.get("role", "")).strip()
        if enabled:
            if role != "core_dca":
                record["previous_role_before_dca"] = role or "tactical"
            record["role"] = "core_dca"
            record["fixed_daily_buy_amount"] = amount
            record["allow_extra_buys"] = bool(allow_extra_buys)
        else:
            restore_role = str(record.get("previous_role_before_dca", "")).strip() or ("tactical" if role == "core_dca" else role or "tactical")
            if role == "core_dca":
                record["role"] = restore_role
            record.pop("previous_role_before_dca", None)
            record.pop("fixed_daily_buy_amount", None)
            record["allow_extra_buys"] = False

    apply_to_record(definition_item)
    apply_to_record(current_item)

    definition["updated_at"] = timestamp_now()
    definition_path.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")
    current_path, _snapshot = save_portfolio_state(
        agent_home,
        portfolio,
        source="config_update",
        event_date=portfolio.get("as_of_date", "") or "unknown",
        event_type="config_update",
    )
    return definition_path, current_path


def upsert_watchlist_item(
    agent_home: Path,
    *,
    code: str,
    name: str,
    category: str,
    benchmark: str,
    risk_level: str,
) -> Path:
    path = agent_home / "config" / "watchlist.json"
    payload = load_watchlist(agent_home)
    funds = [item for item in payload.get("funds", []) if item.get("code") != code]
    funds.append(
        {
            "code": code,
            "name": name,
            "category": category,
            "benchmark": benchmark,
            "risk_level": risk_level,
        }
    )
    payload["funds"] = sorted(funds, key=lambda item: item.get("code", ""))
    payload["updated_at"] = timestamp_now()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def remove_watchlist_item(agent_home: Path, code: str) -> Path:
    path = agent_home / "config" / "watchlist.json"
    payload = load_watchlist(agent_home)
    payload["funds"] = [item for item in payload.get("funds", []) if item.get("code") != code]
    payload["updated_at"] = timestamp_now()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
