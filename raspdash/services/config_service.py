from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from raspdash.config import CONFIG_PATH, DATA_DIR, load_config

LAYOUTS_PATH = DATA_DIR / "layouts.json"


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_dashboard_config() -> dict[str, Any]:
    config = load_config()
    dashboard = config.setdefault("dashboard", {})
    dashboard.setdefault("widgets", {})
    dashboard.setdefault("widget_order", list(dashboard["widgets"].keys()))
    dashboard.setdefault("editor_snap", True)
    dashboard.setdefault("editor_grid_size", 5)
    return config


def save_dashboard_config(config: dict[str, Any]) -> None:
    atomic_write_json(CONFIG_PATH, config)


def load_layouts() -> dict[str, Any]:
    if not LAYOUTS_PATH.exists():
        return {"layouts": {}}
    with LAYOUTS_PATH.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        return {"layouts": {}}
    loaded.setdefault("layouts", {})
    return loaded


def save_layouts(layouts: dict[str, Any]) -> None:
    atomic_write_json(LAYOUTS_PATH, layouts)
