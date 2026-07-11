from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"


DEFAULT_CONFIG: dict[str, Any] = {
    "display": {
        "resolution": "1280x720",
        "fullscreen": True,
        "brightness": 1.0,
        "background_dim": 0.72,
        "render_scale": 0.65,
        "splash": "boot-splash.jpg",
        "background": "carbon-pattern",
    },
    "obd": {
        "provider": "simulated",
        "vehicle_stream_interval": 0.1,
        "hexv2": {
            "port": "auto",
            "baudrate": 115200,
            "allow_requests": False,
        },
        "elm327": {
            "port": "/dev/ttyUSB0",
            "baudrate": 115200,
            "bluetooth_mac": "",
            "protocol": "6",
            "header": "7DF",
            "poll_timeout": 12.0,
            "min_poll_interval": 0.05,
            "slow_poll_interval": 1.0,
            "ride_logging": True,
            "acc_distance_logging": False,
            "ride_log_interval": 1.0,
            "ride_log_duration": 900.0,
            "allow_requests": False,
        },
    },
    "dashboard": {
        "widget_order": [
            "engine_rpm",
            "vehicle_speed",
            "coolant_temp",
            "intake_temp",
            "battery_voltage",
            "engine_load",
            "throttle",
            "map_pressure",
            "barometric_pressure",
            "boost",
        ],
        "widgets": {
            "oil_temp": {
                "enabled": False,
                "source": "oil_temp_c",
                "label": "ENGINE OIL",
                "font_size": 72,
                "color": "#e8f1ff",
                "position": "left",
                "x": 8,
                "y": 32,
                "width": 28,
                "displayType": "Golf 7 klok",
                "style": "golf7",
            },
            "dsg_temp": {
                "enabled": False,
                "source": "dsg_temp_c",
                "label": "DSG TEMP",
                "font_size": 72,
                "color": "#e8f1ff",
                "position": "right",
                "x": 64,
                "y": 32,
                "width": 28,
                "displayType": "Golf 7 klok",
                "style": "golf7",
            },
            "battery_voltage": {
                "enabled": True,
                "source": "battery_voltage_v",
                "label": "BATTERY",
                "font_size": 46,
                "color": "#d9f5ff",
                "position": "custom",
                "x": 79,
                "y": 10,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "engine_load": {
                "enabled": True,
                "source": "engine_load_pct",
                "label": "LOAD",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 3,
                "y": 52,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "intake_temp": {
                "enabled": True,
                "source": "intake_temp_c",
                "label": "INTAKE AIR",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 60,
                "y": 10,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "vehicle_speed": {
                "enabled": True,
                "source": "speed_kmh",
                "label": "SPEED",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 22,
                "y": 10,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "engine_rpm": {
                "enabled": True,
                "source": "rpm",
                "label": "RPM",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 3,
                "y": 10,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "coolant_temp": {
                "enabled": True,
                "source": "coolant_temp_c",
                "label": "COOLANT",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 41,
                "y": 10,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "throttle": {
                "enabled": True,
                "source": "throttle_pct",
                "label": "THROTTLE",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 22,
                "y": 52,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "map_pressure": {
                "enabled": True,
                "source": "map_kpa",
                "label": "MAP",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 41,
                "y": 52,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "barometric_pressure": {
                "enabled": True,
                "source": "barometric_pressure_kpa",
                "label": "BARO",
                "font_size": 46,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 60,
                "y": 52,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
            "boost": {
                "enabled": True,
                "source": "boost_bar",
                "label": "BOOST",
                "font_size": 42,
                "color": "#e8f1ff",
                "position": "custom",
                "x": 79,
                "y": 52,
                "width": 18,
                "displayType": "Digitaal",
                "style": "digitaal",
            },
        },
        "accent_color": "#2d7dff",
        "dimmed_color": "#7e8fa8",
        "status_enabled": True,
        "oil_startup_toast": {
            "enabled": True,
            "position": "top-center",
            "duration_seconds": 60,
            "source": "oil_level_method_2_pct",
            "warn_pct": 30,
            "critical_pct": 20,
            "width_pct": 46,
            "x_pct": 50,
            "y_pct": 5.5,
        },
        "dtc_startup_toast": {
            "enabled": True,
            "position": "bottom-center",
            "duration_seconds": 90,
            "width_pct": 60,
            "x_pct": 50,
            "y_pct": 6,
        },
        "editor_snap": True,
        "editor_grid_size": 2.5,
        "warning_thresholds": {
            "oil_temp_c": {"warn": 115, "critical": 125},
            "dsg_temp_c": {"warn": 105, "critical": 120},
            "coolant_temp_c": {"warn": 120, "critical": 130},
            "intake_temp_c": {"warn": 60, "critical": 75},
        },
    },
    "ota": {
        "enabled": False,
        "channel": "local",
        "manifest_url": "",
    },
}


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_data_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return merge_defaults(copy.deepcopy(DEFAULT_CONFIG), loaded)


def save_config(config: dict[str, Any]) -> None:
    ensure_data_dirs()
    fd, temp_name = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=CONFIG_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, CONFIG_PATH)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def merge_defaults(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = merge_defaults(base[key], value)
        else:
            base[key] = value
    return base
