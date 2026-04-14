from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import ensure_layout, resolve_agent_home

SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(name: str, agent_home: Path, extra_args: list[str] | None = None) -> None:
    command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT_DIR / name), "--agent-home", str(agent_home)]
    if extra_args:
        command.extend(extra_args)
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync full fund and benchmark history stores.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    parser.add_argument("--fund-only", nargs="*")
    parser.add_argument("--benchmark-only", nargs="*")
    parser.add_argument("--proxy-only", nargs="*")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)

    fund_args = ["--only", *args.fund_only] if args.fund_only else None
    benchmark_args = ["--only", *args.benchmark_only] if args.benchmark_only else None
    proxy_args = ["--only", *args.proxy_only] if args.proxy_only else None
    run_script("fetch_fund_nav_history.py", agent_home, fund_args)
    run_script("fetch_benchmark_history.py", agent_home, benchmark_args)
    run_script("fetch_proxy_history.py", agent_home, proxy_args)


if __name__ == "__main__":
    main()
