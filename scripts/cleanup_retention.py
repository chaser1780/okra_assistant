from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from common import resolve_agent_home, timestamp_now, today_shanghai


DEFAULT_PROTECTED_PATHS = [
    "db/long_memory",
    "db/execution_sync",
    "db/portfolio_state",
    "db/validated_advice",
    "db/decisions",
    "db/decision_ledger",
    "db/decision_latest",
    "config",
    "docs",
    "references",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "archive_root": "backups/retention",
    "dry_run_default": True,
    "protected_paths": DEFAULT_PROTECTED_PATHS,
    "rules": [],
}


@dataclass(frozen=True)
class RetentionItem:
    rule: str
    action: str
    path: str
    archive_path: str | None
    size_bytes: int
    reason: str
    date: str | None = None
    modified_at: str | None = None


@dataclass(frozen=True)
class RetentionPlan:
    agent_home: str
    as_of: str
    dry_run: bool
    items: list[RetentionItem]
    skipped: list[dict[str, Any]]
    protected_violations: list[dict[str, Any]]

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_home": self.agent_home,
            "as_of": self.as_of,
            "dry_run": self.dry_run,
            "total_items": len(self.items),
            "total_size_bytes": self.total_size_bytes,
            "actions": [item.__dict__ for item in self.items],
            "skipped": self.skipped,
            "protected_violations": self.protected_violations,
        }


def summarize_by_rule(plan: RetentionPlan) -> dict[str, dict[str, int]]:
    rule_totals: dict[str, dict[str, int]] = {}
    for item in plan.items:
        bucket = rule_totals.setdefault(item.rule, {"items": 0, "bytes": 0})
        bucket["items"] += 1
        bucket["bytes"] += item.size_bytes
    return rule_totals


def retention_plan_from_dict(payload: dict[str, Any]) -> RetentionPlan:
    return RetentionPlan(
        agent_home=str(payload.get("agent_home", "")),
        as_of=str(payload.get("as_of", "")),
        dry_run=bool(payload.get("dry_run", True)),
        items=[
            RetentionItem(
                rule=str(item.get("rule", "")),
                action=str(item.get("action", "")),
                path=str(item.get("path", "")),
                archive_path=str(item.get("archive_path")) if item.get("archive_path") else None,
                size_bytes=int(item.get("size_bytes") or 0),
                reason=str(item.get("reason", "")),
                date=str(item.get("date")) if item.get("date") else None,
                modified_at=str(item.get("modified_at")) if item.get("modified_at") else None,
            )
            for item in payload.get("actions", [])
        ],
        skipped=list(payload.get("skipped", [])),
        protected_violations=list(payload.get("protected_violations", [])),
    )


def render_markdown_report(plan: RetentionPlan, config: dict[str, Any], *, limit: int = 80, plan_path: str | None = None) -> str:
    mode = "dry-run" if plan.dry_run else "apply"
    protected_paths = [str(item) for item in config.get("protected_paths", DEFAULT_PROTECTED_PATHS)]
    lines = [
        "# OKRA Retention Review",
        "",
        f"- Mode: `{mode}`",
        f"- As of: `{plan.as_of}`",
        f"- Agent home: `{plan.agent_home}`",
        f"- Planned items: `{len(plan.items)}`",
        f"- Planned size: `{_format_bytes(plan.total_size_bytes)}`",
        f"- Protected violations: `{len(plan.protected_violations)}`",
        "",
        "## Rule Summary",
        "",
        "| Rule | Items | Size |",
        "| --- | ---: | ---: |",
    ]
    rule_totals = summarize_by_rule(plan)
    if rule_totals:
        for rule_name, totals in sorted(rule_totals.items()):
            lines.append(f"| `{rule_name}` | {totals['items']} | {_format_bytes(totals['bytes'])} |")
    else:
        lines.append("| none | 0 | 0 B |")

    lines.extend(
        [
            "",
            "## Protected Paths",
            "",
        ]
    )
    for protected in protected_paths:
        lines.append(f"- `{protected}`")
    if plan.protected_violations:
        lines.extend(["", "## Protected Violations", ""])
        for violation in plan.protected_violations:
            lines.append(f"- `{violation.get('path', '')}` via `{violation.get('rule', '')}`: {violation.get('reason', '')}")

    lines.extend(
        [
            "",
            "## Planned Actions",
            "",
            "| Action | Rule | Path | Size | Reason |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for item in plan.items[: max(0, limit)]:
        reason = str(item.reason).replace("|", "\\|")
        lines.append(f"| `{item.action}` | `{item.rule}` | `{item.path}` | {_format_bytes(item.size_bytes)} | {reason} |")
    if len(plan.items) > limit:
        lines.append(f"| ... | ... | {len(plan.items) - limit} more items hidden; rerun with `--verbose` or `--json`. |  |  |")

    if plan.skipped:
        lines.extend(["", "## Skipped", "", "| Rule | Path | Reason |", "| --- | --- | --- |"])
        skipped_summary = plan.skipped[: max(0, limit)]
        for item in skipped_summary:
            lines.append(f"| `{item.get('rule', '')}` | `{item.get('path', '')}` | {item.get('reason', '')} |")
        if len(plan.skipped) > limit:
            lines.append(f"| ... | {len(plan.skipped) - limit} more skipped items hidden. |  |")

    lines.extend(
        [
            "",
            "## Human Checklist",
            "",
            "- Confirm protected violations are `0`.",
            "- Confirm `raw/news` actions are archive-only and have downstream `db/llm_context` coverage.",
            "- Confirm delete actions are limited to rebuildable `logs`, `cache`, `temp`, or old backup snapshots.",
            "- Prefer applying the reviewed JSON plan instead of rebuilding a fresh plan at apply time.",
            "",
            "Suggested review command:",
            "",
            "```powershell",
            "python -B -X utf8 scripts\\cleanup_retention.py --dry-run --assert-protected --report",
            "```",
        ]
    )
    if plan_path:
        lines.extend(
            [
                "",
                "Reviewed apply command:",
                "",
                "```powershell",
                f"python -B -X utf8 scripts\\cleanup_retention.py --apply-plan \"{plan_path}\" --assert-protected",
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(
    agent_home: Path,
    plan: RetentionPlan,
    config: dict[str, Any],
    report_path: str | Path,
    *,
    limit: int = 80,
    plan_path: str | None = None,
) -> Path:
    root = agent_home.resolve()
    path = _resolve_inside_root(root, report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(plan, config, limit=limit, plan_path=plan_path), encoding="utf-8")
    return path


def write_plan_snapshot(agent_home: Path, plan: RetentionPlan, plan_path: str | Path) -> Path:
    root = agent_home.resolve()
    path = _resolve_inside_root(root, plan_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**plan.to_dict(), "generated_at": timestamp_now()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_plan_snapshot(agent_home: Path, plan_path: str | Path) -> RetentionPlan:
    root = agent_home.resolve()
    path = _resolve_inside_root(root, plan_path)
    plan = retention_plan_from_dict(json.loads(path.read_text(encoding="utf-8")))
    if Path(plan.agent_home).resolve() != root:
        raise ValueError(f"Plan agent_home does not match current project: {plan.agent_home}")
    return RetentionPlan(
        agent_home=plan.agent_home,
        as_of=plan.as_of,
        dry_run=False,
        items=plan.items,
        skipped=plan.skipped,
        protected_violations=plan.protected_violations,
    )


def load_retention_config(agent_home: Path) -> dict[str, Any]:
    path = agent_home / "config" / "retention.toml"
    config = dict(DEFAULT_CONFIG)
    if not path.exists():
        return config
    payload = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    retention = payload.get("retention", {})
    config.update({key: value for key, value in retention.items() if key != "rules"})
    config["rules"] = retention.get("rules", [])
    if not config.get("protected_paths"):
        config["protected_paths"] = DEFAULT_PROTECTED_PATHS
    return config


def build_retention_plan(
    agent_home: Path,
    config: dict[str, Any] | None = None,
    *,
    as_of: date | None = None,
    dry_run: bool = True,
) -> RetentionPlan:
    root = agent_home.resolve()
    config = config or load_retention_config(root)
    as_of_date = as_of or _parse_date(today_shanghai()) or date.today()
    archive_root = _resolve_inside_root(root, str(config.get("archive_root") or "backups/retention"))
    protected_paths = [_resolve_inside_root(root, item) for item in config.get("protected_paths", DEFAULT_PROTECTED_PATHS)]
    items: list[RetentionItem] = []
    skipped: list[dict[str, Any]] = []
    protected_violations: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for raw_rule in config.get("rules", []):
        rule = dict(raw_rule)
        if not rule.get("enabled", True):
            continue
        for candidate in _iter_rule_candidates(root, rule, as_of_date):
            path = candidate["path"]
            resolved_path = path.resolve()
            if resolved_path in seen:
                skipped.append(_skip(rule, path, "already_planned"))
                continue
            if _is_under_any(resolved_path, protected_paths):
                protected_violations.append(
                    {
                        "rule": rule.get("name", ""),
                        "path": _relative(root, path),
                        "reason": "protected_path",
                    }
                )
                continue
            if not _requirement_exists(root, rule, candidate.get("date")):
                skipped.append(_skip(rule, path, "missing_required_downstream_artifact"))
                continue
            action = str(rule.get("action") or "archive")
            if action not in {"archive", "delete"}:
                skipped.append(_skip(rule, path, f"unsupported_action:{action}"))
                continue
            archive_path = _archive_path(root, archive_root, rule, path) if action == "archive" else None
            item = RetentionItem(
                rule=str(rule.get("name") or ""),
                action=action,
                path=_relative(root, path),
                archive_path=_relative(root, archive_path) if archive_path else None,
                size_bytes=_path_size(path),
                reason=str(candidate.get("reason") or ""),
                date=candidate.get("date"),
                modified_at=_path_modified_at(path),
            )
            items.append(item)
            seen.add(resolved_path)

    return RetentionPlan(
        agent_home=str(root),
        as_of=as_of_date.isoformat(),
        dry_run=dry_run,
        items=items,
        skipped=skipped,
        protected_violations=protected_violations,
    )


def apply_retention_plan(agent_home: Path, plan: RetentionPlan) -> None:
    root = agent_home.resolve()
    if plan.protected_violations:
        raise RuntimeError("Refusing to apply retention plan with protected path violations.")
    for item in plan.items:
        target = _resolve_inside_root(root, item.path)
        if not target.exists():
            continue
        current_size = _path_size(target)
        if current_size != item.size_bytes:
            raise RuntimeError(
                f"Refusing to apply stale retention item: {item.path} size changed from {item.size_bytes} to {current_size}."
            )
        if item.action == "delete":
            _remove_path(target)
        elif item.action == "archive":
            if not item.archive_path:
                raise RuntimeError(f"Missing archive path for {item.path}")
            archive_path = _resolve_inside_root(root, item.archive_path)
            _zip_path(target, archive_path)
            _remove_path(target)


def _iter_rule_candidates(root: Path, rule: dict[str, Any], as_of: date) -> Iterable[dict[str, Any]]:
    selector = str(rule.get("selector") or "")
    base = _resolve_inside_root(root, str(rule.get("path") or "."))
    if not base.exists():
        return []
    if selector == "dated_files":
        return list(_dated_files(root, base, rule, as_of))
    if selector == "dated_dirs":
        return list(_dated_dirs(root, base, rule, as_of))
    if selector == "mtime_files":
        return list(_mtime_files(root, base, rule, as_of))
    if selector == "backup_snapshots":
        return list(_backup_snapshots(root, base, rule))
    return []


def _dated_files(root: Path, base: Path, rule: dict[str, Any], as_of: date) -> Iterable[dict[str, Any]]:
    pattern = str(rule.get("pattern") or "*")
    retention_days = int(rule.get("retention_days") or 0)
    for path in sorted(base.glob(pattern)):
        if not path.is_file():
            continue
        item_date = _parse_date_from_text(path.stem)
        if item_date is None:
            continue
        age_days = (as_of - item_date).days
        if age_days > retention_days:
            yield {
                "path": path,
                "date": item_date.isoformat(),
                "reason": f"dated file is {age_days} days old; retention is {retention_days} days",
            }


def _dated_dirs(root: Path, base: Path, rule: dict[str, Any], as_of: date) -> Iterable[dict[str, Any]]:
    retention_days = int(rule.get("retention_days") or 0)
    for path in sorted(item for item in base.iterdir() if item.is_dir()):
        item_date = _parse_date_from_text(path.name)
        if item_date is None:
            continue
        age_days = (as_of - item_date).days
        if age_days > retention_days:
            yield {
                "path": path,
                "date": item_date.isoformat(),
                "reason": f"dated directory is {age_days} days old; retention is {retention_days} days",
            }


def _mtime_files(root: Path, base: Path, rule: dict[str, Any], as_of: date) -> Iterable[dict[str, Any]]:
    pattern = str(rule.get("pattern") or "*")
    retention_days = int(rule.get("retention_days") or 0)
    include_keywords = [str(item).lower() for item in rule.get("include_keywords", [])]
    exclude_keywords = [str(item).lower() for item in rule.get("exclude_keywords", [])]
    preserved = _preserved_latest_files(base, rule)
    for path in sorted(item for item in base.rglob(pattern) if item.is_file()):
        relative_text = _relative(root, path).lower()
        if path.resolve() in preserved:
            continue
        if include_keywords and not any(keyword in relative_text for keyword in include_keywords):
            continue
        if exclude_keywords and any(keyword in relative_text for keyword in exclude_keywords):
            continue
        mtime_date = datetime.fromtimestamp(path.stat().st_mtime).date()
        age_days = (as_of - mtime_date).days
        if age_days > retention_days:
            yield {
                "path": path,
                "date": mtime_date.isoformat(),
                "reason": f"mtime is {age_days} days old; retention is {retention_days} days",
            }


def _backup_snapshots(root: Path, base: Path, rule: dict[str, Any]) -> Iterable[dict[str, Any]]:
    pattern = str(rule.get("pattern") or "*.zip")
    exclude_roots = [_resolve_inside_root(root, item) for item in rule.get("exclude_paths", [])]
    files = [
        item
        for item in base.rglob(pattern)
        if item.is_file() and not _is_under_any(item.resolve(), exclude_roots)
    ]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    keep: set[Path] = {item.resolve() for item in files[: int(rule.get("keep_latest_count") or 0)]}
    monthly_limit = int(rule.get("keep_monthly_count") or 0)
    monthly_kept = 0
    monthly_seen: set[str] = set()
    for path in files:
        month = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m")
        if month in monthly_seen:
            continue
        monthly_seen.add(month)
        if monthly_kept < monthly_limit:
            keep.add(path.resolve())
            monthly_kept += 1
    for path in files:
        if path.resolve() in keep:
            continue
        yield {
            "path": path,
            "date": datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(),
            "reason": "backup exceeds latest/monthly retention limits",
        }


def _preserved_latest_files(base: Path, rule: dict[str, Any]) -> set[Path]:
    count = int(rule.get("preserve_latest_count") or 0)
    patterns = [str(item) for item in rule.get("preserve_latest_patterns", [])]
    if count <= 0 or not patterns:
        return set()
    matches: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        relative = str(path.relative_to(base)).replace("\\", "/").lower()
        if any(fnmatch.fnmatch(name, pattern.lower()) or fnmatch.fnmatch(relative, pattern.lower()) for pattern in patterns):
            matches.append(path)
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return {item.resolve() for item in matches[:count]}


def _requirement_exists(root: Path, rule: dict[str, Any], date_text: str | None) -> bool:
    requirement = rule.get("require_existing")
    if not requirement:
        return True
    if not date_text:
        return False
    required_path = _resolve_inside_root(root, str(requirement).format(date=date_text))
    return required_path.exists()


def _archive_path(root: Path, archive_root: Path, rule: dict[str, Any], path: Path) -> Path:
    relative = path.resolve().relative_to(root)
    safe_name = "__".join(relative.parts)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return archive_root / str(rule.get("name") or "retention") / f"{safe_name}.{stamp}.zip"


def _zip_path(path: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if path.is_file():
            archive.write(path, arcname=path.name)
            return
        for item in path.rglob("*"):
            if item.is_file():
                archive.write(item, arcname=str(item.relative_to(path.parent)))


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _resolve_inside_root(root: Path, relative_or_absolute: str | Path) -> Path:
    candidate = Path(relative_or_absolute)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _is_under(resolved, root):
        raise ValueError(f"Path escapes agent home: {relative_or_absolute}")
    return resolved


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_under_any(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or _is_under(path, root) for root in roots)


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _path_modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _relative(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _skip(rule: dict[str, Any], path: Path, reason: str) -> dict[str, Any]:
    return {"rule": rule.get("name", ""), "path": str(path), "reason": reason}


def _parse_date_from_text(value: str) -> date | None:
    for index in range(max(1, len(value) - 9)):
        parsed = _parse_date(value[index : index + 10])
        if parsed:
            return parsed
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _print_human(plan: RetentionPlan, *, verbose: bool = False, limit: int = 80) -> None:
    mode = "dry-run" if plan.dry_run else "apply"
    print(f"Retention plan ({mode}) as_of={plan.as_of}")
    print(f"agent_home={plan.agent_home}")
    print(f"planned_items={len(plan.items)} total_size_bytes={plan.total_size_bytes}")
    rule_totals = summarize_by_rule(plan)
    if rule_totals:
        print("by_rule:")
        for rule_name, totals in sorted(rule_totals.items()):
            print(f"  - {rule_name}: {totals['items']} items, {totals['bytes']} bytes")
    if plan.protected_violations:
        print(f"protected_violations={len(plan.protected_violations)}")
        for violation in plan.protected_violations:
            print(f"  ! {violation['rule']} {violation['path']} ({violation['reason']})")
    visible_items = plan.items if verbose else plan.items[:limit]
    for item in visible_items:
        target = f" -> {item.archive_path}" if item.archive_path else ""
        print(f"  - {item.action:7s} {item.path}{target} [{item.rule}] {item.reason}")
    if not verbose and len(plan.items) > limit:
        print(f"... {len(plan.items) - limit} more planned items hidden; use --verbose or --json to inspect all actions.")
    if plan.skipped:
        print(f"skipped={len(plan.skipped)}")


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply OKRA retention rules for rebuildable runtime data.")
    parser.add_argument("--agent-home", default=None, help="Project root. Defaults to FUND_AGENT_HOME or F:\\okra_assistant.")
    parser.add_argument("--as-of", default=None, help="Date used for age checks, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only. This is the default unless --apply is passed.")
    parser.add_argument("--apply", action="store_true", help="Execute the planned archive/delete operations.")
    parser.add_argument("--apply-plan", default=None, help="Apply a previously reviewed JSON plan snapshot instead of rebuilding a fresh plan.")
    parser.add_argument("--assert-protected", action="store_true", help="Fail if any protected path is selected by rules.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--verbose", action="store_true", help="Print every planned action in human-readable output.")
    parser.add_argument("--limit", type=int, default=80, help="Maximum planned actions to print without --verbose.")
    parser.add_argument(
        "--report",
        nargs="?",
        const="reports/maintenance/retention_latest.md",
        default=None,
        help="Write a Markdown review report. Defaults to reports/maintenance/retention_latest.md.",
    )
    parser.add_argument(
        "--plan-output",
        default=None,
        help="Write a JSON plan snapshot. Defaults next to --report when --report is used.",
    )
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    config = load_retention_config(agent_home)
    if args.apply_plan:
        plan = load_plan_snapshot(agent_home, args.apply_plan)
    else:
        as_of_date = _parse_date(args.as_of) if args.as_of else None
        if args.as_of and as_of_date is None:
            raise SystemExit(f"Invalid --as-of date: {args.as_of}")
        dry_run = not args.apply
        plan = build_retention_plan(agent_home, config, as_of=as_of_date, dry_run=dry_run)
    if args.json:
        print(json.dumps({**plan.to_dict(), "generated_at": timestamp_now()}, ensure_ascii=False, indent=2))
    else:
        _print_human(plan, verbose=args.verbose, limit=max(0, args.limit))
    plan_output = args.plan_output
    if args.report is not None and plan_output is None and not args.apply_plan:
        plan_output = str(Path(args.report).with_suffix(".plan.json"))
    if plan_output:
        written_plan_path = write_plan_snapshot(agent_home, plan, plan_output)
        print(f"plan={written_plan_path}")
    if args.report is not None:
        report_plan_path = plan_output.replace("\\", "/") if isinstance(plan_output, str) else None
        report_path = write_markdown_report(agent_home, plan, config, args.report, limit=max(0, args.limit), plan_path=report_plan_path)
        print(f"report={report_path}")
    if args.assert_protected and plan.protected_violations:
        return 2
    if args.apply or args.apply_plan:
        apply_retention_plan(agent_home, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
