from __future__ import annotations

from typing import Any

import serial
from serial.tools import list_ports

from raspdash.providers.base import VehicleData, VehicleProvider


HEX_V2_HINTS = ("hex", "ross-tech", "vcds", "usb serial", "ch340", "ftdi")
HEX_V2_IDS = {(0x0403, 0xFA24)}


class HexV2Provider(VehicleProvider):
    name = "hexv2"
    probe_baudrates = (115200, 38400, 9600)

    @staticmethod
    def detect_ports() -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        for port in list_ports.comports():
            haystack = " ".join(
                str(part or "")
                for part in (port.device, port.description, port.manufacturer, port.product)
            ).lower()
            usb_id = (port.vid, port.pid)
            if usb_id in HEX_V2_IDS or any(hint in haystack for hint in HEX_V2_HINTS):
                matches.append(
                    {
                        "device": port.device,
                        "description": port.description or "",
                        "manufacturer": port.manufacturer or "",
                        "product": port.product or "",
                        "vid": f"{port.vid:04x}" if port.vid is not None else "",
                        "pid": f"{port.pid:04x}" if port.pid is not None else "",
                        "serial_number": port.serial_number or "",
                    }
                )
        return matches

    def selected_port(self) -> str | None:
        configured = self.config.get("port", "auto")
        if configured and configured != "auto":
            return str(configured)
        ports = self.detect_ports()
        if not ports:
            return None
        return ports[0]["device"]

    def probe_serial_channel(self) -> dict[str, Any]:
        port = self.selected_port()
        if not port:
            return {
                "connected": False,
                "port": "",
                "status": "HEX USB adapter not detected",
                "baudrate": None,
            }

        errors: list[str] = []
        for baudrate in self.probe_baudrates:
            try:
                with serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=0.25,
                    write_timeout=0.25,
                    rtscts=False,
                    dsrdtr=False,
                ) as handle:
                    handle.dtr = False
                    handle.rts = False
                    handle.reset_input_buffer()
                    waiting = handle.in_waiting
                    sample = handle.read(min(waiting, 64)) if waiting else b""
                    return {
                        "connected": True,
                        "port": port,
                        "baudrate": baudrate,
                        "status": "HEX USB serial channel opened",
                        "sample_hex": sample.hex(" "),
                    }
            except serial.SerialException as exc:
                errors.append(f"{baudrate}: {exc}")

        return {
            "connected": False,
            "port": port,
            "baudrate": None,
            "status": "HEX USB serial channel could not be opened",
            "errors": errors,
        }

    def read(self) -> VehicleData:
        probe = self.probe_serial_channel()
        if not probe["connected"]:
            return VehicleData(
                provider=self.name,
                connected=False,
                status=probe["status"],
            )

        return VehicleData(
            provider=self.name,
            connected=True,
            status=(
                f"HEX USB serial channel open on {probe['port']}; "
                "this interface is not ELM/STN compatible. No vehicle requests sent."
            ),
        )

    def diagnostics(self) -> dict[str, Any]:
        return {"ports": self.detect_ports(), "probe": self.probe_serial_channel()}
