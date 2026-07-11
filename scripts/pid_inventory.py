from __future__ import annotations

import argparse
from pathlib import Path

import serial

from discovery_common import (
    PID_RANGES,
    elm_command,
    now_iso,
    parse_mode01_payload,
    setup_elm,
    supported_pids_from_payload,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory standard OBD supported PIDs without brute force.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--header", default="7DF")
    parser.add_argument("--output", default="data/pid_inventory.json")
    args = parser.parse_args()

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
            result["tested_supported_pids"][pid] = elm_command(ser, f"01{pid}", delay=0.25, timeout=5.0)

    write_json(Path(args.output), result)
    print(f"supported_pids={','.join(result['supported_pids']) or 'none'}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
