from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from common import dump_json, ensure_layout, evaluation_snapshot_path, load_json, resolve_agent_home, resolve_date, timestamp_now


def iter_review_payloads(agent_home):
    for relative in ("db/review_results", "db/execution_reviews"):
        base = resolve_agent_home(agent_home) / relative
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            payload = load_json(path)
            if payload:
                yield payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate review outputs into evaluation scorecards.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Snapshot date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)

    decision_scorecard = Counter()
    no_trade_baseline = Counter()
    theme_scorecard: dict[str, Counter] = defaultdict(Counter)
    agent_scorecard: dict[str, Counter] = defaultdict(Counter)
    memory_effect_scorecard = Counter()
    news_source_scorecard = Counter()
    sentiment_usefulness_scorecard = Counter()

    for payload in iter_review_payloads(agent_home):
        for item in payload.get("items", []) or []:
            action = str(item.get("source_action", "hold") or "hold")
            outcome = str(item.get("outcome", "unknown") or "unknown")
            decision_scorecard[f"{action}:{outcome}"] += 1
            no_trade_baseline[str(item.get("no_trade_baseline", "unknown") or "unknown")] += 1
            for hint in item.get("candidate_memory_hints", []) or []:
                memory_effect_scorecard[hint] += 1
            if "news" in str(item.get("diagnostic_reason", "")).lower():
                news_source_scorecard["news_linked"] += 1
            if "sentiment" in str(item.get("diagnostic_reason", "")).lower():
                sentiment_usefulness_scorecard["sentiment_linked"] += 1
            theme_scorecard[str(item.get("benchmark_name", "unknown") or "unknown")][outcome] += 1
            for agent_name in item.get("agent_support", []) or []:
                agent_scorecard[agent_name][outcome] += 1

    payload = {
        "report_date": report_date,
        "generated_at": timestamp_now(),
        "decision_scorecard": dict(decision_scorecard),
        "no_trade_baseline_scorecard": dict(no_trade_baseline),
        "theme_scorecard": {key: dict(value) for key, value in theme_scorecard.items()},
        "agent_scorecard": {key: dict(value) for key, value in agent_scorecard.items()},
        "memory_effect_scorecard": dict(memory_effect_scorecard),
        "news_source_scorecard": dict(news_source_scorecard),
        "sentiment_usefulness_scorecard": dict(sentiment_usefulness_scorecard),
    }
    print(dump_json(evaluation_snapshot_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
