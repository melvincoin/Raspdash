from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import serial

from raspdash.providers.base import VehicleData, VehicleProvider
from raspdash.services.acc_distance_logger import AccDistanceLogger


PROVEN_UDS_DIDS = {
    "engine": {"header": "7E0", "dids": ("11BD", "15B7", "F40B", "F433", "177D", "181D", "1763", "1766", "1767", "1768", "4F80", "4F81", "58D1", "113F")},
    "transmission": {"header": "7E1", "dids": ("2104", "028D", "380A", "3808", "3816", "381D")},
}
PROVEN_UDS_SEQUENCE = (
    ("engine", "7E0", "11BD"),
    ("engine", "7E0", "15B7"),
    ("engine", "7E0", "F40B"),
    ("engine", "7E0", "F433"),
    ("engine", "7E0", "177D"),
    ("engine", "7E0", "181D"),
    ("engine", "7E0", "1763"),
    ("engine", "7E0", "1766"),
    ("engine", "7E0", "1767"),
    ("engine", "7E0", "1768"),
    ("engine", "7E0", "4F80"),
    ("engine", "7E0", "4F81"),
    ("engine", "7E0", "58D1"),
    ("transmission", "7E1", "2104"),
    ("transmission", "7E1", "028D"),
    ("transmission", "7E1", "380A"),
    ("transmission", "7E1", "3808"),
    ("transmission", "7E1", "3816"),
    ("transmission", "7E1", "381D"),
)
RIDE_CANDIDATE_SEQUENCE = (
    ("engine", "7E0", "1627"),
    ("engine", "7E0", "1628"),
    ("engine", "7E0", "113F"),
    ("engine", "7E0", "16BD"),
    ("engine", "7E0", "16BA"),
    ("engine", "7E0", "16BB"),
    ("engine", "7E0", "4051"),
    ("engine", "7E0", "10EA"),
    ("engine", "7E0", "10EB"),
    ("engine", "7E0", "1715"),
    ("engine", "7E0", "1716"),
    ("engine", "7E0", "1717"),
    ("engine", "7E0", "1718"),
    ("cluster", "714", "2211"),
)
FAILED_DID_CACHE = Path(__file__).resolve().parents[2] / "data" / "obd_did_cache.json"
RIDE_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "ride_logs"
CANDIDATE_LOG_KEYS = {
    ("engine", "1627"), ("engine", "1628"), ("engine", "113F"), ("engine", "16BD"),
    ("engine", "16BA"), ("engine", "16BB"), ("engine", "4051"), ("engine", "10EA"), ("engine", "10EB"),
    ("engine", "1715"), ("engine", "1716"), ("engine", "1717"), ("engine", "1718"),
    ("acc", "102E"), ("acc", "1011"), ("acc", "1012"), ("acc", "1065"), ("acc", "1880"),
    ("cluster", "2211"),
}
RESPONSE_MODULES = {
    "7E8": "Engine",
    "7E9": "Transmission",
    "7EA": "Module 7EA",
    "7EB": "Module 7EB",
    "7EC": "Module 7EC",
    "7ED": "Module 7ED",
    "7EE": "Module 7EE",
    "7EF": "Module 7EF",
}


def _elm_command(ser: serial.Serial, command: str, delay: float = 0.01, timeout: float = 0.35) -> str:
    ser.reset_input_buffer()
    ser.write((command + "\r").encode("ascii"))
    ser.flush()
    time.sleep(delay)

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

    response = b"".join(chunks).decode("ascii", errors="ignore")
    if not response:
        raise serial.SerialException("ELM327 did not return data")
    if ">" not in response:
        cleaned = response.replace("\r", " ").replace("\n", " ").strip()
        raise serial.SerialException(f"ELM327 incomplete response: {cleaned or 'no prompt'}")
    return response.replace(command, "").replace(">", "").replace("\r", "\n").strip()


def _elm_pid(ser: serial.Serial, pid: str, timeout: float = 0.28) -> list[int] | None:
    response = _elm_command(ser, f"01{pid}", delay=0.01, timeout=timeout)
    normalized = response.upper().replace(" ", "")
    if "UNABLETOCONNECT" in normalized or "NODATA" in normalized or "STOPPED" in normalized:
        return None

    compact = "".join(ch for ch in response.upper() if ch in "0123456789ABCDEF")
    marker = f"41{pid}"
    index = compact.find(marker)
    if index < 0:
        return None

    payload = compact[index + len(marker) :]
    if len(payload) < 2:
        return None
    return [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]


def _decode_obd_dtc(high: int, low: int) -> str | None:
    if high == 0 and low == 0:
        return None
    systems = ("P", "C", "B", "U")
    return f"{systems[(high & 0xC0) >> 6]}{(high & 0x30) >> 4}{high & 0x0F:X}{(low & 0xF0) >> 4:X}{low & 0x0F:X}"


def _dtc_payloads_by_module(response: str, service: int) -> dict[str, list[int]]:
    payloads: dict[str, list[int]] = {}
    positive = 0x40 + service
    for line in response.upper().replace(" ", "").splitlines():
        compact = "".join(ch for ch in line if ch in "0123456789ABCDEF")
        if len(compact) < 10:
            continue
        header = compact[:3]
        if header not in RESPONSE_MODULES:
            continue
        data = [int(compact[i : i + 2], 16) for i in range(3, len(compact) - 1, 2)]
        if not data:
            continue
        pci = data[0]
        frame_type = pci >> 4
        if frame_type == 0:
            length = pci & 0x0F
            payload = data[1 : 1 + length]
        else:
            payload = data[1:]
        if not payload or payload[0] != positive:
            continue
        payloads.setdefault(header, []).extend(payload[1:])
    return payloads


def _read_obd_dtcs(ser: serial.Serial) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    status_by_mode = {"03": "confirmed", "07": "pending", "0A": "permanent"}
    _elm_command(ser, "ATSH7DF", timeout=0.3)
    for mode, status in status_by_mode.items():
        try:
            response = _elm_command(ser, mode, timeout=1.2)
        except serial.SerialException:
            continue
        normalized = response.upper().replace(" ", "")
        if "NODATA" in normalized or "UNABLETOCONNECT" in normalized or "STOPPED" in normalized:
            continue
        for header, payload in _dtc_payloads_by_module(response, int(mode, 16)).items():
            for index in range(0, len(payload) - 1, 2):
                code = _decode_obd_dtc(payload[index], payload[index + 1])
                if not code:
                    continue
                key = (RESPONSE_MODULES.get(header, header), code, status)
                if key in seen:
                    continue
                seen.add(key)
                alerts.append({"module": key[0], "code": code, "status": status})
    return alerts[:8]


def _elm_did(ser: serial.Serial, did: str, header: str, timeout: float = 1.0) -> list[int] | None:
    clean_did = "".join(ch for ch in did.upper() if ch in "0123456789ABCDEF")
    clean_header = "".join(ch for ch in header.upper() if ch in "0123456789ABCDEF")
    if len(clean_did) != 4 or len(clean_header) not in {3, 8}:
        return None

    _elm_command(ser, f"ATSH{clean_header}", timeout=0.3)
    response = _elm_command(ser, f"22{clean_did}", timeout=timeout)
    normalized = response.upper().replace(" ", "")
    if "UNABLETOCONNECT" in normalized or "NODATA" in normalized or "STOPPED" in normalized:
        return None

    payload = _extract_isotp_payload(response, clean_did)
    if payload is not None:
        return payload

    compact = "".join(ch for ch in response.upper() if ch in "0123456789ABCDEF")
    marker = f"62{clean_did}"
    index = compact.find(marker)
    if index < 0:
        return None
    payload = compact[index + len(marker) :]
    if len(payload) < 2:
        return None
    return [int(payload[i : i + 2], 16) for i in range(0, len(payload) - 1, 2)]


def _extract_isotp_payload(response: str, did: str) -> list[int] | None:
    frames: list[list[int]] = []
    for line in response.upper().replace(" ", "").splitlines():
        compact = "".join(ch for ch in line if ch in "0123456789ABCDEF")
        if len(compact) < 8 or not compact.startswith("7E8"):
            continue
        data = [int(compact[i : i + 2], 16) for i in range(3, len(compact) - 1, 2)]
        if data[:3] == [0x7F, 0x22, 0x78] or data[1:4] == [0x7F, 0x22, 0x78]:
            continue
        frames.append(data)

    assembled: list[int] = []
    expected_length: int | None = None
    for frame in frames:
        if not frame:
            continue
        pci = frame[0]
        frame_type = pci >> 4
        if frame_type == 0:
            expected_length = pci & 0x0F
            assembled = frame[1 : 1 + expected_length]
            break
        if frame_type == 1 and len(frame) >= 2:
            expected_length = ((pci & 0x0F) << 8) | frame[1]
            assembled = frame[2:]
            continue
        if frame_type == 2 and expected_length is not None:
            assembled.extend(frame[1:])

    if expected_length is None:
        return None
    assembled = assembled[:expected_length]
    marker = [0x62, int(did[:2], 16), int(did[2:], 16)]
    if assembled[:3] != marker:
        return None
    return assembled[3:]


def _u16_be(payload: list[int]) -> int | None:
    return ((payload[0] << 8) | payload[1]) if len(payload) >= 2 else None


def _u16_le(payload: list[int]) -> int | None:
    return ((payload[1] << 8) | payload[0]) if len(payload) >= 2 else None


def _plausible_temp(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= -39 or value > 180:
        return None
    return round(value, 1)


def _decode_u16_be_kelvin_10(payload: list[int]) -> float | None:
    raw = _u16_be(payload)
    return _plausible_temp((raw / 10) - 273.15 if raw is not None else None)


def _decode_u16_le_celsius(payload: list[int]) -> float | None:
    raw = _u16_le(payload)
    return _plausible_temp(float(raw) if raw is not None else None)


def _decode_u8_kpa(payload: list[int]) -> float | None:
    return float(payload[0]) if payload else None


def _decode_u16_be_bar_1000(payload: list[int]) -> float | None:
    raw = _u16_be(payload)
    if raw is None:
        return None
    value = raw / 1000
    return round(value, 3) if 0 <= value <= 20 else None


def _decode_u16_be_percent_10(payload: list[int]) -> float | None:
    raw = _u16_be(payload)
    if raw is None:
        return None
    value = raw / 10
    return round(value, 1) if 0 <= value <= 100 else None


def _decode_58d1_current_pct(payload: list[int]) -> float | None:
    if len(payload) < 10:
        return None
    raw = (payload[8] << 8) | payload[9]
    value = raw / 10
    return round(value, 1) if 0 <= value <= 100 else None


def _decode_58d1_warning(payload: list[int]) -> int | None:
    if len(payload) < 11:
        return None
    return payload[10] if payload[10] in {0, 1} else None


def _decode_u16_le_bar_10(payload: list[int]) -> float | None:
    raw = _u16_le(payload)
    if raw is None:
        return None
    value = raw / 10
    return round(value, 1) if 0 <= value <= 60 else None


def _decode_u16_le_rpm(payload: list[int]) -> float | None:
    raw = _u16_le(payload)
    return float(raw) if raw is not None and 0 <= raw <= 10000 else None


def _raw_hex(payload: list[int]) -> str | None:
    return " ".join(f"{byte:02X}" for byte in payload) if payload else None


def _value_or_previous(value: Any, previous: Any) -> Any:
    return previous if value is None else value


def _read_proven_uds(ser: serial.Serial, previous: VehicleData, targets: tuple[tuple[str, str, str], ...]) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    raw_values: dict[str, str] = {}
    engine_payloads: dict[str, list[int] | None] = {}
    transmission_payloads: dict[str, list[int] | None] = {}
    try:
        for module, header, did in targets:
            payload = _elm_did(ser, did, header, timeout=0.65)
            if payload:
                raw_values[f"{module}:{did}"] = _raw_hex(payload) or ""
            if module == "engine":
                engine_payloads[did] = payload
            elif module == "transmission":
                transmission_payloads[did] = payload
    except serial.SerialException:
        return values, raw_values

    values["oil_temp_c"] = _value_or_previous(_decode_u16_be_kelvin_10(engine_payloads.get("11BD") or []), previous.oil_temp_c)
    values["oil_pan_temp_c"] = _value_or_previous(_decode_u16_be_kelvin_10(engine_payloads.get("15B7") or []), previous.oil_pan_temp_c)
    values["absolute_intake_pressure_kpa"] = _value_or_previous(_decode_u8_kpa(engine_payloads.get("F40B") or []), previous.absolute_intake_pressure_kpa)
    values["ambient_air_pressure_kpa"] = _value_or_previous(_decode_u8_kpa(engine_payloads.get("F433") or []), previous.ambient_air_pressure_kpa)
    if values["absolute_intake_pressure_kpa"] is not None:
        values["absolute_intake_pressure_bar"] = round(values["absolute_intake_pressure_kpa"] / 100, 2)
    if values["ambient_air_pressure_kpa"] is not None:
        values["ambient_air_pressure_bar"] = round(values["ambient_air_pressure_kpa"] / 100, 2)
    values["engine_oil_pressure_actual_bar"] = _value_or_previous(_decode_u16_be_bar_1000(engine_payloads.get("177D") or []), previous.engine_oil_pressure_actual_bar)
    values["engine_oil_pressure_setpoint_bar"] = _value_or_previous(_decode_u16_be_bar_1000(engine_payloads.get("181D") or []), previous.engine_oil_pressure_setpoint_bar)
    oil_level_status = _raw_hex(engine_payloads.get("1763") or [])
    values["oil_level_status_raw"] = _value_or_previous(oil_level_status, previous.oil_level_status_raw)
    if oil_level_status is not None:
        values["oil_level_available"] = oil_level_status == "00 00"
    else:
        values["oil_level_available"] = previous.oil_level_available
    values["oil_level_method_1_pct"] = _value_or_previous(_decode_u16_be_percent_10(engine_payloads.get("1766") or []), previous.oil_level_method_1_pct)
    values["oil_level_method_2_pct"] = _value_or_previous(_decode_u16_be_percent_10(engine_payloads.get("1767") or []), previous.oil_level_method_2_pct)
    values["oil_level_method_3_pct"] = _value_or_previous(_decode_u16_be_percent_10(engine_payloads.get("1768") or []), previous.oil_level_method_3_pct)
    values["oil_level_max_relative_pct"] = _value_or_previous(_decode_u16_be_percent_10(engine_payloads.get("4F80") or []), previous.oil_level_max_relative_pct)
    values["oil_level_min_relative_pct"] = _value_or_previous(_decode_u16_be_percent_10(engine_payloads.get("4F81") or []), previous.oil_level_min_relative_pct)
    values["oil_level_current_pct"] = _value_or_previous(_decode_58d1_current_pct(engine_payloads.get("58D1") or []), previous.oil_level_current_pct)
    values["oil_level_warning_raw"] = _value_or_previous(_decode_58d1_warning(engine_payloads.get("58D1") or []), previous.oil_level_warning_raw)
    fuel_payload = engine_payloads.get("113F") or []
    if len(fuel_payload) >= 2:
        values["fuel_rate_lph"] = ((fuel_payload[0] << 8) | fuel_payload[1]) / 100
    values["act_intake_position_raw"] = _value_or_previous(_raw_hex(engine_payloads.get("16BA") or []), previous.act_intake_position_raw)
    values["act_exhaust_position_raw"] = _value_or_previous(_raw_hex(engine_payloads.get("16BB") or []), previous.act_exhaust_position_raw)
    if values["act_intake_position_raw"] is not None and values["act_exhaust_position_raw"] is not None:
        values["act_active"] = values["act_intake_position_raw"] == "0A" and values["act_exhaust_position_raw"] == "0A"
    values["transmission_fluid_temp_c"] = _value_or_previous(_decode_u16_le_celsius(transmission_payloads.get("2104") or []), previous.transmission_fluid_temp_c)
    values["dsg_temp_c"] = _value_or_previous(values["transmission_fluid_temp_c"], previous.dsg_temp_c)
    values["tcu_module_temp_c"] = _value_or_previous(_decode_u16_le_celsius(transmission_payloads.get("028D") or []), previous.tcu_module_temp_c)
    values["transmission_input_speed_rpm"] = _value_or_previous(_decode_u16_le_rpm(transmission_payloads.get("380A") or []), previous.transmission_input_speed_rpm)
    values["selector_lever_position_raw"] = _value_or_previous(_raw_hex(transmission_payloads.get("3808") or []), previous.selector_lever_position_raw)
    values["displayed_gear_raw"] = _value_or_previous(_raw_hex(transmission_payloads.get("3816") or []), previous.displayed_gear_raw)
    values["transmission_oil_pressure_actual_bar"] = _value_or_previous(_decode_u16_le_bar_10(transmission_payloads.get("381D") or []), previous.transmission_oil_pressure_actual_bar)
    absolute = values.get("absolute_intake_pressure_kpa")
    ambient = values.get("ambient_air_pressure_kpa")
    if absolute is not None and ambient is not None:
        values["boost_estimated_bar"] = round((absolute - ambient) / 100, 2)
    return values, raw_values


def _did_is_blocked(module: str, did: str) -> bool:
    cache = _load_did_cache()
    failed = cache.get("failed_or_unsupported_dids", {})
    return did.upper() in {item.upper() for item in failed.get(module, [])}


def _load_did_cache() -> dict[str, Any]:
    try:
        return json.loads(FAILED_DID_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_voltage(ser: serial.Serial) -> float | None:
    try:
        voltage_raw = _elm_command(ser, "ATRV")
    except serial.SerialException:
        return None
    for token in voltage_raw.replace("V", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


class Elm327Provider(VehicleProvider):
    name = "elm327"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._lock = threading.Lock()
        self._last_read = VehicleData(provider=self.name, connected=False, status="ELM327 not polled yet")
        self._last_read_at = 0.0
        self._ser: serial.Serial | None = None
        self._initialized = False
        self._slow_read_at = 0.0
        self._uds_read_at = 0.0
        self._act_read_at = 0.0
        self._uds_index = 0
        self._ride_log_at = 0.0
        self._candidate_raw: dict[str, str] = {}
        self.acc_distance_logger = AccDistanceLogger(RIDE_LOG_DIR / "acc_distance")
        self._ride_candidate_index = 0
        self._act_candidate_index = 0
        self._ride_started_at: float | None = None
        self._engine_off_since: float | None = None
        self._dtc_alerts: list[dict[str, str]] = []
        self._dtc_scan_done_for_start = False

    def close(self) -> None:
        if self._ser is not None and self._ser.is_open:
            self._ser.close()
        self._ser = None
        self._initialized = False

    def _ensure_serial(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            self._ser = serial.Serial(
                port=self.config["port"],
                baudrate=int(self.config.get("baudrate", 38400)),
                timeout=0.08,
                write_timeout=0.4,
            )
            self._initialized = False
        if not self._initialized:
            self._initialize_adapter(self._ser)
            self._initialized = True
        return self._ser

    def _initialize_adapter(self, ser: serial.Serial) -> None:
        _elm_command(ser, "ATE0", delay=0.05, timeout=0.8)
        _elm_command(ser, "ATL0", delay=0.05, timeout=0.8)
        _elm_command(ser, "ATS0", delay=0.05, timeout=0.8)
        _elm_command(ser, "ATH1", delay=0.05, timeout=0.8)
        _elm_command(ser, "ATCAF1", delay=0.05, timeout=0.8)
        _elm_command(ser, "ATST19", delay=0.05, timeout=0.8)
        protocol = str(self.config.get("protocol", "6")).strip() or "6"
        _elm_command(ser, f"ATSP{protocol}", delay=0.05, timeout=1.0)
        header = str(self.config.get("header", "7DF")).strip()
        if header:
            _elm_command(ser, f"ATSH{header}", delay=0.05, timeout=0.8)

    def _ride_window_active(self, rpm: float | None) -> bool:
        now = time.monotonic()
        if rpm is not None and rpm > 0:
            self._engine_off_since = None
            if self._ride_started_at is None:
                self._ride_started_at = now
                self._candidate_raw = {}
                self._dtc_scan_done_for_start = False
            duration = max(60.0, float(self.config.get("ride_log_duration", 900.0)))
            return now - self._ride_started_at < duration
        if self._engine_off_since is None:
            self._engine_off_since = now
        elif now - self._engine_off_since >= 60.0:
            self._ride_started_at = None
            self._candidate_raw = {}
            self._dtc_scan_done_for_start = False
        return False

    def _read_startup_dtcs(self, ser: serial.Serial, rpm: float | None) -> list[dict[str, str]]:
        if self.config.get("startup_dtc_scan", True) is not True:
            return self._dtc_alerts
        if rpm is None or rpm <= 250 or self._dtc_scan_done_for_start:
            return self._dtc_alerts
        self._dtc_scan_done_for_start = True
        self._dtc_alerts = _read_obd_dtcs(ser)
        return self._dtc_alerts

    def _append_ride_log(self, data: VehicleData, raw_updates: dict[str, str], ride_window_active: bool) -> None:
        if self.config.get("ride_logging", True) is not True:
            return
        self._candidate_raw.update(
            {
                key: value
                for key, value in raw_updates.items()
                if tuple(key.split(":", 1)) in CANDIDATE_LOG_KEYS
            }
        )
        if not ride_window_active:
            return
        now = time.monotonic()
        if now - self._ride_log_at < float(self.config.get("ride_log_interval", 1.0)):
            return
        timestamp = datetime.now(timezone.utc)
        record = {
            "timestamp": timestamp.isoformat(),
            "candidate_raw": dict(self._candidate_raw),
            "speed_kmh": data.speed_kmh,
            "rpm": data.rpm,
            "engine_load_pct": data.engine_load_pct,
            "throttle_pct": data.throttle_pct,
            "map_kpa": data.map_kpa,
            "barometric_pressure_kpa": data.barometric_pressure_kpa,
            "boost_bar": data.boost_bar,
            "oil_temp_c": data.oil_temp_c,
            "transmission_fluid_temp_c": data.transmission_fluid_temp_c,
            "engine_oil_pressure_actual_bar": data.engine_oil_pressure_actual_bar,
        }
        try:
            RIDE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = RIDE_LOG_DIR / f"ride-{timestamp.astimezone().date().isoformat()}.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            self._ride_log_at = now
        except OSError:
            pass

    def _poll_acc_distance(self, ser: serial.Serial, data: VehicleData, ride_window_active: bool) -> None:
        # The candidate module-13 DIDs are not reachable through this car's
        # diagnostic gateway. Keep the experimental logger opt-in so normal
        # rides do not spend serial bandwidth on guaranteed unsupported reads.
        if self.config.get("acc_distance_logging", False) is not True:
            self.acc_distance_logger.stop_ride()
            return
        if not ride_window_active:
            self.acc_distance_logger.stop_ride()
            return
        self.acc_distance_logger.start_ride()
        did = self.acc_distance_logger.next_did()
        if did is None:
            return
        try:
            payload = _elm_did(ser, did, "757", timeout=0.4)
            status = "ok" if payload is not None else "unsupported"
        except serial.SerialException:
            payload = None
            status = "timeout"
        self.acc_distance_logger.record(did, payload, status, {
            "speed_kmh": data.speed_kmh,
            "rpm": data.rpm,
            "engine_load": data.engine_load_pct,
            "throttle": data.throttle_pct,
            "map_bar": round(data.map_kpa / 100, 2) if data.map_kpa is not None else None,
            "boost_bar": data.boost_bar,
        })

    def add_acc_marker(self, label: str) -> bool:
        return self.acc_distance_logger.marker(label)

    def acc_log_status(self) -> dict[str, Any]:
        return self.acc_distance_logger.status()

    def _read_fast(self) -> VehicleData:
        ser = self._ensure_serial()
        header = str(self.config.get("header", "7DF")).strip()
        if header:
            _elm_command(ser, f"ATSH{header}", delay=0.01, timeout=0.35)

        previous = self._last_read
        rpm = _elm_pid(ser, "0C")
        speed = _elm_pid(ser, "0D")
        throttle = _elm_pid(ser, "11")
        load = _elm_pid(ser, "04")
        map_pressure = _elm_pid(ser, "0B")

        read_slow = time.monotonic() - self._slow_read_at >= float(self.config.get("slow_poll_interval", 1.0))
        read_uds = time.monotonic() - self._uds_read_at >= float(self.config.get("uds_poll_interval", 2.0))
        coolant = intake = barometric = None
        voltage = previous.battery_voltage_v
        if read_slow:
            coolant = _elm_pid(ser, "05")
            intake = _elm_pid(ser, "0F")
            barometric = _elm_pid(ser, "33")
            voltage = _read_voltage(ser)
            self._slow_read_at = time.monotonic()

        map_kpa = map_pressure[0] if map_pressure else None
        baro_kpa = barometric[0] if barometric else previous.barometric_pressure_kpa
        rpm_value = (((rpm[0] * 256) + rpm[1]) / 4) if rpm and len(rpm) >= 2 else None
        speed_value = speed[0] if speed else None
        fast_act_active: bool | None = None
        fast_act_raw: str | None = None
        if rpm_value is not None and rpm_value > 250 and time.monotonic() - self._act_read_at >= 0.5:
            try:
                act_payload = _elm_did(ser, "16BA", "7E0", timeout=0.25)
                fast_act_raw = _raw_hex(act_payload or [])
                if fast_act_raw is not None:
                    fast_act_active = fast_act_raw == "0A"
            except serial.SerialException:
                pass
            self._act_read_at = time.monotonic()
        ride_window_active = self._ride_window_active(rpm_value)
        dtc_alerts = self._read_startup_dtcs(ser, rpm_value)
        uds_values: dict[str, Any] = {}
        raw_updates: dict[str, str] = {}
        if read_uds and self.config.get("enable_proven_uds", True) is True:
            batch_size = max(1, int(self.config.get("uds_batch_size", 2)))
            if ride_window_active:
                batch_size = max(1, batch_size - 1)
            targets = tuple(PROVEN_UDS_SEQUENCE[(self._uds_index + index) % len(PROVEN_UDS_SEQUENCE)] for index in range(batch_size))
            self._uds_index = (self._uds_index + batch_size) % len(PROVEN_UDS_SEQUENCE)
            if ride_window_active:
                targets += (RIDE_CANDIDATE_SEQUENCE[self._ride_candidate_index],)
                self._ride_candidate_index = (self._ride_candidate_index + 1) % len(RIDE_CANDIDATE_SEQUENCE)
            if rpm_value is not None and rpm_value > 250:
                act_targets = (("engine", "7E0", "16BB"),)
                for act_target in act_targets:
                    if act_target not in targets:
                        targets += (act_target,)
            if rpm_value is not None and rpm_value > 250 and not any(did == "113F" for _module, _header, did in targets):
                targets += (("engine", "7E0", "113F"),)
            uds_values, raw_updates = _read_proven_uds(ser, previous, targets)
            self._uds_read_at = time.monotonic()

        absolute_kpa = uds_values.get("absolute_intake_pressure_kpa")
        ambient_kpa = uds_values.get("ambient_air_pressure_kpa")
        if absolute_kpa is None:
            absolute_kpa = map_kpa
        if ambient_kpa is None:
            ambient_kpa = baro_kpa
        boost_estimated_bar = uds_values.get("boost_estimated_bar")
        if boost_estimated_bar is None and absolute_kpa is not None and ambient_kpa is not None:
            boost_estimated_bar = round((absolute_kpa - ambient_kpa) / 100, 2)
        boost_bar = max(0, boost_estimated_bar) if boost_estimated_bar is not None else previous.boost_bar
        fuel_rate_lph = uds_values.get("fuel_rate_lph", previous.fuel_rate_lph)
        fuel_consumption = (
            round(fuel_rate_lph * 100 / speed_value, 1)
            if fuel_rate_lph is not None and speed_value is not None and speed_value >= 3
            else None
        )
        connected_values = (rpm, speed, coolant, intake, throttle, load, map_pressure, barometric)
        result = VehicleData(
            provider="elm327",
            connected=any(value is not None for value in connected_values) or bool(uds_values),
            oil_temp_c=uds_values.get("oil_temp_c", previous.oil_temp_c),
            oil_pan_temp_c=uds_values.get("oil_pan_temp_c", previous.oil_pan_temp_c),
            dsg_temp_c=uds_values.get("dsg_temp_c", previous.dsg_temp_c),
            transmission_fluid_temp_c=uds_values.get("transmission_fluid_temp_c", previous.transmission_fluid_temp_c),
            tcu_module_temp_c=uds_values.get("tcu_module_temp_c", previous.tcu_module_temp_c),
            transmission_input_speed_rpm=uds_values.get("transmission_input_speed_rpm", previous.transmission_input_speed_rpm),
            selector_lever_position_raw=uds_values.get("selector_lever_position_raw", previous.selector_lever_position_raw),
            displayed_gear_raw=uds_values.get("displayed_gear_raw", previous.displayed_gear_raw),
            absolute_intake_pressure_kpa=absolute_kpa,
            ambient_air_pressure_kpa=ambient_kpa,
            absolute_intake_pressure_bar=round(absolute_kpa / 100, 2) if absolute_kpa is not None else previous.absolute_intake_pressure_bar,
            ambient_air_pressure_bar=round(ambient_kpa / 100, 2) if ambient_kpa is not None else previous.ambient_air_pressure_bar,
            boost_estimated_bar=boost_estimated_bar,
            engine_oil_pressure_actual_bar=uds_values.get("engine_oil_pressure_actual_bar", previous.engine_oil_pressure_actual_bar),
            engine_oil_pressure_setpoint_bar=uds_values.get("engine_oil_pressure_setpoint_bar", previous.engine_oil_pressure_setpoint_bar),
            transmission_oil_pressure_actual_bar=uds_values.get("transmission_oil_pressure_actual_bar", previous.transmission_oil_pressure_actual_bar),
            oil_level_available=uds_values.get("oil_level_available", previous.oil_level_available),
            oil_level_status_raw=uds_values.get("oil_level_status_raw", previous.oil_level_status_raw),
            oil_level_method_1_pct=uds_values.get("oil_level_method_1_pct", previous.oil_level_method_1_pct),
            oil_level_method_2_pct=uds_values.get("oil_level_method_2_pct", previous.oil_level_method_2_pct),
            oil_level_method_3_pct=uds_values.get("oil_level_method_3_pct", previous.oil_level_method_3_pct),
            oil_level_max_relative_pct=uds_values.get("oil_level_max_relative_pct", previous.oil_level_max_relative_pct),
            oil_level_min_relative_pct=uds_values.get("oil_level_min_relative_pct", previous.oil_level_min_relative_pct),
            oil_level_current_pct=uds_values.get("oil_level_current_pct", previous.oil_level_current_pct),
            oil_level_warning_raw=uds_values.get("oil_level_warning_raw", previous.oil_level_warning_raw),
            battery_voltage_v=voltage,
            coolant_temp_c=(coolant[0] - 40) if coolant else previous.coolant_temp_c,
            intake_temp_c=(intake[0] - 40) if intake else previous.intake_temp_c,
            boost_bar=boost_bar,
            map_kpa=absolute_kpa,
            barometric_pressure_kpa=ambient_kpa,
            rpm=rpm_value,
            speed_kmh=speed_value,
            throttle_pct=(throttle[0] * 100 / 255) if throttle else None,
            engine_load_pct=(load[0] * 100 / 255) if load else None,
            fuel_rate_lph=fuel_rate_lph,
            fuel_consumption_l_per_100km=fuel_consumption,
            act_active=False if rpm_value is not None and rpm_value <= 250 else (fast_act_active if fast_act_active is not None else uds_values.get("act_active", previous.act_active)),
            act_intake_position_raw=fast_act_raw or uds_values.get("act_intake_position_raw", previous.act_intake_position_raw),
            act_exhaust_position_raw=uds_values.get("act_exhaust_position_raw", previous.act_exhaust_position_raw),
            dtc_alerts=dtc_alerts,
            status="ELM327 fast OBD-II polling active"
            if any(value is not None for value in connected_values)
            else "ELM327 adapter connected, but ECU returned no OBD-II data",
        )
        self._append_ride_log(result, raw_updates, ride_window_active)
        if read_uds:
            self._poll_acc_distance(ser, result, ride_window_active)
        return result

    def read(self) -> VehicleData:
        if not self.config.get("port"):
            return VehicleData(
                provider=self.name,
                connected=False,
                status="ELM327 Bluetooth serial port not configured",
            )

        if self.config.get("allow_requests") is not True:
            return VehicleData(
                provider=self.name,
                connected=False,
                status="ELM327 configured; OBD requests disabled until explicitly approved",
            )

        if time.monotonic() - self._last_read_at < float(self.config.get("min_poll_interval", 0.05)):
            return self._last_read

        if not self._lock.acquire(blocking=False):
            return self._last_read

        try:
            self._last_read = self._read_fast()
            self._last_read_at = time.monotonic()
            return self._last_read
        except Exception as exc:
            self.close()
            self._last_read = VehicleData(provider=self.name, connected=False, status=str(exc))
            self._last_read_at = time.monotonic()
            return self._last_read
        finally:
            self._lock.release()
