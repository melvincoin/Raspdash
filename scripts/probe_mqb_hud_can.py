#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone

import serial


FRAME_RE = re.compile(r"(?:^|\s)([0-9A-F]{3})\s+((?:[0-9A-F]{2}\s*){1,8})(?:$|\r|\n)")


def command(handle: serial.Serial, value: str, timeout: float = 1.0) -> str:
    handle.reset_input_buffer()
    handle.write((value + "\r").encode("ascii"))
    handle.flush()
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = handle.read(256)
        if chunk:
            chunks.append(chunk)
            if b">" in chunk:
                break
        else:
            time.sleep(0.01)
    return b"".join(chunks).decode("ascii", errors="ignore")


def main() -> int:
    parser = argparse.ArgumentParser(description="Passively probe one MQB CAN broadcast ID through an ELM327-compatible adapter")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--can-id", default="397")
    parser.add_argument("--duration", type=float, default=5.0)
    args = parser.parse_args()
    can_id = args.can_id.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{3}", can_id):
        parser.error("--can-id must be a three-digit hexadecimal 11-bit CAN ID")

    with serial.Serial(args.port, args.baudrate, timeout=0.05, write_timeout=1.0) as handle:
        setup = {}
        for value, timeout in (("ATZ", 2.0), ("ATE0", 1.0), ("ATL1", 1.0), ("ATS1", 1.0), ("ATH1", 1.0), ("ATSP6", 1.5), ("ATCAF0", 1.0), (f"ATCRA{can_id}", 1.0)):
            setup[value] = command(handle, value, timeout).replace("\r", " ").replace("\n", " ").strip()

        handle.reset_input_buffer()
        handle.write(b"ATMA\r")
        handle.flush()
        deadline = time.monotonic() + max(1.0, args.duration)
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            chunk = handle.read(512)
            if chunk:
                chunks.append(chunk)
            else:
                time.sleep(0.01)
        handle.write(b"\r")
        handle.flush()
        time.sleep(0.2)
        chunks.append(handle.read(2048))
        # Clear ATCRA and all monitor state before releasing the serial port so
        # the normal dashboard provider can immediately receive ECU replies.
        cleanup = command(handle, "ATZ", 2.0).replace("\r", " ").replace("\n", " ").strip()

    raw = b"".join(chunks).decode("ascii", errors="ignore").upper()
    frames = []
    for match in FRAME_RE.finditer(raw):
        frame_id, payload = match.groups()
        if frame_id == can_id:
            frames.append({"can_id": frame_id, "data": " ".join(payload.split())})
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "can_id": can_id,
        "duration_seconds": args.duration,
        "setup": setup,
        "cleanup": cleanup,
        "frame_count": len(frames),
        "unique_payloads": sorted({frame["data"] for frame in frames}),
        "raw_tail": raw[-1000:],
    }, indent=2))
    return 0 if frames else 2


if __name__ == "__main__":
    raise SystemExit(main())
