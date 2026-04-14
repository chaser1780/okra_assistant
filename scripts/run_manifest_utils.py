from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from common import dump_json, run_manifest_dir, timestamp_now


def new_run_manifest(agent_home: Path, pipeline_name: str, mode: str, report_date: str) -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "pipeline_name": pipeline_name,
        "mode": mode,
        "report_date": report_date,
        "started_at": timestamp_now(),
        "finished_at": None,
        "status": "running",
        "current_step": "",
        "running_steps": [],
        "step_timings": [],
        "errors": [],
    }


def begin_step(manifest: dict, step_name: str, display_name: str | None = None) -> dict:
    entry = {
        "step_name": step_name,
        "display_name": display_name or step_name,
        "started_at": timestamp_now(),
        "finished_at": None,
        "seconds": None,
        "status": "running",
    }
    manifest.setdefault("step_timings", []).append(entry)
    manifest["current_step"] = entry["display_name"]
    running = manifest.setdefault("running_steps", [])
    if entry["display_name"] not in running:
        running.append(entry["display_name"])
    return entry


def add_step_timing(manifest: dict, step_name: str, seconds: float, status: str = "ok") -> None:
    finish_step(manifest, step_name, seconds, status=status)


def finish_step(
    manifest: dict,
    step_name: str,
    seconds: float,
    *,
    status: str = "ok",
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    target = None
    for item in reversed(manifest.setdefault("step_timings", [])):
        if item.get("step_name") == step_name and item.get("status") == "running":
            target = item
            break
    if target is None:
        target = {
            "step_name": step_name,
            "display_name": step_name,
            "started_at": timestamp_now(),
        }
        manifest.setdefault("step_timings", []).append(target)
    target["finished_at"] = timestamp_now()
    target["seconds"] = round(float(seconds), 3)
    target["status"] = status
    if error:
        target["error"] = error
    if extra:
        target.update(extra)
    running = manifest.setdefault("running_steps", [])
    display_name = target.get("display_name") or step_name
    manifest["running_steps"] = [item for item in running if item != display_name]
    manifest["current_step"] = manifest["running_steps"][-1] if manifest["running_steps"] else ""
    if error:
        manifest.setdefault("errors", []).append({"step_name": step_name, "error": error})


def finalize_manifest(manifest: dict, success: bool, errors: list[dict] | None = None, extra: dict | None = None) -> dict:
    manifest["finished_at"] = timestamp_now()
    manifest["status"] = "ok" if success else "failed"
    manifest["current_step"] = ""
    manifest["running_steps"] = []
    if errors:
        manifest["errors"] = errors
    if extra:
        manifest.update(extra)
    return manifest


def manifest_path(agent_home: Path, manifest: dict) -> Path:
    report_date = manifest.get("report_date", datetime.now().date().isoformat())
    pipeline_name = manifest.get("pipeline_name", "pipeline")
    run_id = manifest.get("run_id", "unknown")
    return run_manifest_dir(agent_home) / report_date / f"{pipeline_name}_{run_id}.json"


def write_manifest(agent_home: Path, manifest: dict) -> Path:
    path = manifest_path(agent_home, manifest)
    return dump_json(path, manifest)
