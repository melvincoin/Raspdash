from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial


ECUS = {
    "engine": {"request_header": "7E0", "response_header": "7E8"},
    "transmission": {"request_header": "7E1", "response_header": "7E9"},
}

IDENT_DIDS = ("F180", "F181", "F182", "F187", "F189", "F18A", "F190", "F1A0")
VIN_DIDS = {"F190"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_hex(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch in "0123456789ABCDEF")


def mask_vin(text: str) -> str:
    vin = re.sub(r"[^A-HJ-NPR-Z0-9]", "", text.upper())
    if len(vin) == 17:
        return f"{vin[:3]}***********{vin[-3:]}"
    return ""


def ascii_payload(compact: str, did: str) -> str:
    payload = uds_payload_bytes(compact, did)
    if not payload:
        return ""
    chars = []
    for value in payload:
        if 32 <= value <= 126:
            chars.append(chr(value))
    return "".join(chars).strip()


def uds_payload_bytes(compact: str, did: str) -> list[int]:
    frames: list[list[int]] = []
    for marker in re.finditer(r"7E[89][0-9A-F]", compact):
        chunk = compact[marker.start() + 3 :]
        next_marker = re.search(r"7E[89][0-9A-F]", chunk)
        if next_marker:
            chunk = chunk[: next_marker.start()]
        if len(chunk) >= 2:
            frames.append([int(chunk[i : i + 2], 16) for i in range(0, len(chunk) - 1, 2)])
    if not frames:
        return []

    data: list[int] = []
    for frame in frames:
        pci = frame[0]
        frame_type = pci >> 4
        if frame_type == 0:
            data.extend(frame[1 : 1 + (pci & 0x0F)])
        elif frame_type == 1 and len(frame) >= 2:
            total_len = ((pci & 0x0F) << 8) + frame[1]
            data.extend(frame[2:])
            data = data[:total_len]
        elif frame_type == 2:
            data.extend(frame[1:])

    marker_bytes = [0x62, int(did[:2], 16), int(did[2:], 16)]
    for index in range(0, max(0, len(data) - len(marker_bytes) + 1)):
        if data[index : index + len(marker_bytes)] == marker_bytes:
            payload = data[index + len(marker_bytes) :]
            return [byte for byte in payload if byte not in {0xAA}]
    return []


def read_until_prompt(ser: serial.Serial, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = ser.read(64)
        if chunk:
            chunks.append(chunk)
            if b">" in chunk:
                break
        else:
            time.sleep(0.02)
    return b"".join(chunks).decode("ascii", errors="replace")


def elm_command(ser: serial.Serial, command: str, delay: float = 0.2, timeout: float = 4.0) -> dict[str, Any]:
    started = time.monotonic()
    ser.reset_input_buffer()
    ser.write((command + "\r").encode("ascii"))
    ser.flush()
    time.sleep(delay)
    raw = read_until_prompt(ser, timeout)
    response = raw.replace(command, "").replace(">", "").replace("\r", "\n").strip()
    normalized = response.upper().replace(" ", "")
    status = "ok"
    if not raw:
        status = "no_response"
    elif "NODATA" in normalized or "UNABLETOCONNECT" in normalized:
        status = "no_response"
    elif "7F22" in compact_hex(response):
        status = "unsupported"
    elif "7F" in compact_hex(response):
        status = "negative_response"
    return {
        "command": command,
        "raw": raw,
        "response": response,
        "compact": compact_hex(response),
        "status": status,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def setup_elm(ser: serial.Serial, protocol: str, header: str) -> list[dict[str, Any]]:
    commands = [
        ("ATZ", 1.0, 3.0),
        ("ATE0", 0.2, 2.0),
        ("ATL0", 0.2, 2.0),
        ("ATS0", 0.2, 2.0),
        ("ATH1", 0.2, 2.0),
        ("ATCAF1", 0.2, 2.0),
        (f"ATSP{protocol}", 0.4, 3.0),
        (f"ATSH{header}", 0.2, 2.0),
    ]
    return [elm_command(ser, command, delay, timeout) for command, delay, timeout in commands]


def identify_module(ser: serial.Serial, name: str, protocol: str) -> dict[str, Any]:
    ecu = ECUS[name]
    result: dict[str, Any] = {
        "name": name,
        **ecu,
        "setup": setup_elm(ser, protocol, ecu["request_header"]),
        "session": elm_command(ser, "1003", delay=0.25, timeout=3.0),
        "identification": {},
    }
    for did in IDENT_DIDS:
        response = elm_command(ser, f"22{did}", delay=0.25, timeout=5.0)
        text = ascii_payload(response["compact"], did)
        result["identification"][did] = {
            "status": response["status"],
            "response": response["response"],
            "text": mask_vin(text) if did in VIN_DIDS else text,
            "vin_masked": mask_vin(text) if did in VIN_DIDS else "",
        }
    return result


def write_report(path: Path, data: dict[str, Any]) -> None:
    lines = [
        "# Module Identification",
        "",
        f"Generated: {data['generated_at']}",
        "",
        "| module | request | response | DID | status | decoded text |",
        "|---|---|---|---|---|---|",
    ]
    for module in data["modules"]:
        for did, item in module["identification"].items():
            text = ascii_payload(compact_hex(item.get("response", "")), did)
            if did in VIN_DIDS:
                text = mask_vin(text)
            lines.append(
                f"| {module['name']} | `{module['request_header']}` | `{module['response_header']}` | `{did}` | {item['status']} | `{text}` |"
            )
    lines.append("")
    lines.append("VIN is masked when present.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only UDS module identification.")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--protocol", default="6")
    parser.add_argument("--output", default="data/module_identification.json")
    parser.add_argument("--report", default="reports/module_identification.md")
    parser.add_argument("--from-json", default="")
    args = parser.parse_args()

    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        write_report(Path(args.report), data)
        print(f"Wrote {args.report}")
        return 0

    data = {
        "generated_at": now_iso(),
        "port": args.port,
        "baudrate": args.baudrate,
        "protocol": args.protocol,
        "modules": [],
    }
    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        for name in ("engine", "transmission"):
            data["modules"].append(identify_module(ser, name, args.protocol))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_report(Path(args.report), data)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
