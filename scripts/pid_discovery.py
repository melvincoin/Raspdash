from __future__ import annotations

import argparse
from pathlib import Path

import serial

from discovery_common import (
    PID_RANGES,
    build_base_registry,
    elm_command,
    load_json,
    now_iso,
    parse_mode01_payload,
    setup_elm,
    supported_pids_from_payload,
    update_metric,
    write_json,
    STANDARD_PID_METRICS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover supported OBD-II Mode 01 PIDs without brute force.")
    parser.add_argument("--port", default="/dev/rfcomm0")
    parser.add_argument("--baudrate", type=int, default=38400)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--header", default="7DF")
    parser.add_argument("--output", default="data/pid_discovery.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    registry_path = Path(args.registry)
    write_json(registry_path, build_base_registry(load_json(registry_path, {"metrics": {}})))

    result = {
        "generated_at": now_iso(),
        "port": args.port,
        "baudrate": args.baudrate,
        "protocol": args.protocol,
        "header": args.header,
        "range_queries": {},
        "supported_pids": [],
        "tested_supported_pids": {},
    }

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        result["setup"] = setup_elm(ser, args.protocol, args.header)
        supported: set[str] = set()
        for range_start in PID_RANGES:
            command = f"01{range_start}"
            item = elm_command(ser, command, delay=0.3, timeout=6.0)
            payload = parse_mode01_payload(item["response"], range_start)
            pids = supported_pids_from_payload(range_start, payload or [])
            item["decoded_supported_pids"] = pids
            result["range_queries"][command] = item
            supported.update(pids)

        result["supported_pids"] = sorted(supported)
        for pid in result["supported_pids"]:
            item = elm_command(ser, f"01{pid}", delay=0.25, timeout=5.0)
            result["tested_supported_pids"][pid] = item

    pid_to_metric = {meta["pid"]: key for key, meta in STANDARD_PID_METRICS.items() if meta.get("pid")}
    for pid, key in pid_to_metric.items():
        update_metric(
            registry_path,
            key,
            available=pid in result["supported_pids"],
            status="supported" if pid in result["supported_pids"] else "unsupported",
        )

    write_json(output, result)
    print(f"supported_pids={','.join(result['supported_pids']) or 'none'}")
    print(f"Wrote {output}")
    print(f"Updated {registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
