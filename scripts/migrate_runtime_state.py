from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from common import (
    dump_json,
    ensure_layout,
    legacy_review_memory_dir,
    legacy_trade_journal_dir,
    resolve_agent_home,
    legacy_review_memory_path,
    legacy_trade_journal_path,
    actual_trade_dir,
    iter_actual_trade_items,
    timestamp_now,
)
from long_memory_store import migrate_legacy_review_memory, write_domain_mirrors


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_manifest(root: Path) -> list[dict]:
    if not root.exists():
        return []
    items: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": stat.st_size,
                "sha256": _file_sha256(path),
            }
        )
    return items


def _assert_archive_target(src: Path, dst: Path, legacy_root: Path) -> None:
    if not _is_within(dst, legacy_root):
        raise RuntimeError(f"Archive target must stay under {legacy_root}: {dst}")
    if src.resolve() == dst.resolve() or _is_within(dst, src):
        raise RuntimeError(f"Archive target must not be inside source tree: {src} -> {dst}")


def _validate_copied_tree(src: Path, dst: Path, manifest: list[dict]) -> None:
    for item in manifest:
        relative = Path(str(item["path"]))
        source = src / relative
        target = dst / relative
        if not target.exists():
            raise RuntimeError(f"Archive validation failed; missing copied file: {target}")
        if target.stat().st_size != item["size"] or _file_sha256(target) != item["sha256"]:
            raise RuntimeError(f"Archive validation failed; copied file differs: {source} -> {target}")


def _copy_tree(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    count = 0
    for path in src.rglob("*"):
        relative = path.relative_to(src)
        target = dst / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def _archive_tree(src: Path, dst: Path, legacy_root: Path) -> dict:
    if not src.exists():
        return {"file_count": 0, "manifest_path": "", "deleted": False}
    _assert_archive_target(src, dst, legacy_root)
    manifest = _tree_manifest(src)
    count = _copy_tree(src, dst)
    _validate_copied_tree(src, dst, manifest)
    manifest_path = dump_json(
        dst / "archive_manifest.json",
        {
            "generated_at": timestamp_now(),
            "source": str(src),
            "destination": str(dst),
            "file_count": count,
            "files": manifest,
        },
    )
    if src.exists():
        shutil.rmtree(src)
    return {"file_count": count, "manifest_path": str(manifest_path), "deleted": True}


def _dry_trade_summary(agent_home: Path) -> dict:
    dates = {}
    for item in iter_actual_trade_items(agent_home):
        trade_date = str(item.get("trade_date", "") or "")
        dates[trade_date] = dates.get(trade_date, 0) + 1
    return {
        "actual_trade_dates": len(dates),
        "actual_trade_items": sum(dates.values()),
    }


def run_cutover(agent_home: Path, *, dry_run: bool) -> dict:
    ensure_layout(agent_home)
    review_dir = legacy_review_memory_path(agent_home).parent
    trade_dir = legacy_trade_journal_path(agent_home, "1970-01-01").parent
    legacy_review_dir = legacy_review_memory_dir(agent_home)
    legacy_trade_dir = legacy_trade_journal_dir(agent_home)
    report = {
        "generated_at": timestamp_now(),
        "dry_run": dry_run,
        "review_memory_exists": review_dir.exists(),
        "trade_journal_exists": trade_dir.exists(),
        "actual_trade_summary": _dry_trade_summary(agent_home),
        "archived_review_files": 0,
        "archived_trade_files": 0,
        "legacy_review_dir": str(legacy_review_dir),
        "legacy_trade_dir": str(legacy_trade_dir),
        "migrated_review_memory": {},
        "archive_manifests": {},
        "deleted_legacy_source_dirs": [],
    }
    if dry_run:
        if review_dir.exists():
            report["archived_review_files"] = len([path for path in review_dir.rglob("*") if path.is_file()])
        if trade_dir.exists():
            report["archived_trade_files"] = len([path for path in trade_dir.rglob("*") if path.is_file()])
        return report

    report["migrated_review_memory"] = migrate_legacy_review_memory(agent_home)
    write_domain_mirrors(agent_home)
    if review_dir.exists():
        archived = _archive_tree(review_dir, legacy_review_dir, legacy_root=agent_home / "db" / "legacy")
        report["archived_review_files"] = archived["file_count"]
        report["archive_manifests"]["review_memory"] = archived["manifest_path"]
        if archived["deleted"]:
            report["deleted_legacy_source_dirs"].append(str(review_dir))
    if trade_dir.exists():
        archived = _archive_tree(trade_dir, legacy_trade_dir, legacy_root=agent_home / "db" / "legacy")
        report["archived_trade_files"] = archived["file_count"]
        report["archive_manifests"]["trade_journal"] = archived["manifest_path"]
        if archived["deleted"]:
            report["deleted_legacy_source_dirs"].append(str(trade_dir))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut over runtime state to long_memory/execution_sync and archive legacy paths.")
    parser.add_argument("--agent-home")
    parser.add_argument("--cutover", action="store_true")
    parser.add_argument("--confirm-delete-legacy", action="store_true", help="Required with --cutover before old runtime directories are deleted.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    agent_home = resolve_agent_home(args.agent_home)
    dry_run = bool(args.dry_run or not args.cutover or not args.confirm_delete_legacy)
    payload = run_cutover(agent_home, dry_run=dry_run)
    payload["cutover_requested"] = bool(args.cutover)
    payload["delete_confirmed"] = bool(args.confirm_delete_legacy)
    if args.cutover and not args.confirm_delete_legacy:
        payload["safety_notice"] = "dry_run_only: pass --confirm-delete-legacy with --cutover to archive and delete old runtime directories."
    report_path = agent_home / "db" / "legacy" / "cutover_report.json"
    dump_json(report_path, payload)
    print(report_path)


if __name__ == "__main__":
    main()
