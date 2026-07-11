from __future__ import annotations


WIDGET_THEMES: dict[str, dict[str, str]] = {
    "GOLF7": {"id": "Golf 7 klok", "label": "Golf 7 klok", "renderer": "golf7"},
    "GOLF8": {"id": "Golf 8 klok", "label": "Golf 8 klok", "renderer": "golf8"},
    "RETRO": {"id": "VW Retro", "label": "VW Retro", "renderer": "retro"},
    "DIGITAAL": {"id": "Digitaal", "label": "Digitaal", "renderer": "digitaal"},
}

THEME_BY_ID = {theme["id"]: theme for theme in WIDGET_THEMES.values()}
THEME_BY_RENDERER = {theme["renderer"]: theme for theme in WIDGET_THEMES.values()}
