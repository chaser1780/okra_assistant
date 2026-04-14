from __future__ import annotations

import json
from pathlib import Path


def default_ui_state() -> dict:
    return {
        "last_tab": "dash",
        "view_mode": "analyst",
        "pane_positions": {},
        "filters": {},
        "selections": {},
        "sort": {"realtime": "pnl_desc"},
    }


def _merge(base, incoming):
    if not isinstance(base, dict) or not isinstance(incoming, dict):
        return incoming
    merged = dict(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ui_state_path(home: Path) -> Path:
    return home / "config" / "ui_state.json"


def load_ui_state(home: Path) -> dict:
    path = ui_state_path(home)
    if not path.exists():
        return default_ui_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_ui_state()
    return _merge(default_ui_state(), payload if isinstance(payload, dict) else {})


def save_ui_state(home: Path, state: dict) -> Path:
    path = ui_state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_merge(default_ui_state(), state), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
