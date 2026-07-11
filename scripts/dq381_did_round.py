from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import serial

from discovery_common import elm_command, now_iso, setup_elm, write_json


def parse_candidates(path: Path) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_candidates = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "candidates:":
            in_candidates = True
            continue
        if not in_candidates:
            continue
        if stripped.startswith("- "):
            if current:
                candidates.append(current)
            current = {}
            stripped = stripped[2:].strip()
        if current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = value.strip().strip('"').strip("'")
    if current:
        candidates.append(current)
    return candidates


def compact_hex(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch in "0123456789ABCDEF")


def classify(response: dict[str, Any], did: str) -> str:
    compact = compact_hex(response.get("response", ""))
    if "7F2231" in compact:
        return "unsupported"
    if "7F2278" in compact and "7F2231" not in compact:
        return "pending_only"
    if f"62{did}" in compact:
        return "works"
    if response.get("status") in {"no_response", "no_data", "unsupported", "stopped", "error"}:
        return str(response.get("status"))
    return "unknown"


def possible_temp_decode(response: dict[str, Any], did: str) -> str:
    compact = compact_hex(response.get("response", ""))
    marker = f"62{did}"
    index = compact.find(marker)
    if index < 0:
        return ""
    payload = compact[index + len(marker) :]
    if len(payload) < 2:
        return ""
    data = [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]
    guesses = [f"A-40={data[0] - 40}C"]
    if len(data) >= 2:
        raw16 = data[0] * 256 + data[1]
        guesses.append(f"u16/10={raw16 / 10:.1f}C")
        guesses.append(f"(u16-2731)/10={(raw16 - 2731) / 10:.1f}C")
    return ", ".join(guesses)


def write_report(path: Path, results: list[dict[str, Any]]) -> None:
    lines = [
        "# DQ381 DID Test Round",
        "",
        f"Generated: {now_iso()}",
        "",
        "| metric | DID | response | decoded_possible | status | next_action |",
        "|---|---|---|---|---|---|",
    ]
    for item in results:
        raw = str(item["response"].get("response", "")).replace("\n", "<br>")
        next_action = "stop" if item["status"] == "works" else "exclude for now"
        lines.append(
            f"| {item['metric']} | {item['did']} | `{raw}` | {item['decoded_possible'] or ''} | {item['status']} | {next_action} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Small read-only DQ381 DID candidate round.")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--candidates", default="config/vag_candidates.yaml")
    parser.add_argument("--output", default="data/dq381_did_test_round.json")
    parser.add_argument("--report", default="reports/dq381_did_test_round.md")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    candidates = parse_candidates(Path(args.candidates))[: args.limit]
    results: list[dict[str, Any]] = []

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        current_header = None
        for candidate in candidates:
            did = compact_hex(candidate["did"])
            header = compact_hex(candidate.get("header", "7E1"))
            if len(did) != 4:
                continue
            if header != current_header:
                setup_elm(ser, args.protocol, header)
                elm_command(ser, "1003", delay=0.25, timeout=3.0)
                current_header = header
            response = elm_command(ser, f"22{did}", delay=0.25, timeout=5.0)
            status = classify(response, did)
            results.append(
                {
                    **candidate,
                    "did": did,
                    "header": header,
                    "status": status,
                    "response": response,
                    "decoded_possible": possible_temp_decode(response, did),
                }
            )

    write_json(Path(args.output), {"generated_at": now_iso(), "results": results})
    write_report(Path(args.report), results)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
