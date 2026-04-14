from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import agent_snapshot_root, ensure_layout, llm_context_path, llm_advice_path, portfolio_report_path, resolve_agent_home, resolve_date, validated_advice_path


def next_snapshot_dir(agent_home: Path, report_date: str) -> Path:
    base = agent_snapshot_root(agent_home, report_date)
    base.mkdir(parents=True, exist_ok=True)
    versions = sorted(path for path in base.iterdir() if path.is_dir() and path.name.startswith("v"))
    target = base / f"v{len(versions) + 1:03d}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_copy(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot key run artifacts.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD format.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    report_date = resolve_date(args.date)
    snapshot_dir = next_snapshot_dir(agent_home, report_date)

    safe_copy(llm_context_path(agent_home, report_date), snapshot_dir / "llm_context.json")
    safe_copy(llm_advice_path(agent_home, report_date), snapshot_dir / "llm_advice.json")
    safe_copy(validated_advice_path(agent_home, report_date), snapshot_dir / "validated_advice.json")
    safe_copy(portfolio_report_path(agent_home, report_date), snapshot_dir / "final_report.md")
    print(snapshot_dir)


if __name__ == "__main__":
    main()