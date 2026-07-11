from __future__ import annotations

import argparse
from pathlib import Path

import serial

from discovery_common import elm_command, now_iso, setup_elm, write_json


SAFE_CHECKS = [
    ("identify", "ATI", 0.2, 2.0),
    ("device_description", "AT@1", 0.2, 2.0),
    ("device_identifier", "AT@2", 0.2, 2.0),
    ("protocol_name", "ATDP", 0.2, 2.0),
    ("protocol_number", "ATDPN", 0.2, 2.0),
    ("voltage", "ATRV", 0.2, 2.0),
    ("adaptive_timing", "ATAT1", 0.2, 2.0),
    ("describe_protocol", "ATDP", 0.2, 2.0),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory ELM/STN-compatible adapter capabilities.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--header", default="7DF")
    parser.add_argument("--json-output", default="data/adapter_inventory.json")
    parser.add_argument("--report", default="reports/adapter_inventory.md")
    args = parser.parse_args()

    result = {
        "generated_at": now_iso(),
        "port": args.port,
        "baudrate": args.baudrate,
        "protocol": args.protocol,
        "header": args.header,
        "checks": {},
    }
    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        result["setup"] = setup_elm(ser, args.protocol, args.header)
        for name, command, delay, timeout in SAFE_CHECKS:
            result["checks"][name] = elm_command(ser, command, delay, timeout)

    write_json(Path(args.json_output), result)
    lines = [
        "# Adapter Inventory",
        "",
        f"Generated: {result['generated_at']}",
        f"Port: `{args.port}`",
        f"Baudrate: `{args.baudrate}`",
        "",
        "| Check | Command | Status | Response |",
        "|---|---|---|---|",
    ]
    for name, item in result["checks"].items():
        response = str(item.get("response", "")).replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {name} | `{item['command']}` | {item['status']} | {response} |")
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.json_output}")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
