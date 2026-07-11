from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import serial

from discovery_common import elm_command, load_json, now_iso, setup_elm, update_metric, write_json


def parse_ecus(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    ecus: dict[str, dict[str, Any]] = {}
    current: str | None = None
    in_ecus = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "ecus:":
            in_ecus = True
            continue
        if in_ecus and raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            ecus[current] = {}
            continue
        if current and raw.startswith("    ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            ecus[current][key] = value.strip().strip('"').strip("'")
    return ecus


def parse_candidates(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    candidates: list[dict[str, str]] = []
    category: str | None = None
    metric: str | None = None
    in_candidates = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped == "categories:":
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
            category = stripped[:-1]
            metric = None
            in_candidates = False
            continue
        if category and raw.startswith("    metric:"):
            metric = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            in_candidates = False
            continue
        if category and raw.startswith("    candidates:"):
            in_candidates = True
            continue
        if category and in_candidates and stripped.startswith("-"):
            value = stripped[1:].strip().strip('"').strip("'")
            if ":" in value:
                ecu, did = value.split(":", 1)
            else:
                ecu, did = "engine", value
            candidates.append({"category": category, "metric": metric or category, "ecu": ecu, "did": did})
    return candidates


def classify(response: dict[str, Any], did: str) -> str:
    compact = "".join(ch for ch in response.get("response", "").upper() if ch in "0123456789ABCDEF")
    if response.get("status") in {"no_response", "no_data"}:
        return "no_response"
    if "7F22" in compact:
        return "unsupported"
    if f"62{did.upper()}" in compact or "62" in compact:
        return "works"
    if response.get("status") == "ok":
        return "unknown"
    return response.get("status", "unknown")


def decode_value(metric: str, did: str, response: dict[str, Any]) -> float | None:
    compact = "".join(ch for ch in response.get("response", "").upper() if ch in "0123456789ABCDEF")
    marker = f"62{did.upper()}"
    index = compact.find(marker)
    if index < 0:
        return None
    payload = compact[index + len(marker) :]
    if len(payload) < 2:
        return None
    data = [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]
    if metric in {"engine_oil_temp", "dsg_temp", "transmission_temp", "clutch_temp"} and did.upper() == "F45C":
        return data[0] - 40
    if metric == "engine_oil_temp" and did.upper() in {"202F", "30F9", "38BB", "30DB", "3A59"} and len(data) >= 2:
        raw = (data[0] * 256) + data[1]
        return (raw - 2731.4) / 10.0
    if metric in {"dsg_temp", "transmission_temp"} and did.upper() == "A008" and data:
        return data[0] - 40
    if metric in {"dsg_temp", "transmission_temp"} and did.upper() in {"0024", "0102"} and data:
        candidates = [data[0] - 40]
        if len(data) >= 2:
            raw = (data[0] * 256) + data[1]
            candidates.extend([(raw - 2731) / 10.0, raw / 10.0])
        for value in candidates:
            if -40 <= value <= 180:
                return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only UDS ReadDataByIdentifier probe for manual candidates.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--ecus", default="config/uds_ecus.yaml")
    parser.add_argument("--candidates", default="config/vag_dids_candidates.yaml")
    parser.add_argument("--output", default="data/uds_probe.json")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ecus = parse_ecus(Path(args.ecus))
    candidates = parse_candidates(Path(args.candidates))
    result = {
        "generated_at": now_iso(),
        "execute": args.execute,
        "service": "22",
        "requests_sent": 0,
        "ecus": ecus,
        "candidates": candidates,
        "results": [],
    }

    if not args.execute or not candidates:
        result["status"] = "prepared_only" if not candidates else "execute_flag_required"
        write_json(Path(args.output), result)
        print(f"Wrote {args.output}")
        print("No UDS requests sent.")
        return 0

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        for candidate in candidates:
            ecu = ecus.get(candidate["ecu"])
            if not ecu or str(ecu.get("enabled", "true")).lower() == "false":
                item = {**candidate, "status": "invalid", "error": "ECU not configured or disabled"}
                result["results"].append(item)
                continue
            did = "".join(ch for ch in candidate["did"].upper() if ch in "0123456789ABCDEF")
            if len(did) != 4:
                item = {**candidate, "status": "invalid", "error": "DID must be exactly 2 bytes"}
                result["results"].append(item)
                continue
            setup = setup_elm(ser, args.protocol, ecu["request_header"])
            response = elm_command(ser, f"22{did}", delay=0.25, timeout=8.0)
            status = classify(response, did)
            value = decode_value(candidate["metric"], did, response)
            result["requests_sent"] += 1
            item = {**candidate, "did": did, "status": status, "value": value, "setup": setup, "response": response}
            result["results"].append(item)
            update_metric(
                Path(args.registry),
                candidate["metric"],
                available=status == "works" and value is not None,
                status=status,
                value=value,
                raw_response=response.get("raw"),
                confidence=0.45 if status == "works" and value is not None else 0.2,
            )

    write_json(Path(args.output), result)
    print(f"Wrote {args.output}")
    print(f"UDS requests sent: {result['requests_sent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
