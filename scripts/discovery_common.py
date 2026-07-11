from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial


PID_RANGES = ["00", "20", "40", "60", "80", "A0"]

STANDARD_PID_METRICS: dict[str, dict[str, Any]] = {
    "battery_voltage": {
        "display_name": "Battery voltage",
        "unit": "V",
        "category": "standard",
        "source": "ELM327 ATRV",
        "pid": None,
        "confidence": 0.9,
        "estimated": False,
        "min": 10,
        "max": 15,
        "decimals": 1,
    },
    "throttle_position": {
        "display_name": "Throttle position",
        "unit": "%",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 11",
        "pid": "11",
        "confidence": 0.8,
        "estimated": False,
        "min": 0,
        "max": 100,
        "decimals": 1,
    },
    "intake_temp": {
        "display_name": "Intake temperature",
        "unit": "deg C",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 0F",
        "pid": "0F",
        "confidence": 0.8,
        "estimated": False,
        "min": -40,
        "max": 100,
        "decimals": 0,
    },
    "coolant_temp": {
        "display_name": "Coolant temperature",
        "unit": "deg C",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 05",
        "pid": "05",
        "confidence": 0.8,
        "estimated": False,
        "min": -40,
        "max": 130,
        "decimals": 0,
    },
    "vehicle_speed": {
        "display_name": "Vehicle speed",
        "unit": "km/h",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 0D",
        "pid": "0D",
        "confidence": 0.8,
        "estimated": False,
        "min": 0,
        "max": 260,
        "decimals": 0,
    },
    "engine_rpm": {
        "display_name": "Engine RPM",
        "unit": "rpm",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 0C",
        "pid": "0C",
        "confidence": 0.8,
        "estimated": False,
        "min": 0,
        "max": 8000,
        "decimals": 0,
    },
    "engine_load": {
        "display_name": "Engine load",
        "unit": "%",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 04",
        "pid": "04",
        "confidence": 0.8,
        "estimated": False,
        "min": 0,
        "max": 100,
        "decimals": 1,
    },
    "manifold_absolute_pressure": {
        "display_name": "Manifold absolute pressure",
        "unit": "kPa",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 0B",
        "pid": "0B",
        "confidence": 0.8,
        "estimated": False,
        "min": 0,
        "max": 255,
        "decimals": 0,
    },
    "barometric_pressure": {
        "display_name": "Barometric pressure",
        "unit": "kPa",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 33",
        "pid": "33",
        "confidence": 0.8,
        "estimated": False,
        "min": 70,
        "max": 110,
        "decimals": 0,
    },
    "fuel_rate": {
        "display_name": "Fuel rate",
        "unit": "L/h",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 5E",
        "pid": "5E",
        "confidence": 0.75,
        "estimated": False,
        "min": 0,
        "max": 80,
        "decimals": 2,
    },
    "boost_estimated_bar": {
        "display_name": "Boost estimated",
        "unit": "bar",
        "category": "calculated",
        "source": "MAP - BARO",
        "pid": None,
        "confidence": 0.55,
        "estimated": True,
        "min": -1,
        "max": 2,
        "decimals": 2,
        "raw_sources": ["manifold_absolute_pressure", "barometric_pressure"],
    },
    "boost_estimated_kpa": {
        "display_name": "Boost estimated",
        "unit": "kPa",
        "category": "calculated",
        "source": "MAP - BARO",
        "pid": None,
        "confidence": 0.55,
        "estimated": True,
        "min": -100,
        "max": 200,
        "decimals": 0,
        "raw_sources": ["manifold_absolute_pressure", "barometric_pressure"],
    },
}

VAG_METRICS: dict[str, dict[str, Any]] = {
    "engine_oil_temp": ("Engine oil temperature", "deg C", "VAG/UDS experimental"),
    "dsg_temp": ("DSG temperature", "deg C", "VAG/UDS experimental"),
    "transmission_temp": ("Transmission temperature", "deg C", "VAG/UDS experimental"),
    "clutch_temp": ("Clutch temperature", "deg C", "VAG/UDS experimental"),
    "charge_pressure_actual": ("Charge pressure actual", "kPa", "VAG/UDS experimental"),
    "charge_pressure_requested": ("Charge pressure requested", "kPa", "VAG/UDS experimental"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_until_prompt(ser: serial.Serial, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = ser.read(64)
        if chunk:
            chunks.append(chunk)
            if b">" in chunk:
                break
        else:
            time.sleep(0.02)
    return b"".join(chunks).decode("ascii", errors="replace")


def elm_command(ser: serial.Serial, command: str, delay: float = 0.2, timeout: float = 4.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        ser.reset_input_buffer()
        ser.write((command + "\r").encode("ascii"))
        ser.flush()
        time.sleep(delay)
        raw = read_until_prompt(ser, timeout)
        response = raw.replace(command, "").replace(">", "").replace("\r", "\n").strip()
        normalized = response.upper().replace(" ", "")
        return {
            "command": command,
            "ok": bool(raw),
            "raw": raw,
            "response": response,
            "status": response_status(normalized, raw),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "command": command,
            "ok": False,
            "raw": "",
            "response": "",
            "status": "error",
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def response_status(normalized: str, raw: str) -> str:
    if not raw:
        return "no_response"
    if "NODATA" in normalized:
        return "no_data"
    if "UNABLETOCONNECT" in normalized:
        return "no_response"
    if "?" in normalized or "ERROR" in normalized:
        return "unsupported"
    if "STOPPED" in normalized:
        return "stopped"
    return "ok"


def setup_elm(ser: serial.Serial, protocol: str, header: str) -> list[dict[str, Any]]:
    setup = [
        ("ATZ", 1.0, 3.0),
        ("ATE0", 0.2, 2.0),
        ("ATL0", 0.2, 2.0),
        ("ATS0", 0.2, 2.0),
        ("ATH1", 0.2, 2.0),
        ("ATCAF1", 0.2, 2.0),
        (f"ATSP{protocol}", 0.4, 3.0),
    ]
    if header:
        setup.append((f"ATSH{header}", 0.2, 2.0))
    return [elm_command(ser, command, delay, timeout) for command, delay, timeout in setup]


def parse_mode01_payload(response: str, pid: str) -> list[int] | None:
    compact = "".join(ch for ch in response.upper() if ch in "0123456789ABCDEF")
    marker = f"41{pid}"
    index = compact.find(marker)
    if index < 0:
        return None
    payload = compact[index + len(marker) :]
    if len(payload) < 2:
        return None
    return [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]


def supported_pids_from_payload(range_start: str, payload: list[int]) -> list[str]:
    if len(payload) < 4:
        return []
    base = int(range_start, 16)
    bits = "".join(f"{byte:08b}" for byte in payload[:4])
    return [f"{base + index + 1:02X}" for index, bit in enumerate(bits) if bit == "1"]


def decode_metric(metric_key: str, payload: list[int] | None, raw_response: str | None = None) -> float | None:
    if metric_key == "battery_voltage" and raw_response:
        for token in raw_response.replace("V", " ").split():
            try:
                return float(token)
            except ValueError:
                continue
    if not payload:
        return None
    if metric_key == "engine_load":
        return payload[0] * 100 / 255
    if metric_key == "coolant_temp":
        return payload[0] - 40
    if metric_key == "manifold_absolute_pressure":
        return payload[0]
    if metric_key == "engine_rpm" and len(payload) >= 2:
        return ((payload[0] * 256) + payload[1]) / 4
    if metric_key == "vehicle_speed":
        return payload[0]
    if metric_key == "intake_temp":
        return payload[0] - 40
    if metric_key == "throttle_position":
        return payload[0] * 100 / 255
    if metric_key == "barometric_pressure":
        return payload[0]
    if metric_key == "fuel_rate" and len(payload) >= 2:
        return ((payload[0] * 256) + payload[1]) * 0.05
    return None


def build_base_registry(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = existing or {"generated_at": now_iso(), "metrics": {}}
    registry["generated_at"] = now_iso()
    metrics = registry.setdefault("metrics", {})
    for key, meta in STANDARD_PID_METRICS.items():
        item = metrics.setdefault(key, {})
        item.update(
            {
                "key": key,
                "display_name": meta["display_name"],
                "unit": meta["unit"],
                "category": meta["category"],
                "source": meta["source"],
                "confidence": meta["confidence"],
                "estimated": meta["estimated"],
                "min": meta["min"],
                "max": meta["max"],
                "decimals": meta["decimals"],
                "available": item.get("available", False),
                "status": item.get("status", "unavailable"),
                "last_update": item.get("last_update"),
                "value": item.get("value"),
            }
        )
        if "raw_sources" in meta:
            item["raw_sources"] = meta["raw_sources"]
    for key, (display_name, unit, source) in VAG_METRICS.items():
        item = metrics.setdefault(key, {})
        item.update(
            {
                "key": key,
                "display_name": display_name,
                "unit": unit,
                "category": "vag_uds_experimental",
                "source": source,
                "confidence": item.get("confidence", 0.2),
                "estimated": False,
                "min": item.get("min"),
                "max": item.get("max"),
                "decimals": item.get("decimals", 1),
                "available": item.get("available", False),
                "status": item.get("status", "unknown"),
                "last_update": item.get("last_update"),
                "value": item.get("value"),
            }
        )
    return registry


def update_metric(
    registry_path: Path,
    key: str,
    *,
    available: bool,
    status: str,
    value: float | None = None,
    raw_response: str | None = None,
    confidence: float | None = None,
) -> None:
    registry = build_base_registry(load_json(registry_path, {"metrics": {}}))
    item = registry["metrics"][key]
    item["available"] = available
    item["status"] = status
    item["value"] = value
    item["last_update"] = now_iso()
    if raw_response is not None:
        item["raw_response"] = raw_response
    if confidence is not None:
        item["confidence"] = confidence
    write_json(registry_path, registry)
