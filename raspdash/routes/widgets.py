from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, jsonify, request

from raspdash.middleware.error_handler import ApiError
from raspdash.middleware.validate_widget import normalize_widget, serialize_widget
from raspdash.services.config_service import load_dashboard_config, save_dashboard_config
from raspdash.services.layout_service import (
    auto_layout,
    find_overlaps,
    free_space,
    grid_value,
    nearest_free_position,
    overlap_warnings,
    snap_to_grid,
    sort_order,
)

widget_bp = Blueprint("widgets", __name__, url_prefix="/api/widgets")


def dashboard_parts():
    config = load_dashboard_config()
    dashboard = config["dashboard"]
    widgets = dashboard.setdefault("widgets", {})
    order = dashboard.setdefault("widget_order", list(widgets.keys()))
    return config, dashboard, widgets, order


def widget_response(widget_id: str, widgets: dict, status_code: int = 200):
    payload = {
        "ok": True,
        "widget": serialize_widget(widget_id, widgets[widget_id]),
        "warnings": overlap_warnings(widgets, widget_id),
    }
    return jsonify(payload), status_code


@widget_bp.get("")
def list_widgets():
    _config, _dashboard, widgets, order = dashboard_parts()
    return jsonify(
        {
            "ok": True,
            "widgets": [serialize_widget(widget_id, widgets[widget_id]) for widget_id in order if widget_id in widgets],
            "widget_order": [widget_id for widget_id in order if widget_id in widgets],
        }
    )


@widget_bp.post("")
def create_widget():
    config, dashboard, widgets, order = dashboard_parts()
    payload = request.get_json(force=True)
    widget_id = str(uuid4())
    widget = normalize_widget(payload)
    if dashboard.get("editor_snap"):
        widget = snap_to_grid(widget, dashboard.get("editor_grid_size", 5))
    widgets[widget_id] = widget
    order.append(widget_id)
    save_dashboard_config(config)
    return widget_response(widget_id, widgets, 201)


@widget_bp.put("/<widget_id>")
def replace_widget(widget_id: str):
    config, dashboard, widgets, order = dashboard_parts()
    if widget_id not in widgets:
        raise ApiError("Widget niet gevonden", 404)
    widget = normalize_widget(request.get_json(force=True))
    if dashboard.get("editor_snap"):
        widget = snap_to_grid(widget, dashboard.get("editor_grid_size", 5))
    widgets[widget_id] = widget
    if widget_id not in order:
        order.append(widget_id)
    save_dashboard_config(config)
    return widget_response(widget_id, widgets)


@widget_bp.patch("/<widget_id>")
def patch_widget(widget_id: str):
    config, dashboard, widgets, _order = dashboard_parts()
    if widget_id not in widgets:
        raise ApiError("Widget niet gevonden", 404)
    payload = request.get_json(force=True)
    widget = normalize_widget(payload, widgets[widget_id], partial=True)
    if dashboard.get("editor_snap") and any(key in payload for key in ("x", "y")):
        widget = snap_to_grid(widget, dashboard.get("editor_grid_size", 5))
    widgets[widget_id] = widget
    save_dashboard_config(config)
    return widget_response(widget_id, widgets)


@widget_bp.delete("/<widget_id>")
def delete_widget(widget_id: str):
    config, _dashboard, widgets, order = dashboard_parts()
    if widget_id not in widgets:
        raise ApiError("Widget niet gevonden", 404)
    del widgets[widget_id]
    order[:] = [item for item in order if item != widget_id]
    save_dashboard_config(config)
    return jsonify({"ok": True, "deleted": widget_id})


@widget_bp.post("/auto-layout")
def run_auto_layout():
    config, _dashboard, widgets, order = dashboard_parts()
    payload = request.get_json(force=True)
    strategy = payload.get("strategy", "grid")
    if strategy not in {"grid", "row", "column"}:
        raise ApiError('strategy moet "grid", "row" of "column" zijn')
    config["dashboard"]["widgets"] = auto_layout(
        widgets,
        order,
        strategy=strategy,
        padding=grid_value(payload.get("padding"), 2),
        start_x=grid_value(payload.get("startX"), 0),
        start_y=grid_value(payload.get("startY"), 0),
    )
    save_dashboard_config(config)
    return jsonify({"ok": True, "widgets": config["dashboard"]["widgets"], "warnings": find_overlaps(config["dashboard"]["widgets"])})


@widget_bp.post("/<widget_id>/snap")
def snap_widget(widget_id: str):
    config, dashboard, widgets, _order = dashboard_parts()
    if widget_id not in widgets:
        raise ApiError("Widget niet gevonden", 404)
    widgets[widget_id] = nearest_free_position(widget_id, widgets, grid_size=dashboard.get("editor_grid_size", 5))
    save_dashboard_config(config)
    return widget_response(widget_id, widgets)


@widget_bp.post("/<widget_id>/duplicate")
def duplicate_widget(widget_id: str):
    config, dashboard, widgets, order = dashboard_parts()
    if widget_id not in widgets:
        raise ApiError("Widget niet gevonden", 404)
    grid_size = max(1, grid_value(dashboard.get("editor_grid_size"), 5))
    new_id = str(uuid4())
    duplicate = dict(widgets[widget_id])
    duplicate["x"] = grid_value(duplicate.get("x"), 0) + grid_size
    duplicate["y"] = grid_value(duplicate.get("y"), 0) + grid_size
    duplicate = nearest_free_position(new_id, {**widgets, new_id: duplicate}, grid_size=grid_size)
    widgets[new_id] = duplicate
    order.append(new_id)
    save_dashboard_config(config)
    return widget_response(new_id, widgets, 201)


@widget_bp.get("/overlaps")
def overlaps():
    _config, _dashboard, widgets, _order = dashboard_parts()
    return jsonify({"ok": True, "overlaps": find_overlaps(widgets)})


@widget_bp.get("/free-space")
def free_space_report():
    _config, _dashboard, widgets, _order = dashboard_parts()
    return jsonify({"ok": True, **free_space(widgets)})


@widget_bp.post("/sort")
def sort_widgets():
    config, _dashboard, widgets, _order = dashboard_parts()
    payload = request.get_json(force=True)
    by = payload.get("by")
    order = payload.get("order", "asc")
    if by not in {"label", "parameter", "position_x", "position_y", "displayType"}:
        raise ApiError("Ongeldig sorteerveld")
    if order not in {"asc", "desc"}:
        raise ApiError('order moet "asc" of "desc" zijn')
    config["dashboard"]["widget_order"] = sort_order(widgets, by, order)
    save_dashboard_config(config)
    return jsonify({"ok": True, "widget_order": config["dashboard"]["widget_order"]})


@widget_bp.get("/grid")
def get_grid():
    _config, dashboard, _widgets, _order = dashboard_parts()
    return jsonify(
        {
            "ok": True,
            "snapToGrid": bool(dashboard.get("editor_snap", True)),
            "gridSize": grid_value(dashboard.get("editor_grid_size"), 5),
        }
    )


@widget_bp.put("/grid")
def put_grid():
    config, dashboard, _widgets, _order = dashboard_parts()
    payload = request.get_json(force=True)
    dashboard["editor_snap"] = bool(payload.get("snapToGrid", dashboard.get("editor_snap", True)))
    dashboard["editor_grid_size"] = max(1, grid_value(payload.get("gridSize"), dashboard.get("editor_grid_size", 5)))
    save_dashboard_config(config)
    return jsonify({"ok": True, "snapToGrid": dashboard["editor_snap"], "gridSize": dashboard["editor_grid_size"]})
