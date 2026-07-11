from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import serial

from discovery_common import elm_command, load_json, now_iso, setup_elm, write_json


FIRST_BATCH = {
    ("engine", "11BD"),
    ("engine", "15B7"),
    ("engine", "11F0"),
    ("engine", "11F1"),
    ("engine", "11DD"),
    ("engine", "F40B"),
    ("engine", "F433"),
    ("engine", "177D"),
    ("engine", "181D"),
    ("engine", "58D1"),
    ("transmission", "2104"),
    ("transmission", "38B2"),
    ("transmission", "028D"),
    ("transmission", "380A"),
    ("transmission", "380B"),
    ("transmission", "3808"),
    ("transmission", "3816"),
    ("transmission", "381D"),
    ("transmission", "382F"),
    ("transmission", "3839"),
}


def parse_candidates(path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_candidates = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped == "candidates:":
            in_candidates = True
            continue
        if not in_candidates or not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current:
                candidates.append(current)
            current = {}
            rest = stripped[2:]
            if ":" in rest:
                key, value = rest.split(":", 1)
                current[key.strip()] = clean_yaml_value(value)
            continue
        if current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = clean_yaml_value(value)
    if current:
        candidates.append(current)
    return candidates


def clean_yaml_value(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value


def write_candidates(path: Path, candidates: list[dict[str, Any]]) -> None:
    head = [
        "metadata:",
        "  engine_asam: EV_ECM15TFS01105E906018BC",
        "  engine_part: 05E906018BC",
        "  transmission_asam: EV_TCMDQ381061",
        "  transmission_part: 0GC300046A",
        '  service: "22"',
        "  source: OBDeleven live data export 2026-06-16",
        "candidates:",
    ]
    lines = head[:]
    for item in candidates:
        lines.append(f"  - module: {item['module']}")
        for key in ("header", "did", "metric_key", "display_name", "priority", "unit_guess", "status"):
            value = item.get(key, "")
            if key in {"header", "did"}:
                value = f'"{value}"'
            elif key == "unit_guess" and str(value) == "%":
                value = '"%"'
            lines.append(f"    {key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_hex(response: str) -> str:
    return "".join(ch for ch in response.upper() if ch in "0123456789ABCDEF")


def extract_payload(response: str, did: str) -> list[int]:
    compact = compact_hex(response)
    marker = f"62{did.upper()}"
    index = compact.find(marker)
    if index < 0:
        return []
    payload = compact[index + len(marker) :]
    return [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]


def classify(response: dict[str, Any], did: str) -> str:
    compact = compact_hex(response.get("response", ""))
    if f"62{did.upper()}" in compact:
        return "positive"
    if "7F2231" in compact or "7F22" in compact:
        return "unsupported"
    if response.get("status") in {"no_response", "no_data", "stopped", "error"}:
        return response["status"]
    return "unknown"


def u16_be(payload: list[int]) -> int | None:
    if len(payload) < 2:
        return None
    return payload[0] * 256 + payload[1]


def s16_be(payload: list[int]) -> int | None:
    raw = u16_be(payload)
    if raw is None:
        return None
    return raw - 65536 if raw >= 32768 else raw


def decode_candidates(item: dict[str, Any], payload: list[int]) -> list[dict[str, Any]]:
    if not payload:
        return []
    unit = str(item.get("unit_guess", "raw"))
    guesses: list[dict[str, Any]] = [{"decoder": "raw_hex", "value": " ".join(f"{b:02X}" for b in payload), "plausible": True}]
    raw_u16 = u16_be(payload)
    raw_s16 = s16_be(payload)
    if unit == "deg C":
        guesses.append({"decoder": "u8-40", "value": payload[0] - 40, "plausible": -39 < payload[0] - 40 < 180 and payload[0] != 0})
        if raw_u16 is not None:
            guesses.append({"decoder": "u16/10", "value": raw_u16 / 10, "plausible": -39 < raw_u16 / 10 < 180 and raw_u16 != 0})
        if raw_s16 is not None:
            guesses.append({"decoder": "s16/10", "value": raw_s16 / 10, "plausible": -39 < raw_s16 / 10 < 180 and raw_s16 != 0})
    elif unit in {"kPa", "bar"}:
        if raw_u16 is not None:
            guesses.extend(
                [
                    {"decoder": "u16_kPa", "value": raw_u16, "plausible": 0 < raw_u16 < 400},
                    {"decoder": "u16_hPa_to_kPa", "value": raw_u16 / 10, "plausible": 0 < raw_u16 / 10 < 400},
                    {"decoder": "u16/100_bar", "value": raw_u16 / 100, "plausible": 0 <= raw_u16 / 100 < 30},
                ]
            )
        guesses.append({"decoder": "u8_kPa", "value": payload[0], "plausible": 0 < payload[0] < 255})
    elif unit in {"rpm", "km/h"}:
        if raw_u16 is not None:
            guesses.extend(
                [
                    {"decoder": "u16", "value": raw_u16, "plausible": 0 <= raw_u16 < 10000},
                    {"decoder": "u16/4", "value": raw_u16 / 4, "plausible": 0 <= raw_u16 / 4 < 10000},
                ]
            )
    elif unit == "V" and raw_u16 is not None:
        guesses.extend(
            [
                {"decoder": "u16/1000", "value": raw_u16 / 1000, "plausible": 5 < raw_u16 / 1000 < 16},
                {"decoder": "u16/100", "value": raw_u16 / 100, "plausible": 5 < raw_u16 / 100 < 16},
            ]
        )
    return guesses


def registry_entry(item: dict[str, Any], guess: dict[str, Any], payload: list[int], response: str) -> dict[str, Any]:
    return {
        "display_name": item["display_name"],
        "module": item["module"],
        "header": item["header"],
        "did": item["did"],
        "unit": item.get("unit_guess"),
        "source": "OBDeleven targeted UDS DID",
        "decoder": guess["decoder"],
        "value": guess["value"],
        "raw_payload": " ".join(f"{b:02X}" for b in payload),
        "raw_response": response,
        "status": "candidate_positive_needs_validation",
        "available": False,
        "confidence": 0.45,
        "last_update": now_iso(),
    }


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# OBDeleven Candidates Test",
        "",
        f"Generated: {now_iso()}",
        "",
        "| module | DID | metric | status | payload | plausible decodes |",
        "|---|---:|---|---|---|---|",
    ]
    for row in rows:
        decodes = []
        for guess in row.get("decode_guesses", []):
            if guess.get("plausible"):
                decodes.append(f"{guess['decoder']}={guess['value']}")
        lines.append(
            f"| {row['module']} | `{row['did']}` | {row['metric_key']} | {row['status']} | `{row.get('payload_hex', '')}` | {', '.join(decodes) or '-'} |"
        )
    lines.extend(
        [
            "",
            "Only `positive` responses contain `62 <DID>`. `unsupported` means `7F 22 31`.",
            "Plausible decode guesses are not dashboard-approved until validated against OBDeleven/VCDS live values.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test targeted OBDeleven UDS DID candidates in small read-only batches.")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--candidates", default="config/obdeleven_candidates.yaml")
    parser.add_argument("--jsonl", default="data/obdeleven_candidates_test.jsonl")
    parser.add_argument("--report", default="reports/obdeleven_candidates_test.md")
    parser.add_argument("--registry", default="data/metric_registry.json")
    parser.add_argument("--module", choices=["engine", "transmission", "all"], default="all")
    parser.add_argument("--batch", choices=["first", "unknown"], default="first")
    parser.add_argument("--max-per-module", type=int, default=10)
    parser.add_argument("--update-candidates", action="store_true", help="Write supported/unsupported statuses back to the candidates YAML.")
    parser.add_argument("--update-registry", action="store_true", help="Register positive plausible results after manual validation.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    candidates = parse_candidates(candidates_path)
    selected = [
        item
        for item in candidates
        if (args.module == "all" or item["module"] == args.module)
        and (args.batch != "first" or (item["module"], item["did"]) in FIRST_BATCH)
        and item.get("status", "unknown") == "unknown"
    ]
    counts: dict[str, int] = {}
    limited: list[dict[str, Any]] = []
    for item in selected:
        module = item["module"]
        counts[module] = counts.get(module, 0)
        if counts[module] >= args.max_per_module:
            continue
        limited.append(item)
        counts[module] += 1

    if not args.execute:
        print(f"Prepared {len(limited)} candidates. Add --execute to send read-only UDS service 22 requests.")
        return 0

    rows: list[dict[str, Any]] = []
    registry = load_json(Path(args.registry), {"generated_at": now_iso(), "metrics": {}})
    metrics = registry.setdefault("metrics", {})
    Path(args.jsonl).parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser, Path(args.jsonl).open("a", encoding="utf-8") as log:
        for item in limited:
            setup_elm(ser, args.protocol, item["header"])
            response = elm_command(ser, f"22{item['did']}", delay=0.25, timeout=4.0)
            status = classify(response, item["did"])
            payload = extract_payload(response.get("response", ""), item["did"]) if status == "positive" else []
            guesses = decode_candidates(item, payload) if status == "positive" else []
            payload_hex = " ".join(f"{b:02X}" for b in payload)
            item["status"] = "supported" if status == "positive" else status
            row = {
                "tested_at": now_iso(),
                **item,
                "status": status,
                "payload_hex": payload_hex,
                "decode_guesses": guesses,
                "raw_response": response.get("raw", ""),
                "elapsed_ms": response.get("elapsed_ms"),
            }
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            plausible = [guess for guess in guesses if guess.get("plausible") and guess.get("decoder") != "raw_hex"]
            if args.update_registry and status == "positive" and plausible:
                metrics[item["metric_key"]] = registry_entry(item, plausible[0], payload, response.get("raw", ""))

    if args.update_registry:
        registry["generated_at"] = now_iso()
        write_json(Path(args.registry), registry)
    if args.update_candidates:
        write_candidates(candidates_path, candidates)
    write_report(Path(args.report), rows)
    print(f"Tested {len(rows)} candidates")
    print(f"Wrote {args.jsonl}")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
