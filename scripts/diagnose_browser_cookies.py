from __future__ import annotations

import argparse
import json

from common import ensure_layout, load_settings, resolve_agent_home
from fetch_fund_news import browser_cookie_candidates, browser_candidate_metadata, resolve_preferred_profile_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose browser cookie candidates for sentiment providers.")
    parser.add_argument("--agent-home", help="Override FUND_AGENT_HOME.")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    settings = load_settings(agent_home)
    payload = {"platforms": {}}
    for platform in ("xueqiu", "douyin"):
        preferred = resolve_preferred_profile_dir(settings, platform)
        payload["platforms"][platform] = {
            "preferred": {
                "browser": preferred[0],
                "profile_dir": str(preferred[1]),
            }
            if preferred
            else {},
            "candidates": [browser_candidate_metadata(browser_name, cookies_path) for browser_name, _local_state, cookies_path in browser_cookie_candidates(settings, platform)],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
