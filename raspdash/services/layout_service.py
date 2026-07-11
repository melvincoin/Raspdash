from __future__ import annotations

from typing import Any

GRID_LIMIT = 90
DIGITAL_HEIGHT_RATIO = 0.42


def grid_value(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def widget_rect(widget: dict[str, Any]) -> dict[str, int]:
    width = grid_value(widget.get("width"), 28)
    return {
        "x": grid_value(widget.get("x"), 0),
        "y": grid_value(widget.get("y"), 0),
        "width": width,
        "height": widget_height(widget),
    }


def widget_renderer(widget: dict[str, Any]) -> str:
    style = str(widget.get("style") or widget.get("displayType") or "golf7")
    legacy = {"gauge": "golf7", "digital": "digitaal", "Digitaal": "digitaal", "Golf 7 klok": "golf7", "VW Retro": "retro"}
    return legacy.get(style, style)


def is_digital(widget: dict[str, Any]) -> bool:
    return widget_renderer(widget) == "digitaal"


def widget_height(widget: dict[str, Any]) -> int:
    width = grid_value(widget.get("width"), 28)
    if is_digital(widget):
        return max(8, min(width, grid_value(width * DIGITAL_HEIGHT_RATIO, 10)))
    return width


def rects_overlap(left: dict[str, int], right: dict[str, int]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def find_overlaps(widgets: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    ids = [widget_id for widget_id, widget in widgets.items() if widget.get("enabled", True) is not False]
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            if rects_overlap(widget_rect(widgets[left_id]), widget_rect(widgets[right_id])):
                pairs.append({"a": left_id, "b": right_id})
    return pairs


def overlap_warnings(widgets: dict[str, dict[str, Any]], widget_id: str) -> list[str]:
    rect = widget_rect(widgets[widget_id])
    warnings = []
    for other_id, other in widgets.items():
        if other_id != widget_id and rects_overlap(rect, widget_rect(other)):
            warnings.append(f"overlap met widget {other_id}")
    return warnings


def clamp_widget(widget: dict[str, Any]) -> dict[str, Any]:
    updated = dict(widget)
    width = max(14, min(44, grid_value(updated.get("width"), 28)))
    height = widget_height({**updated, "width": width})
    updated["width"] = width
    updated["x"] = max(0, min(90 - width, grid_value(updated.get("x"), 0)))
    updated["y"] = max(0, min(90 - height, grid_value(updated.get("y"), 0)))
    return updated


def snap_to_grid(widget: dict[str, Any], grid_size: int) -> dict[str, Any]:
    updated = dict(widget)
    step = max(1, grid_value(grid_size, 5))
    updated["x"] = round(grid_value(updated.get("x"), 0) / step) * step
    updated["y"] = round(grid_value(updated.get("y"), 0) / step) * step
    return clamp_widget(updated)


def is_free(candidate: dict[str, Any], widgets: dict[str, dict[str, Any]], ignore_id: str | None = None) -> bool:
    rect = widget_rect(candidate)
    for widget_id, widget in widgets.items():
        if widget_id == ignore_id:
            continue
        if rects_overlap(rect, widget_rect(widget)):
            return False
    return True


def nearest_free_position(
    widget_id: str,
    widgets: dict[str, dict[str, Any]],
    *,
    grid_size: int,
) -> dict[str, Any]:
    widget = snap_to_grid(widgets[widget_id], grid_size)
    if is_free(widget, widgets, widget_id):
        return widget

    step = max(1, grid_value(grid_size, 5))
    width = grid_value(widget.get("width"), 28)
    start_x = grid_value(widget.get("x"), 0)
    start_y = grid_value(widget.get("y"), 0)
    best: tuple[int, dict[str, Any]] | None = None

    # Zoek de dichtstbijzijnde vrije gridplek zonder overlap.
    for y in range(0, GRID_LIMIT - width + 1, step):
        for x in range(0, GRID_LIMIT - width + 1, step):
            candidate = {**widget, "x": x, "y": y}
            if not is_free(candidate, widgets, widget_id):
                continue
            distance = abs(x - start_x) + abs(y - start_y)
            if best is None or distance < best[0]:
                best = (distance, candidate)
    return best[1] if best else widget


def auto_layout(
    widgets: dict[str, dict[str, Any]],
    order: list[str],
    *,
    strategy: str,
    padding: int,
    start_x: int,
    start_y: int,
) -> dict[str, dict[str, Any]]:
    updated = {widget_id: dict(widget) for widget_id, widget in widgets.items()}
    if strategy == "grid":
        return ideal_grid_layout(updated, order, padding=max(0, grid_value(padding, 2)))

    x = grid_value(start_x, 0)
    y = grid_value(start_y, 0)
    gap = max(0, grid_value(padding, 2))
    column_width = 0

    for widget_id in order:
        if widget_id not in updated:
            continue
        widget = clamp_widget(updated[widget_id])
        width = grid_value(widget.get("width"), 28)
        height = widget_height(widget)
        if strategy == "row":
            widget["x"] = x
            widget["y"] = grid_value(start_y, 0)
            x += width + gap
        elif strategy == "column":
            widget["x"] = grid_value(start_x, 0)
            widget["y"] = y
            y += height + gap
        else:
            if x + width > GRID_LIMIT:
                x = grid_value(start_x, 0)
                y += column_width + gap
                column_width = 0
            widget["x"] = x
            widget["y"] = y
            x += width + gap
            column_width = max(column_width, width)
        updated[widget_id] = clamp_widget(widget)
    return updated


def ideal_grid_layout(widgets: dict[str, dict[str, Any]], order: list[str], *, padding: int) -> dict[str, dict[str, Any]]:
    updated = {widget_id: dict(widget) for widget_id, widget in widgets.items()}
    enabled_ids = [widget_id for widget_id in order if widget_id in updated and updated[widget_id].get("enabled", True) is not False]
    analog_ids = [widget_id for widget_id in enabled_ids if not is_digital(updated[widget_id])]
    digital_ids = [widget_id for widget_id in enabled_ids if is_digital(updated[widget_id])]

    placed: dict[str, dict[str, Any]] = {}
    for index, widget_id in enumerate(analog_ids):
        widget = clamp_widget(updated[widget_id])
        target_x, target_y = analog_target(index, len(analog_ids), grid_value(widget.get("width"), 24), padding)
        widget["x"] = target_x
        widget["y"] = target_y
        placed[widget_id] = clamp_widget(widget)
        updated[widget_id] = placed[widget_id]

    for widget_id in digital_ids:
        widget = clamp_widget(updated[widget_id])
        widget["x"], widget["y"] = best_digital_position(widget, placed, padding)
        placed[widget_id] = clamp_widget(widget)
        updated[widget_id] = placed[widget_id]

    return updated


def analog_target(index: int, total: int, width: int, padding: int) -> tuple[int, int]:
    gap = max(2, padding)
    if total == 1:
        return ((GRID_LIMIT - width) // 2, (GRID_LIMIT - width) // 2)
    if total == 2:
        return (10 if index == 0 else GRID_LIMIT - width - 10, (GRID_LIMIT - width) // 2)
    if total == 3:
        xs = distributed_columns(3, width)
        return (xs[index], 6)
    if total == 4:
        xs = [8, GRID_LIMIT - width - 8]
        ys = [6, GRID_LIMIT - width - 6]
        return (xs[index % 2], ys[index // 2])

    columns = 3
    xs = distributed_columns(columns, width)
    row = index // columns
    column = index % columns
    y_step = min(width + gap + 12, max(width + gap, 42))
    y = min(GRID_LIMIT - width, row * y_step)
    return (xs[column], y)


def distributed_columns(count: int, width: int) -> list[int]:
    if count <= 1:
        return [(GRID_LIMIT - width) // 2]
    return [round(index * (GRID_LIMIT - width) / (count - 1)) for index in range(count)]


def best_digital_position(widget: dict[str, Any], placed: dict[str, dict[str, Any]], padding: int) -> tuple[int, int]:
    width = grid_value(widget.get("width"), 24)
    height = widget_height(widget)
    gap = max(2, padding)
    x_lanes = unique_ints([GRID_LIMIT - width, (GRID_LIMIT - width) // 2, 0, 2, GRID_LIMIT - width - 2])
    y_step = height + gap
    y_values = list(range(0, GRID_LIMIT - height + 1, y_step))
    candidates: list[tuple[int, int, int]] = []

    for x in x_lanes:
        for y in y_values:
            candidate = {**widget, "x": x, "y": y}
            if is_free(candidate, placed):
                candidates.append((digital_score(x, y, width, height), x, y))

    if not candidates:
        for y in range(0, GRID_LIMIT - height + 1):
            for x in range(0, GRID_LIMIT - width + 1):
                candidate = {**widget, "x": x, "y": y}
                if is_free(candidate, placed):
                    candidates.append((digital_score(x, y, width, height), x, y))

    if not candidates:
        return (0, 0)
    _score, x, y = min(candidates, key=lambda item: item[0])
    return (x, y)


def digital_score(x: int, y: int, width: int, height: int) -> int:
    right_bonus = (GRID_LIMIT - width - x) * 3
    lower_than_top_bonus = 0 if y >= 24 else 40
    alignment_penalty = (x % 2) + (y % max(1, height))
    return right_bonus + lower_than_top_bonus + alignment_penalty + y


def unique_ints(values: list[int]) -> list[int]:
    result: list[int] = []
    for value in values:
        clipped = max(0, min(GRID_LIMIT, grid_value(value)))
        if clipped not in result:
            result.append(clipped)
    return result


def sort_order(widgets: dict[str, dict[str, Any]], by: str, order: str) -> list[str]:
    reverse = order == "desc"
    key_map = {
        "label": lambda item: str(item[1].get("label", "")).lower(),
        "parameter": lambda item: str(item[1].get("source", item[1].get("parameter", ""))).lower(),
        "position_x": lambda item: grid_value(item[1].get("x"), 0),
        "position_y": lambda item: grid_value(item[1].get("y"), 0),
        "displayType": lambda item: str(item[1].get("displayType", item[1].get("style", ""))).lower(),
    }
    return [widget_id for widget_id, _ in sorted(widgets.items(), key=key_map[by], reverse=reverse)]


def free_space(widgets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    occupied = [[False for _ in range(GRID_LIMIT)] for _ in range(GRID_LIMIT)]
    for widget in widgets.values():
        rect = widget_rect(widget)
        for y in range(rect["y"], min(GRID_LIMIT, rect["y"] + rect["height"])):
            for x in range(rect["x"], min(GRID_LIMIT, rect["x"] + rect["width"])):
                occupied[y][x] = True

    free_cells = sum(1 for row in occupied for cell in row if not cell)
    best = {"x": 0, "y": 0, "width": 0, "height": 0, "area": 0}

    # Brute force op 90x90 cellen is klein genoeg en exact.
    for top in range(GRID_LIMIT):
        heights = [True] * GRID_LIMIT
        for bottom in range(top, GRID_LIMIT):
            for x in range(GRID_LIMIT):
                heights[x] = heights[x] and not occupied[bottom][x]
            start = None
            for x in range(GRID_LIMIT + 1):
                if x < GRID_LIMIT and heights[x]:
                    if start is None:
                        start = x
                elif start is not None:
                    width = x - start
                    height = bottom - top + 1
                    area = width * height
                    if area > best["area"]:
                        best = {"x": start, "y": top, "width": width, "height": height, "area": area}
                    start = None
    return {"free_cells": free_cells, "largest_free_rectangle": best}
