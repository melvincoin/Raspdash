from __future__ import annotations

import argparse
import copy
from pathlib import Path

import serial

from discovery_common import (
    STANDARD_PID_METRICS,
    decode_metric,
    elm_command,
    load_json,
    now_iso,
    parse_mode01_payload,
    setup_elm,
    update_metric,
    write_json,
)


TARGET_METRICS = [
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
    "engine_oil_temp",
]

EXTRA_STANDARD = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe selected standard values only when supported by discovery.")
    parser.add_argument("--port", default="/dev/rfcomm0")
    parser.add_argument("--baudrate", type=int, default=38400)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--header", default="7DF")
    parser.add_argument("--pid-discovery", default="data/pid_discovery.json")
    parser.add_argument("--output", default="data/value_probe.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--samples", type=int, default=3)
    return parser.parse_args()


def metric_meta(key: str) -> dict:
    return EXTRA_STANDARD.get(key) or STANDARD_PID_METRICS[key]


def main() -> int:
    args = parse_args()
    discovery = load_json(Path(args.pid_discovery), {"supported_pids": []})
    supported_pids = set(discovery.get("supported_pids", []))
    result = {
        "generated_at": now_iso(),
        "protocol": args.protocol,
        "header": args.header,
        "supported_pids_source": args.pid_discovery,
        "values": {},
    }

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        result["setup"] = setup_elm(ser, args.protocol, args.header)
        for key in TARGET_METRICS:
            if key == "battery_voltage":
                samples = [elm_command(ser, "ATRV", delay=0.2, timeout=3.0) for _ in range(args.samples)]
                item = copy.deepcopy(next((sample for sample in samples if decode_metric(key, None, sample["response"]) is not None), samples[-1]))
                value = decode_metric(key, None, item["response"])
                item["samples"] = samples
                item["value"] = value
                item["unit"] = "V"
                result["values"][key] = item
                update_metric(
                    Path(args.registry),
                    key,
                    available=value is not None,
                    status="ok" if value is not None else item["status"],
                    value=value,
                    raw_response=item["raw"],
                )
                continue

            meta = metric_meta(key)
            pid = meta["pid"]
            samples = [elm_command(ser, f"01{pid}", delay=0.25, timeout=5.0) for _ in range(args.samples)]
            decoded_samples = []
            for sample in samples:
                payload = parse_mode01_payload(sample["response"], pid)
                decoded = decode_metric(key, payload)
                if key == "engine_oil_temp" and payload:
                    decoded = payload[0] - 40
                sample["payload"] = payload
                sample["value"] = decoded
                decoded_samples.append((sample, payload, decoded))
            item, payload, value = next(
                ((sample, sample_payload, decoded) for sample, sample_payload, decoded in decoded_samples if decoded is not None),
                decoded_samples[-1],
            )
            item = copy.deepcopy(item)
            item["listed_supported_by_discovery"] = pid in supported_pids
            item["samples"] = samples
            item["payload"] = payload
            item["value"] = value
            item["unit"] = meta["unit"]
            result["values"][key] = item
            update_metric(
                Path(args.registry),
                key,
                available=value is not None,
                status="ok" if value is not None else item["status"],
                value=value,
                raw_response=item["raw"],
            )

    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    print(f"Updated {args.registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
