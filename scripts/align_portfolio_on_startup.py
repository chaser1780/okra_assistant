from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from common import (
    dump_json,
    ensure_layout,
    load_json,
    portfolio_state_current_path,
    resolve_agent_home,
    resolve_date,
    timestamp_now,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def _safe_date(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 10 and text.count("-") == 2:
        return text
    return ""


def _portfolio_as_of_date(agent_home: Path) -> str:
    current_path = portfolio_state_current_path(agent_home)
    if current_path.exists():
        payload = load_json(current_path)
        if isinstance(payload, dict):
            return _safe_date(payload.get("as_of_date") or payload.get("last_valuation_run_date"))
    legacy_path = agent_home / "config" / "portfolio.json"
    if legacy_path.exists():
        payload = load_json(legacy_path)
        if isinstance(payload, dict):
            return _safe_date(payload.get("as_of_date") or payload.get("last_valuation_run_date"))
    return ""


def _run_script(agent_home: Path, script_name: str, report_date: str) -> dict:
    command = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        str(SCRIPT_DIR / script_name),
        "--agent-home",
        str(agent_home),
        "--date",
        report_date,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    return {
        "script": script_name,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def align_portfolio(agent_home: Path, report_date: str, *, force: bool = False) -> dict:
    ensure_layout(agent_home)
    before_date = _portfolio_as_of_date(agent_home)
    if before_date and before_date >= report_date and not force:
        summary = {
            "status": "skipped",
            "reason": "portfolio_already_current",
            "report_date": report_date,
            "before_as_of_date": before_date,
            "after_as_of_date": before_date,
            "generated_at": timestamp_now(),
            "steps": [],
        }
        dump_json(agent_home / "db" / "portfolio_valuation" / f"{report_date}_startup_alignment.json", summary)
        return summary

    steps = []
    for script_name in ("fetch_fund_quotes.py", "revalue_portfolio_official_nav.py"):
        result = _run_script(agent_home, script_name, report_date)
        steps.append(result)
        if int(result.get("returncode", 1)) != 0:
            summary = {
                "status": "failed",
                "reason": f"{script_name}_failed",
                "report_date": report_date,
                "before_as_of_date": before_date,
                "after_as_of_date": _portfolio_as_of_date(agent_home),
                "generated_at": timestamp_now(),
                "steps": steps,
            }
            dump_json(agent_home / "db" / "portfolio_valuation" / f"{report_date}_startup_alignment.json", summary)
            raise RuntimeError(result.get("stderr") or result.get("stdout") or f"{script_name} failed")

    after_date = _portfolio_as_of_date(agent_home)
    summary = {
        "status": "ok",
        "reason": "",
        "report_date": report_date,
        "before_as_of_date": before_date,
        "after_as_of_date": after_date,
        "generated_at": timestamp_now(),
        "steps": steps,
    }
    dump_json(agent_home / "db" / "portfolio_valuation" / f"{report_date}_startup_alignment.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Align runtime portfolio state to the latest official NAV target on startup.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    report_date = resolve_date(args.date)
    print(json.dumps(align_portfolio(agent_home, report_date, force=args.force), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
