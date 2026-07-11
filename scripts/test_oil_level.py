from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import serial

from discovery_common import elm_command, now_iso, setup_elm


DIDS = {
    "11BA": "Oil fill level",
    "1763": "Bit string for status of oil level",
    "1766": "Engine oil level, test method 1",
    "1767": "Engine oil level, test method 2",
    "1768": "Engine oil level, test method 3",
    "2287": "Oil level, amount added MIN to MAX",
    "22CA": "Oil level, minimum value, compensated",
    "4F80": "Oil level, max. value, relative",
    "4F81": "Oil level, min. value, relative",
    "58D1": "Engine oil level, current value",
}


def compact_hex(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch in "0123456789ABCDEF")


def classify(response: dict[str, Any], did: str) -> str:
    compact = compact_hex(response.get("response", ""))
    if f"62{did}" in compact:
        return "positive"
    if "7F2231" in compact:
        return "unsupported"
    if "7F2278" in compact:
        return "pending_no_final"
    return response.get("status", "unknown")


def payload(response: dict[str, Any], did: str) -> list[int]:
    compact = compact_hex(response.get("response", ""))
    marker = f"62{did}"
    index = compact.find(marker)
    if index < 0:
        return []
    data = compact[index + len(marker) :]
    return [int(data[i : i + 2], 16) for i in range(0, len(data) - 1, 2)]


def u16_be(data: list[int]) -> int | None:
    return ((data[0] << 8) | data[1]) if len(data) >= 2 else None


def u16_le(data: list[int]) -> int | None:
    return ((data[1] << 8) | data[0]) if len(data) >= 2 else None


def u32_be(data: list[int]) -> int | None:
    return ((data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]) if len(data) >= 4 else None


def decode_guesses(data: list[int]) -> list[dict[str, Any]]:
    if not data:
        return []
    guesses: list[dict[str, Any]] = [{"decoder": "raw_hex", "value": " ".join(f"{byte:02X}" for byte in data)}]
    if len(data) == 1:
        guesses.append({"decoder": "u8", "value": data[0]})
        guesses.append({"decoder": "u8_percent", "value": round(data[0] * 100 / 255, 1)})
    be16 = u16_be(data)
    le16 = u16_le(data)
    be32 = u32_be(data)
    if be16 is not None:
        guesses.extend(
            [
                {"decoder": "u16_be", "value": be16},
                {"decoder": "u16_be/10", "value": be16 / 10},
                {"decoder": "u16_be_percent", "value": round(be16 * 100 / 65535, 2)},
            ]
        )
    if le16 is not None:
        guesses.extend(
            [
                {"decoder": "u16_le", "value": le16},
                {"decoder": "u16_le/10", "value": le16 / 10},
                {"decoder": "u16_le_percent", "value": round(le16 * 100 / 65535, 2)},
            ]
        )
    if be32 is not None:
        guesses.append({"decoder": "u32_be", "value": be32})
    return guesses


def write_report(path: Path, phase: str, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Oil Level UDS Test",
        "",
        f"Generated: {now_iso()}",
        f"Phase: `{phase}`",
        "",
        "Header: `7E0`, service: `22`, read-only.",
        "",
        "| DID | label | status | raw payload | decode candidates |",
        "|---:|---|---|---|---|",
    ]
    for row in rows:
        decodes = ", ".join(f"{item['decoder']}={item['value']}" for item in row["decode_guesses"][:8]) or "-"
        lines.append(f"| `{row['did']}` | {row['label']} | {row['status']} | `{row['payload_hex']}` | {decodes} |")
    lines.extend(
        [
            "",
            "## Voorlopige metrics",
            "",
            "- `oil_level_available`: true als minimaal een oil-level DID positief antwoordt.",
            "- `oil_level_status`: alleen raw/status, geen literwaarde.",
            "- `oil_level_relative_raw`: alleen raw/percent-kandidaat zolang schaal onbekend is.",
            "",
            "Geen dashboardactivatie en geen fake liters. Vergelijking contact aan / motor loopt / 5 minuten na motor uit vraagt meerdere fases met dezelfde script-run en `--phase` label.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only engine oil level UDS test.")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--phase", default="current")
    parser.add_argument("--jsonl", default="data/oil_level_test.jsonl")
    parser.add_argument("--report", default="reports/oil_level_test.md")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if not args.execute:
        print("Prepared oil level test. Add --execute to send read-only UDS requests.")
        return 0

    rows: list[dict[str, Any]] = []
    Path(args.jsonl).parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser, Path(args.jsonl).open("a", encoding="utf-8") as log:
        setup_elm(ser, args.protocol, "7E0")
        for did, label in DIDS.items():
            response = elm_command(ser, f"22{did}", delay=0.25, timeout=4.0)
            status = classify(response, did)
            data = payload(response, did) if status == "positive" else []
            row = {
                "tested_at": now_iso(),
                "phase": args.phase,
                "module": "engine",
                "header": "7E0",
                "did": did,
                "label": label,
                "status": status,
                "payload_hex": " ".join(f"{byte:02X}" for byte in data),
                "decode_guesses": decode_guesses(data),
                "raw_response": response.get("raw", ""),
                "elapsed_ms": response.get("elapsed_ms"),
            }
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_report(Path(args.report), args.phase, rows)
    print(f"Tested {len(rows)} oil-level DIDs")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
