from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from common import ensure_layout, resolve_agent_home, resolve_date
from execution_sync import parse_alipay_screenshot_upload


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Alipay position screenshots and create a safe preview placeholder.")
    parser.add_argument("--agent-home")
    parser.add_argument("--date")
    parser.add_argument("--images", nargs="+", required=True)
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    ensure_layout(agent_home)
    files = []
    for path_text in args.images:
        path = Path(path_text)
        files.append({"name": path.name, "data": base64.b64encode(path.read_bytes()).decode("ascii")})
    result = parse_alipay_screenshot_upload(agent_home, {"snapshot_date": resolve_date(args.date), "files": files})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
