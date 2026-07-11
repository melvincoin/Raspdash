from __future__ import annotations

from flask import Blueprint, jsonify, request

from raspdash.middleware.error_handler import ApiError
from raspdash.services.config_service import load_dashboard_config, load_layouts, save_dashboard_config, save_layouts

layout_bp = Blueprint("layouts", __name__, url_prefix="/api/layouts")


def current_positions(config: dict) -> dict:
    widgets = config["dashboard"].setdefault("widgets", {})
    return {
        widget_id: {
            "x": widget.get("x", 0),
            "y": widget.get("y", 0),
            "width": widget.get("width", 28),
        }
        for widget_id, widget in widgets.items()
    }


@layout_bp.get("")
def list_layouts():
    layouts = load_layouts()
    return jsonify({"ok": True, "layouts": [{"name": name, **preset} for name, preset in layouts["layouts"].items()]})


@layout_bp.post("")
def save_layout():
    payload = request.get_json(force=True)
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ApiError("name is verplicht")
    config = load_dashboard_config()
    layouts = load_layouts()
    layouts["layouts"][name] = {"positions": current_positions(config)}
    save_layouts(layouts)
    return jsonify({"ok": True, "name": name, "layout": layouts["layouts"][name]}), 201


@layout_bp.put("/<name>/apply")
def apply_layout(name: str):
    layouts = load_layouts()
    if name not in layouts["layouts"]:
        raise ApiError("Layout preset niet gevonden", 404)
    config = load_dashboard_config()
    widgets = config["dashboard"].setdefault("widgets", {})
    for widget_id, position in layouts["layouts"][name].get("positions", {}).items():
        if widget_id not in widgets:
            continue
        widgets[widget_id]["x"] = position.get("x", widgets[widget_id].get("x", 0))
        widgets[widget_id]["y"] = position.get("y", widgets[widget_id].get("y", 0))
        widgets[widget_id]["width"] = position.get("width", widgets[widget_id].get("width", 28))
    save_dashboard_config(config)
    return jsonify({"ok": True, "name": name, "config": config})


@layout_bp.delete("/<name>")
def delete_layout(name: str):
    layouts = load_layouts()
    if name not in layouts["layouts"]:
        raise ApiError("Layout preset niet gevonden", 404)
    del layouts["layouts"][name]
    save_layouts(layouts)
    return jsonify({"ok": True, "deleted": name})
