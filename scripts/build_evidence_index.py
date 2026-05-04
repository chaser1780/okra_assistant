from __future__ import annotations

import argparse

from common import dump_json, ensure_layout, evidence_index_path, llm_context_path, load_json, resolve_agent_home, resolve_date
from evidence_index import build_evidence_index_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an indexed evidence artifact from llm_context.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    context = load_json(llm_context_path(agent_home, report_date))
    payload = build_evidence_index_payload(context)
    print(dump_json(evidence_index_path(agent_home, report_date), payload))


if __name__ == "__main__":
    main()
