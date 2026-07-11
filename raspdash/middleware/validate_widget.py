from __future__ import annotations

from typing import Any

from raspdash.config_obd_parameters import OBD_PARAMETERS
from raspdash.middleware.error_handler import ApiError
from raspdash.services.layout_service import grid_value
from raspdash.widget_themes import THEME_BY_ID, THEME_BY_RENDERER

LEGACY_STYLE_MAP = {"gauge": "golf7", "digital": "digitaal"}


def normalize_widget(payload: dict[str, Any], existing: dict[str, Any] | None = None, *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiError("JSON body moet een object zijn")

    widget = dict(existing or {})
    source = payload.get("parameter", payload.get("source", widget.get("source")))
    display_type = payload.get("displayType")
    style = payload.get("style", widget.get("style"))
    if style in LEGACY_STYLE_MAP:
        style = LEGACY_STYLE_MAP[str(style)]

    if display_type is not None:
        theme = THEME_BY_ID.get(str(display_type))
        if theme is None:
            raise ApiError("displayType moet een bekende weergavestijl zijn")
        style = theme["renderer"]

    field_map = {
        "label": "label",
        "color": "color",
        "enabled": "enabled",
        "position": "position",
    }
    for source_key, target_key in field_map.items():
        if source_key in payload:
            widget[target_key] = payload[source_key]

    if "fontSize" in payload:
        widget["font_size"] = payload["fontSize"]
    elif "font_size" in payload:
        widget["font_size"] = payload["font_size"]
    if "width" in payload:
        widget["width"] = payload["width"]
    if "x" in payload:
        widget["x"] = payload["x"]
    if "y" in payload:
        widget["y"] = payload["y"]
    if source is not None:
        widget["source"] = source
    if style is not None:
        widget["style"] = style

    if not partial:
        widget.setdefault("enabled", True)
        widget.setdefault("color", "#e8f1ff")
        widget.setdefault("position", "custom")
        widget.setdefault("font_size", 72)
        widget.setdefault("width", 28)
        widget.setdefault("x", 0)
        widget.setdefault("y", 0)

    validate_widget(widget, partial=partial)
    widget["font_size"] = grid_value(widget.get("font_size"), 72)
    widget["width"] = grid_value(widget.get("width"), 28)
    widget["x"] = grid_value(widget.get("x"), 0)
    widget["y"] = grid_value(widget.get("y"), 0)
    return widget


def validate_widget(widget: dict[str, Any], *, partial: bool = False) -> None:
    required = ["label", "source", "style", "font_size", "width", "x", "y"]
    if not partial:
        for key in required:
            if key not in widget:
                raise ApiError(f"{key} is verplicht")

    if "label" in widget and (not isinstance(widget["label"], str) or not widget["label"].strip()):
        raise ApiError("label is verplicht en moet tekst zijn")

    if "source" in widget and widget["source"] not in OBD_PARAMETERS:
        raise ApiError("parameter moet een bekende OBD-waarde zijn")

    if "style" in widget and widget["style"] not in THEME_BY_RENDERER:
        raise ApiError("displayType moet een bekende weergavestijl zijn")

    if "font_size" in widget:
        font_size = grid_value(widget["font_size"], 72)
        if font_size < 28 or font_size > 132:
            raise ApiError("fontSize moet tussen 28 en 132 liggen")

    width = grid_value(widget.get("width"), 28)
    minimum_width = 3 if str(widget.get("source", "")).startswith("act_active") else 14
    if "width" in widget and (width < minimum_width or width > 44):
        raise ApiError(f"width moet tussen {minimum_width} en 44 liggen")

    x = grid_value(widget.get("x"), 0)
    y = grid_value(widget.get("y"), 0)
    if "x" in widget and (x < 0 or x > 86):
        raise ApiError("x moet tussen 0 en 86 liggen")
    if "y" in widget and (y < 0 or y > 86):
        raise ApiError("y moet tussen 0 en 86 liggen")
    if any(key in widget for key in ("x", "y", "width")) and (x + width > 90 or y + width > 90):
        raise ApiError("x/y + breedte moet binnen 90 grid-eenheden blijven")


def serialize_widget(widget_id: str, widget: dict[str, Any]) -> dict[str, Any]:
    renderer = LEGACY_STYLE_MAP.get(str(widget.get("style")), widget.get("style", "golf7"))
    display_type = THEME_BY_RENDERER.get(renderer, THEME_BY_RENDERER["golf7"])["id"]
    return {
        "id": widget_id,
        **widget,
        "parameter": widget.get("source"),
        "displayType": display_type,
        "fontSize": widget.get("font_size"),
        "height": widget.get("width"),
    }
