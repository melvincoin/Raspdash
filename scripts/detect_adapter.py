from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from serial.tools import list_ports

from discovery_common import now_iso, write_json


def udev_info(device: str) -> dict[str, str]:
    try:
        output = subprocess.check_output(["udevadm", "info", "--query=property", "--name", device], text=True)
    except Exception:
        return {}
    result = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def detect() -> list[dict[str, Any]]:
    devices = []
    for port in list_ports.comports():
        if not (port.device.startswith("/dev/ttyUSB") or port.device.startswith("/dev/ttyACM")):
            continue
        props = udev_info(port.device)
        devices.append(
            {
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
                "vendor_id": f"{port.vid:04X}" if port.vid is not None else props.get("ID_VENDOR_ID"),
                "product_id": f"{port.pid:04X}" if port.pid is not None else props.get("ID_MODEL_ID"),
                "serial_number": port.serial_number or props.get("ID_SERIAL_SHORT"),
                "manufacturer": port.manufacturer or props.get("ID_VENDOR_FROM_DATABASE") or props.get("ID_VENDOR"),
                "product": port.product or props.get("ID_MODEL_FROM_DATABASE") or props.get("ID_MODEL"),
                "chipset": props.get("ID_USB_DRIVER") or props.get("ID_BUS"),
                "udev": props,
            }
        )
    return devices


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect USB serial OBD adapters.")
    parser.add_argument("--output", default="data/adapter_detection.json")
    args = parser.parse_args()
    result = {"generated_at": now_iso(), "adapters": detect()}
    write_json(Path(args.output), result)
    print(json.dumps(result, indent=2))
    return 0 if result["adapters"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
