from __future__ import annotations

import argparse
import json
from copy import deepcopy

from common import ensure_layout, load_json, load_portfolio, resolve_agent_home, resolve_date, trade_journal_path, validated_advice_path
from portfolio_state import upsert_execution_status
from update_portfolio_from_trade import apply_trade, find_cash_hub, save_portfolio


def summarize_before_after(before: dict, after: dict, fund_code: str) -> dict:
    before_cash = find_cash_hub(before)
    after_cash = find_cash_hub(after)
    before_fund = next(item for item in before["funds"] if item["fund_code"] == fund_code)
    after_fund = next(item for item in after["funds"] if item["fund_code"] == fund_code)
    return {
        "fund": {
            "fund_code": fund_code,
            "before_value": round(float(before_fund.get("current_value", 0.0)), 2),
            "after_value": round(float(after_fund.get("current_value", 0.0)), 2),
            "before_units": round(float(before_fund.get("holding_units", 0.0)), 6),
            "after_units": round(float(after_fund.get("holding_units", 0.0)), 6),
            "before_pnl": round(float(before_fund.get("holding_pnl", 0.0)), 2),
            "after_pnl": round(float(after_fund.get("holding_pnl", 0.0)), 2),
        },
        "cash_hub": {
            "fund_code": before_cash.get("fund_code") if before_cash else "",
            "before_value": round(float(before_cash.get("current_value", 0.0)), 2) if before_cash else 0.0,
            "after_value": round(float(after_cash.get("current_value", 0.0)), 2) if after_cash else 0.0,
            "before_units": round(float(before_cash.get("holding_units", 0.0)), 6) if before_cash else 0.0,
            "after_units": round(float(after_cash.get("holding_units", 0.0)), 6) if after_cash else 0.0,
        },
        "portfolio": {
            "before_total_value": round(float(before.get("total_value", 0.0)), 2),
            "after_total_value": round(float(after.get("total_value", 0.0)), 2),
            "before_holding_pnl": round(float(before.get("holding_pnl", 0.0)), 2),
            "after_holding_pnl": round(float(after.get("holding_pnl", 0.0)), 2),
        },
    }


def match_suggestion(agent_home, trade_date: str, fund_code: str, action: str) -> dict | None:
    path = validated_advice_path(agent_home, trade_date)
    if not path.exists():
        return None
    payload = load_json(path)
    wanted_actions = {
        "buy": {"add", "scheduled_dca"},
        "switch_in": {"add"},
        "sell": {"reduce"},
        "switch_out": {"switch_out", "reduce"},
    }.get(action, set())
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for item in payload.get(section, []) or []:
            if item.get("fund_code") != fund_code:
                continue
            if item.get("validated_action") in wanted_actions:
                return item
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a manual trade into the trade journal and update portfolio state.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--fund-code", required=True)
    parser.add_argument("--fund-name", required=True)
    parser.add_argument("--action", required=True, choices=["buy", "sell", "switch_in", "switch_out"])
    parser.add_argument("--amount", required=True, type=float)
    parser.add_argument("--trade-nav", type=float, help="Optional trade NAV for precise unit updates.")
    parser.add_argument("--units", type=float, help="Optional exact units for this trade.")
    parser.add_argument("--note", default="")
    parser.add_argument("--suggestion-id", default="")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    trade_date = resolve_date(args.date)
    path = trade_journal_path(agent_home, trade_date)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"trade_date": trade_date, "items": []}
    payload["items"].append({
        "fund_code": args.fund_code,
        "fund_name": args.fund_name,
        "action": args.action,
        "amount": args.amount,
        "trade_nav": args.trade_nav,
        "units": args.units,
        "note": args.note,
    })
    suggestion = match_suggestion(agent_home, trade_date, args.fund_code, args.action)
    if args.suggestion_id:
        suggestion_path = validated_advice_path(agent_home, trade_date)
        if suggestion_path.exists():
            validated = load_json(suggestion_path)
            for section in ("tactical_actions", "dca_actions", "hold_actions"):
                for item in validated.get(section, []) or []:
                    if item.get("suggestion_id") == args.suggestion_id:
                        suggestion = item
                        break
                if suggestion and suggestion.get("suggestion_id") == args.suggestion_id:
                    break
    if suggestion:
        payload["items"][-1]["suggestion_id"] = suggestion.get("suggestion_id", "")
        payload["items"][-1]["suggestion_date"] = trade_date
        payload["items"][-1]["matched_suggestion_action"] = suggestion.get("validated_action", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    portfolio = load_portfolio(agent_home)
    before = deepcopy(portfolio)
    updated = apply_trade(portfolio, args.fund_code, args.action, args.amount, trade_nav=args.trade_nav, trade_units=args.units)
    portfolio_path = save_portfolio(agent_home, updated, event_date=trade_date, source="trade_update")
    if suggestion and suggestion.get("suggestion_id"):
        upsert_execution_status(
            agent_home,
            trade_date,
            {
                "suggestion_id": suggestion.get("suggestion_id"),
                "fund_code": args.fund_code,
                "fund_name": args.fund_name,
                "suggested_action": suggestion.get("validated_action", ""),
                "trade_action": args.action,
                "trade_amount": args.amount,
                "status": "executed",
                "linked_trade_date": trade_date,
                "linked_note": args.note,
            },
        )
    summary = summarize_before_after(before, updated, args.fund_code)
    if suggestion:
        summary["matched_suggestion"] = {
            "suggestion_id": suggestion.get("suggestion_id", ""),
            "validated_action": suggestion.get("validated_action", ""),
            "validated_amount": suggestion.get("validated_amount", 0.0),
        }
    print(path)
    print(portfolio_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
