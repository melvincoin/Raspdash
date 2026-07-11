from __future__ import annotations

import argparse
import copy
from pathlib import Path

import serial

from discovery_common import (
    STANDARD_PID_METRICS,
    build_base_registry,
    decode_metric,
    elm_command,
    load_json,
    now_iso,
    parse_mode01_payload,
    setup_elm,
    update_metric,
    write_json,
)


TARGETS = [
    "battery_voltage",
    "engine_load",
    "throttle_position",
    "intake_temp",
    "vehicle_speed",
    "engine_rpm",
    "coolant_temp",
    "manifold_absolute_pressure",
    "barometric_pressure",
    "fuel_rate",
]

EXTRA = {
    "engine_oil_temp": {
        "display_name": "Engine oil temperature",
        "unit": "deg C",
        "category": "standard",
        "source": "OBD-II Mode 01 PID 5C",
        "pid": "5C",
        "confidence": 0.7,
        "estimated": False,
        "min": -40,
        "max": 160,
        "decimals": 0,
    }
}


def meta(key: str) -> dict:
    return EXTRA.get(key) or STANDARD_PID_METRICS[key]


def main() -> int:
    parser = argparse.ArgumentParser(description="Map discovered OBD values to dashboard metric registry.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--header", default="7DF")
    parser.add_argument("--pid-inventory", default="data/pid_inventory.json")
    parser.add_argument("--output", default="data/metric_discovery.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--samples", type=int, default=6)
    args = parser.parse_args()

    registry_path = Path(args.registry)
    write_json(registry_path, build_base_registry(load_json(registry_path, {"metrics": {}})))
    result = {"generated_at": now_iso(), "values": {}, "pid_inventory": args.pid_inventory}

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        result["setup"] = setup_elm(ser, args.protocol, args.header)
        for key in [*TARGETS, "engine_oil_temp"]:
            if key == "battery_voltage":
                samples = [elm_command(ser, "ATRV", delay=0.2, timeout=3.0) for _ in range(args.samples)]
                item = copy.deepcopy(next((s for s in samples if decode_metric(key, None, s["response"]) is not None), samples[-1]))
                value = decode_metric(key, None, item["response"])
            else:
                pid = meta(key)["pid"]
                samples = [elm_command(ser, f"01{pid}", delay=0.25, timeout=5.0) for _ in range(args.samples)]
                item = copy.deepcopy(samples[-1])
                value = None
                for sample in samples:
                    payload = parse_mode01_payload(sample["response"], pid)
                    sample["payload"] = payload
                    sample["value"] = payload[0] - 40 if key == "engine_oil_temp" and payload else decode_metric(key, payload)
                    if sample["value"] is not None and value is None:
                        item = copy.deepcopy(sample)
                        value = sample["value"]
            item["samples"] = samples
            item["value"] = value
            result["values"][key] = item
            update_metric(
                registry_path,
                key,
                available=value is not None,
                status="ok" if value is not None else item["status"],
                value=value,
                raw_response=item.get("raw"),
            )

    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    print(f"Updated {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
