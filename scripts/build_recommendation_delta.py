from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, load_json, recommendation_delta_path, resolve_agent_home, resolve_date, validated_advice_path


def action_map(payload: dict) -> dict[str, dict]:
    mapping = {}
    for section in ("tactical_actions", "dca_actions", "hold_actions"):
        for item in payload.get(section, []) or []:
            if item.get("fund_code"):
                mapping[item["fund_code"]] = item
    return mapping


def previous_payload(agent_home, report_date: str) -> dict:
    base_dir = resolve_agent_home(agent_home) / "db" / "validated_advice"
    if not base_dir.exists():
        return {}
    for path in sorted(base_dir.glob("*.json"), key=lambda item: item.stem, reverse=True):
        if path.stem >= report_date:
            continue
        payload = load_json(path)
        if payload:
            return payload
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build recommendation deltas versus the previous available validated advice.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    current = load_json(validated_advice_path(agent_home, report_date))
    previous = previous_payload(agent_home, report_date)
    current_map = action_map(current)
    previous_map = action_map(previous)
    deltas = []
    for fund_code in sorted(set(current_map) | set(previous_map)):
        curr = current_map.get(fund_code, {})
        prev = previous_map.get(fund_code, {})
        prev_action = str(prev.get("validated_action", "") or "")
        new_action = str(curr.get("validated_action", "") or "")
        prev_amount = float(prev.get("validated_amount", 0.0) or 0.0)
        new_amount = float(curr.get("validated_amount", 0.0) or 0.0)
        if prev_action == new_action and round(prev_amount, 2) == round(new_amount, 2):
            continue
        category = "new_decision" if not prev else ("action_changed" if prev_action != new_action else "amount_changed")
        deltas.append(
            {
                "fund_code": fund_code,
                "fund_name": curr.get("fund_name", prev.get("fund_name", "")),
                "prev_action": prev_action,
                "prev_amount": prev_amount,
                "new_action": new_action,
                "new_amount": new_amount,
                "delta_reason": curr.get("thesis", prev.get("thesis", "")),
                "reason_category": category,
                "new_evidence_ids": curr.get("source_signal_ids", []),
                "removed_evidence_ids": prev.get("source_signal_ids", []),
                "memory_ids": [],
                "constraint_hits": curr.get("constraint_hits", []),
            }
        )
    payload = {"report_date": report_date, "generated_at": current.get("generated_at", ""), "items": deltas}
    current["recommendation_deltas"] = deltas
    dump_json(validated_advice_path(agent_home, report_date), current)
    print(dump_json(recommendation_delta_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
