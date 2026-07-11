from __future__ import annotations

import os
import signal
import shutil
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import serial
from serial.tools import list_ports
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_sock import Sock
from werkzeug.utils import secure_filename

from raspdash.config_obd_parameters import OBD_PARAMETERS as PARAMETERS, PROVIDER_PARAMETERS
from raspdash.config import ROOT, load_config, save_config
from raspdash.middleware.error_handler import register_error_handlers
from raspdash.providers import create_provider
from raspdash.providers.hexv2 import HexV2Provider
from raspdash.routes import register_api_routes
from raspdash.widget_themes import WIDGET_THEMES


sock = Sock()
UPLOAD_ROOT = ROOT / "raspdash" / "static" / "uploads"
SPLASH_DIR = UPLOAD_ROOT / "splash"
BACKGROUND_DIR = UPLOAD_ROOT / "backgrounds"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_provider_lock = threading.Lock()
_provider_name = ""
_provider = None

def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "raspdash-local"
    sock.init_app(app)
    ensure_asset_dirs()
    ensure_default_assets()
    register_error_handlers(app)
    register_api_routes(app)
    register_routes(app)
    return app


def ensure_asset_dirs() -> None:
    SPLASH_DIR.mkdir(parents=True, exist_ok=True)
    BACKGROUND_DIR.mkdir(parents=True, exist_ok=True)


def ensure_default_assets() -> None:
    source = ROOT / "Boot splash.jpg"
    if source.exists():
        target = SPLASH_DIR / "boot-splash.jpg"
        if not target.exists():
            shutil.copyfile(source, target)


def register_routes(app: Flask) -> None:
    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", config=load_config(), asset_version=int(time.time()))

    @app.get("/splash")
    def splash():
        return render_template("splash.html", config=load_config())

    @app.get("/admin")
    def admin():
        return render_template("admin.html", config=load_config(), assets=list_assets(), asset_version=int(time.time()))

    @app.get("/api/health")
    def health():
        config = load_config()
        return jsonify(
            {
                "ok": True,
                "provider": config["obd"]["provider"],
                "assets": list_assets(),
            }
        )

    @app.get("/api/system/status")
    def system_status():
        return jsonify(read_system_status())

    @app.post("/api/display/ready")
    def display_ready():
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            return jsonify({"ok": False, "error": "Local display control only"}), 403
        log_path = Path("/tmp/raspdash-kiosk.log")
        pid_path = Path("/tmp/raspdash-cover.pid")

        def kiosk_log(message: str) -> None:
            try:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} backend: {message}\n")
            except OSError:
                pass

        kiosk_log("display ready received")
        cover_removed = False
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="ascii").strip())
                os.kill(pid, signal.SIGTERM)
                cover_removed = True
                kiosk_log(f"cover remove requested pid={pid}")
            except (OSError, ValueError) as exc:
                kiosk_log(f"cover already gone or invalid pid: {exc}")
            try:
                pid_path.unlink()
            except OSError:
                pass
        else:
            kiosk_log("cover pid missing")
        return jsonify({"ok": True, "cover_removed": cover_removed})

    @app.get("/api/config")
    def get_config():
        return jsonify(load_config())

    @app.get("/api/capabilities")
    def capabilities():
        config = load_config()
        provider = request.args.get("provider", config["obd"]["provider"])
        keys = PROVIDER_PARAMETERS.get(provider, PROVIDER_PARAMETERS["simulated"])
        return jsonify(
            {
                "provider": provider,
                "parameters": [{"key": key, **PARAMETERS[key]} for key in keys],
                "providers": {
                    "simulated": "Simulator",
                    "hexv2": "HEX-V2 USB",
                    "elm327": "ELM327 / vLinker USB",
                },
            }
        )

    @app.get("/api/themes")
    def themes():
        return jsonify({"ok": True, "themes": list(WIDGET_THEMES.values())})

    @app.post("/api/config")
    def update_config():
        payload: dict[str, Any] = request.get_json(force=True)
        save_config(payload)
        reset_provider()
        return jsonify({"ok": True, "config": payload})

    @app.get("/api/vehicle")
    def vehicle_snapshot():
        return jsonify(get_provider().read().to_dict())

    @app.route("/api/log/marker", methods=["GET", "POST"])
    def add_log_marker():
        allowed = {"voorligger", "dicht_op_voorligger", "acc_aan", "acc_uit", "front_assist_vermoeden"}
        payload = request.get_json(silent=True) or {}
        label = str(payload.get("label") or request.args.get("label") or "").strip().lower()
        if label not in allowed:
            return jsonify({"ok": False, "error": "Onbekend markerlabel", "allowed": sorted(allowed)}), 400
        provider = get_provider()
        if not hasattr(provider, "add_acc_marker"):
            return jsonify({"ok": False, "error": "ACC-logger is niet beschikbaar"}), 409
        written = provider.add_acc_marker(label)
        return jsonify({"ok": written, "label": label}), 200 if written else 409

    @app.get("/api/log/acc/status")
    def acc_log_status():
        provider = get_provider()
        status = provider.acc_log_status() if hasattr(provider, "acc_log_status") else {"active": False}
        return jsonify({"ok": True, **status})

    @app.get("/api/obd/hexv2")
    def hexv2_detection():
        return jsonify({"ports": HexV2Provider.detect_ports()})

    @app.get("/api/obd/elm327")
    def elm327_detection():
        return jsonify({"ports": detect_elm327_ports()})

    @app.post("/api/upload/<asset_type>")
    def upload_asset(asset_type: str):
        if asset_type not in {"splash", "backgrounds"}:
            return jsonify({"ok": False, "error": "Unknown asset type"}), 400
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        filename = secure_filename(file.filename or "")
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return jsonify({"ok": False, "error": "Unsupported file type"}), 400

        target_dir = SPLASH_DIR if asset_type == "splash" else BACKGROUND_DIR
        file.save(target_dir / filename)
        config = load_config()
        if asset_type == "backgrounds":
            config["display"]["background"] = filename
        elif asset_type == "splash":
            config["display"]["splash"] = filename
        save_config(config)
        return redirect(url_for("admin"))

    @app.get("/uploads/<asset_type>/<path:filename>")
    def uploaded_file(asset_type: str, filename: str):
        if asset_type not in {"splash", "backgrounds"}:
            return jsonify({"ok": False, "error": "Unknown asset type"}), 400
        target_dir = SPLASH_DIR if asset_type == "splash" else BACKGROUND_DIR
        return send_from_directory(target_dir, filename)

    @sock.route("/ws/vehicle")
    def vehicle_stream(ws):
        # Avoid parsing config.json on every frame; on a Pi this otherwise
        # causes needless SD-card I/O. Refresh infrequently so an admin change
        # still takes effect without reconnecting the dashboard.
        stream_interval = max(0.05, min(1.0, float(load_config()["obd"].get("vehicle_stream_interval", 0.25))))
        interval_refresh_at = time.monotonic() + 5.0
        while True:
            try:
                payload = get_provider().read().to_dict()
            except Exception as exc:
                payload = {
                    "oil_temp_c": None,
                    "dsg_temp_c": None,
                    "battery_voltage_v": None,
                    "provider": "error",
                    "connected": False,
                    "status": str(exc),
                }
            ws.send(json.dumps(payload))
            if time.monotonic() >= interval_refresh_at:
                stream_interval = max(0.05, min(1.0, float(load_config()["obd"].get("vehicle_stream_interval", 0.25))))
                interval_refresh_at = time.monotonic() + 5.0
            time.sleep(stream_interval)


def list_assets() -> dict[str, list[str]]:
    return {
        "splash": sorted(path.name for path in SPLASH_DIR.iterdir() if path.suffix.lower() in ALLOWED_EXTENSIONS),
        "backgrounds": [
            "carbon-pattern",
            "dark-gray",
            "vw-blue",
            *sorted(path.name for path in BACKGROUND_DIR.iterdir() if path.suffix.lower() in ALLOWED_EXTENSIONS),
        ],
    }


def detect_elm327_ports() -> list[dict[str, Any]]:
    ports: list[dict[str, Any]] = []
    for port in list_ports.comports():
        if not (port.device.startswith("/dev/ttyUSB") or port.device.startswith("/dev/ttyACM") or port.device.startswith("/dev/rfcomm")):
            continue
        item: dict[str, Any] = {
            "device": port.device,
            "description": port.description or "",
            "manufacturer": port.manufacturer or "",
            "product": port.product or "",
            "serial_number": port.serial_number or "",
            "vid": f"{port.vid:04x}" if port.vid is not None else "",
            "pid": f"{port.pid:04x}" if port.pid is not None else "",
            "adapter_present": False,
            "firmware": "",
            "voltage": "",
            "recommended": False,
        }
        probe = probe_elm327_port(port.device)
        item.update(probe)
        haystack = " ".join(str(item.get(key, "")) for key in ("description", "manufacturer", "product", "firmware")).lower()
        item["recommended"] = item["adapter_present"] and any(token in haystack for token in ("elm", "vlinker", "vgate", "obd"))
        ports.append(item)
    return sorted(ports, key=lambda item: (not item["recommended"], item["device"]))


def probe_elm327_port(device: str) -> dict[str, Any]:
    for baudrate in (115200, 38400):
        try:
            with serial.Serial(device, baudrate=baudrate, timeout=0.2, write_timeout=1) as handle:
                firmware = elm_at_command(handle, "ATI", delay=0.2, timeout=2.0)
                voltage = elm_at_command(handle, "ATRV", delay=0.2, timeout=2.0)
                return {
                    "adapter_present": bool(firmware),
                    "baudrate": baudrate,
                    "firmware": firmware,
                    "voltage": voltage,
                }
        except serial.SerialException as exc:
            last_error = str(exc)
    return {"adapter_present": False, "baudrate": None, "error": locals().get("last_error", "No response")}


def elm_at_command(handle: serial.Serial, command: str, delay: float, timeout: float) -> str:
    handle.reset_input_buffer()
    handle.write((command + "\r").encode("ascii"))
    handle.flush()
    time.sleep(delay)
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = handle.read(64)
        if chunk:
            chunks.append(chunk)
            if b">" in chunk:
                break
        else:
            time.sleep(0.02)
    return b"".join(chunks).decode("ascii", errors="ignore").replace(command, "").replace(">", "").replace("\r", "\n").strip()


def run_status_command(command: list[str], timeout: float = 1.0) -> str:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip()


def parse_throttled(raw: str) -> dict[str, Any]:
    value_text = raw.split("=", 1)[1] if "=" in raw else raw
    try:
        value = int(value_text, 16)
    except ValueError:
        value = 0
    flags = {
        "undervoltage_now": bool(value & 0x1),
        "frequency_capped_now": bool(value & 0x2),
        "throttled_now": bool(value & 0x4),
        "soft_temp_limit_now": bool(value & 0x8),
        "undervoltage_seen": bool(value & 0x10000),
        "frequency_capped_seen": bool(value & 0x20000),
        "throttled_seen": bool(value & 0x40000),
        "soft_temp_limit_seen": bool(value & 0x80000),
    }
    ok = not any(flags.values())
    return {"raw": raw or "unavailable", "value": value, "hex": f"0x{value:X}", "ok": ok, **flags}


def read_system_status() -> dict[str, Any]:
    temp_raw = run_status_command(["vcgencmd", "measure_temp"])
    temp_c = None
    if "=" in temp_raw:
        try:
            temp_c = float(temp_raw.split("=", 1)[1].replace("'C", ""))
        except ValueError:
            temp_c = None
    throttled = parse_throttled(run_status_command(["vcgencmd", "get_throttled"]))
    display_raw = run_status_command(["vcgencmd", "display_power"])
    uptime_seconds = None
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError):
        pass
    load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
    return {
        "ok": throttled["ok"],
        "temperature_c": temp_c,
        "temperature_raw": temp_raw or "unavailable",
        "throttled": throttled,
        "display_power": display_raw or "unavailable",
        "uptime_seconds": uptime_seconds,
        "load_average": {"1m": load[0], "5m": load[1], "15m": load[2]},
        "checked_at": time.time(),
    }


def get_provider():
    global _provider, _provider_name
    with _provider_lock:
        # Configuration updates call reset_provider(). Once constructed, the
        # provider already owns its OBD configuration. Re-reading config.json
        # for every sample only adds latency and SD-card traffic.
        if _provider is None:
            config = load_config()
            name = config["obd"]["provider"]
            provider_config = config["obd"].get(name, {})
            _provider = create_provider(name, provider_config)
            _provider_name = name
        return _provider


def reset_provider() -> None:
    global _provider, _provider_name
    with _provider_lock:
        if _provider is not None:
            _provider.close()
        _provider = None
        _provider_name = ""
