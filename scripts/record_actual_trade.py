from __future__ import annotations

import argparse
import json

from common import ensure_layout, resolve_agent_home
from execution_sync import record_actual_trade


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an actual Alipay fund operation.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date", dest="trade_date")
    parser.add_argument("--time", dest="trade_time", default="")
    parser.add_argument("--fund-code", required=True)
    parser.add_argument("--fund-name", default="")
    parser.add_argument("--operation-type", required=True, choices=["buy", "sell", "dca", "dividend", "fee", "cancel"])
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument("--units", type=float)
    parser.add_argument("--nav", type=float)
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--confirm-date", default="")
    parser.add_argument("--settlement-date", default="")
    parser.add_argument("--linked-suggestion-id", default="")
    parser.add_argument("--linked-advice-date", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    result = record_actual_trade(
        agent_home,
        {
            "trade_date": args.trade_date,
            "trade_time": args.trade_time,
            "fund_code": args.fund_code,
            "fund_name": args.fund_name,
            "operation_type": args.operation_type,
            "amount": args.amount,
            "units": args.units,
            "nav": args.nav,
            "fee": args.fee,
            "confirm_date": args.confirm_date,
            "settlement_date": args.settlement_date,
            "linked_suggestion_id": args.linked_suggestion_id,
            "linked_advice_date": args.linked_advice_date,
            "user_note": args.note,
            "source": "manual",
            "platform": "alipay",
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
