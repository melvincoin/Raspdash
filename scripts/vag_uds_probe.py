from __future__ import annotations

import argparse
from pathlib import Path

import serial

from discovery_common import elm_command, load_json, now_iso, setup_elm, update_metric, write_json


CATEGORY_TO_METRIC = {
    "oil_temperature": "engine_oil_temp",
    "transmission_temperature": "transmission_temp",
    "dsg_temperature": "dsg_temp",
    "clutch_temperature": "clutch_temp",
    "boost_actual": "charge_pressure_actual",
    "charge_pressure": "charge_pressure_requested",
}


def parse_simple_candidates(path: Path) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "categories:":
            continue
        if not raw_line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            categories.setdefault(current, [])
            continue
        if raw_line.startswith("  ") and stripped.endswith(":"):
            current = stripped[:-1]
            categories.setdefault(current, [])
            continue
        if current and stripped.startswith("-"):
            categories[current].append(stripped[1:].strip().strip("'\""))
    return categories


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe manually configured VAG/UDS candidates only.")
    parser.add_argument("--port", default="/dev/rfcomm0")
    parser.add_argument("--baudrate", type=int, default=38400)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--request-header", default="7E0")
    parser.add_argument("--candidates", default="config/vag_candidates.yaml")
    parser.add_argument("--output", default="data/vag_uds_probe.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--execute", action="store_true", help="Actually send configured read-only candidates.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates = parse_simple_candidates(Path(args.candidates))
    result = {
        "generated_at": now_iso(),
        "candidates_file": args.candidates,
        "execute": args.execute,
        "request_header": args.request_header,
        "categories": {},
    }

    total_candidates = sum(len(items) for items in candidates.values())
    if not args.execute or total_candidates == 0:
        for category, metric in CATEGORY_TO_METRIC.items():
            result["categories"][category] = {
                "status": "unknown" if total_candidates == 0 else "skipped",
                "candidates": candidates.get(category, []),
                "results": [],
                "reason": "no manual candidates configured" if total_candidates == 0 else "execute flag not set",
            }
            update_metric(Path(args.registry), metric, available=False, status="unknown", value=None)
        write_json(Path(args.output), result)
        print(f"Wrote {args.output}")
        print("No UDS requests sent.")
        return 0

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        result["setup"] = setup_elm(ser, args.protocol, args.request_header)
        for category, commands in candidates.items():
            category_result = {"status": "unknown", "candidates": commands, "results": []}
            for command in commands:
                item = elm_command(ser, command, delay=0.25, timeout=5.0)
                category_result["results"].append(item)
            statuses = {item["status"] for item in category_result["results"]}
            if "ok" in statuses:
                category_result["status"] = "works"
            elif "no_response" in statuses or "no_data" in statuses:
                category_result["status"] = "no_response"
            elif "unsupported" in statuses or "error" in statuses:
                category_result["status"] = "invalid"
            result["categories"][category] = category_result
            metric = CATEGORY_TO_METRIC.get(category)
            if metric:
                update_metric(
                    Path(args.registry),
                    metric,
                    available=category_result["status"] == "works",
                    status=category_result["status"],
                    value=None,
                    raw_response=" | ".join(item.get("raw", "") for item in category_result["results"]),
                )

    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
