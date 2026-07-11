from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial


DEFAULT_AT_TESTS = [
    ("reset", "ATZ", 1.2, 3.0),
    ("identify", "ATI", 0.2, 2.0),
    ("device_description", "AT@1", 0.2, 2.0),
    ("device_identifier", "AT@2", 0.2, 2.0),
    ("echo_off", "ATE0", 0.2, 2.0),
    ("linefeeds_off", "ATL0", 0.2, 2.0),
    ("spaces_off", "ATS0", 0.2, 2.0),
    ("headers_on", "ATH1", 0.2, 2.0),
    ("auto_format_on", "ATCAF1", 0.2, 2.0),
    ("allow_long_messages", "ATAL", 0.2, 2.0),
    ("current_protocol_number", "ATDPN", 0.2, 2.0),
    ("current_protocol_name", "ATDP", 0.2, 2.0),
    ("adapter_voltage", "ATRV", 0.2, 2.0),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def command(ser: serial.Serial, value: str, delay: float, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        ser.reset_input_buffer()
        ser.write((value + "\r").encode("ascii"))
        ser.flush()
        time.sleep(delay)
        raw = read_until_prompt(ser, timeout)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        normalized = raw.replace(value, "").replace(">", "").replace("\r", "\n").strip()
        upper = normalized.upper().replace(" ", "")
        supported = bool(raw) and "?" not in upper and "ERROR" not in upper
        return {
            "command": value,
            "ok": bool(raw),
            "supported": supported,
            "raw": raw,
            "response": normalized,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        return {
            "command": value,
            "ok": False,
            "supported": False,
            "raw": "",
            "response": "",
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe ELM327 adapter capabilities without vehicle PID polling.")
    parser.add_argument("--port", default="/dev/rfcomm0")
    parser.add_argument("--baudrate", type=int, default=38400)
    parser.add_argument("--protocol", default="6", help="ELM protocol to set before logging protocol info; empty skips ATSP.")
    parser.add_argument("--header", default="7DF", help="CAN header to set for later scripts; empty skips ATSH.")
    parser.add_argument("--output", default="data/elm_capabilities.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "generated_at": now_iso(),
        "port": args.port,
        "baudrate": args.baudrate,
        "requested_protocol": args.protocol,
        "requested_header": args.header,
        "tests": {},
        "summary": {
            "adapter_present": False,
            "firmware": None,
            "protocol_number": None,
            "protocol_name": None,
            "voltage": None,
        },
    }

    with serial.Serial(args.port, args.baudrate, timeout=0.2, write_timeout=1) as ser:
        tests = list(DEFAULT_AT_TESTS)
        if args.protocol:
            tests.insert(10, ("set_protocol", f"ATSP{args.protocol}", 0.4, 3.0))
        if args.header:
            tests.insert(11, ("set_header", f"ATSH{args.header}", 0.2, 2.0))

        for name, value, delay, timeout in tests:
            result["tests"][name] = command(ser, value, delay, timeout)

    identify = result["tests"].get("identify", {})
    protocol_number = result["tests"].get("current_protocol_number", {})
    protocol_name = result["tests"].get("current_protocol_name", {})
    voltage = result["tests"].get("adapter_voltage", {})

    result["summary"]["adapter_present"] = bool(identify.get("ok"))
    result["summary"]["firmware"] = identify.get("response") or None
    result["summary"]["protocol_number"] = protocol_number.get("response") or None
    result["summary"]["protocol_name"] = protocol_name.get("response") or None
    result["summary"]["voltage"] = voltage.get("response") or None

    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
