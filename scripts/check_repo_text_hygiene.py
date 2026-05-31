from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOBS = [
    "README.md",
    "project.toml",
    "app/**/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
    "scripts/**/*.py",
    "tests/**/*.py",
    "docs/**/*.md",
]

MOJIBAKE_TOKENS = [
    "????",
    "鍩閲",
    "鏃鏀",
    "璇鎴",
    "鏅鐜",
    "缁閫",
    "閸",
    "缂",
    "閺",
]

FORBIDDEN_TOKENS = [
    "F:\\",
    "C:\\",
    "$env:USERPROFILE",
    "$env:APPDATA",
    "$env:LOCALAPPDATA",
    "HKCU\\",
    "setx ",
    "OKRA_USE_SHADOW_ADVICE_ADAPTER",
    "OKRA_SHADOW_ADVICE_PROMOTION_APPROVED",
    ".codex",
    "fund_agent_data",
    'api_key_file = "config/openai_api_key.txt"',
    "windows_wsl_setup_acknowledged",
    "db/review_memory/",
    "db/trade_journal/",
    "record_trade.py",
    "update_review_memory.py",
    "write_user_memory.py",
    "trade_journal = true",
    "review_memory = true",
]


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in DEFAULT_GLOBS:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    unique = sorted(set(files))
    return [
        path
        for path in unique
        if ".git" not in path.parts
        and "node_modules" not in path.parts
        and "dist" not in path.parts
        and path.name != "check_repo_text_hygiene.py"
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check source and active docs for mojibake and forbidden legacy runtime terms.")
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    args = parser.parse_args()

    root = Path(args.root).resolve()
    failures: list[str] = []
    for path in iter_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in MOJIBAKE_TOKENS:
            if token in text:
                failures.append(f"{path}: mojibake token '{token}'")
                break
        for token in FORBIDDEN_TOKENS:
            if token in text:
                failures.append(f"{path}: forbidden token '{token}'")
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("repo text hygiene ok")


if __name__ == "__main__":
    main()
