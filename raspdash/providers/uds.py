from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import serial

from scripts.discovery_common import elm_command, setup_elm


@dataclass
class UdsEcu:
    name: str
    request_header: str
    response_header: str


class UdsReadOnlyProvider:
    name = "uds_read_only"

    def __init__(self, port: str, baudrate: int = 115200, protocol: str = "6") -> None:
        self.port = port
        self.baudrate = baudrate
        self.protocol = protocol

    def read_data_by_identifier(self, ecu: UdsEcu, did: str, timeout: float = 5.0) -> dict[str, Any]:
        clean_did = "".join(ch for ch in did.upper() if ch in "0123456789ABCDEF")
        if len(clean_did) != 4:
            return {"ok": False, "status": "invalid", "did": did, "error": "DID must be exactly 2 bytes"}

        with serial.Serial(self.port, self.baudrate, timeout=0.2, write_timeout=1) as ser:
            setup = setup_elm(ser, self.protocol, ecu.request_header)
            response = elm_command(ser, f"22{clean_did}", delay=0.25, timeout=timeout)

        return {
            "ok": response["status"] == "ok" and "62" in response["response"].upper().replace(" ", ""),
            "status": classify_uds_response(response["response"]),
            "ecu": ecu.__dict__,
            "service": "22",
            "did": clean_did,
            "setup": setup,
            "response": response,
        }


def classify_uds_response(response: str) -> str:
    compact = "".join(ch for ch in response.upper() if ch in "0123456789ABCDEF")
    if not compact:
        return "no_response"
    if "7F22" in compact:
        return "negative_response"
    if "62" in compact:
        return "works"
    if "NODATA" in response.upper().replace(" ", ""):
        return "no_response"
    return "unknown"
