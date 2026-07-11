from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class VehicleData:
    oil_temp_c: float | None = None
    oil_pan_temp_c: float | None = None
    dsg_temp_c: float | None = None
    transmission_fluid_temp_c: float | None = None
    tcu_module_temp_c: float | None = None
    transmission_input_speed_rpm: float | None = None
    selector_lever_position_raw: str | None = None
    displayed_gear_raw: str | None = None
    absolute_intake_pressure_kpa: float | None = None
    ambient_air_pressure_kpa: float | None = None
    absolute_intake_pressure_bar: float | None = None
    ambient_air_pressure_bar: float | None = None
    boost_estimated_bar: float | None = None
    engine_oil_pressure_actual_bar: float | None = None
    engine_oil_pressure_setpoint_bar: float | None = None
    transmission_oil_pressure_actual_bar: float | None = None
    oil_level_available: bool | None = None
    oil_level_status_raw: str | None = None
    oil_level_method_1_pct: float | None = None
    oil_level_method_2_pct: float | None = None
    oil_level_method_3_pct: float | None = None
    oil_level_max_relative_pct: float | None = None
    oil_level_min_relative_pct: float | None = None
    oil_level_current_pct: float | None = None
    oil_level_warning_raw: int | None = None
    battery_voltage_v: float | None = None
    coolant_temp_c: float | None = None
    intake_temp_c: float | None = None
    boost_bar: float | None = None
    map_kpa: float | None = None
    barometric_pressure_kpa: float | None = None
    rpm: float | None = None
    speed_kmh: float | None = None
    throttle_pct: float | None = None
    engine_load_pct: float | None = None
    fuel_rate_lph: float | None = None
    fuel_consumption_l_per_100km: float | None = None
    act_active: bool | None = None
    act_intake_position_raw: str | None = None
    act_exhaust_position_raw: str | None = None
    dtc_alerts: list[dict[str, str]] | None = None
    provider: str = "unknown"
    connected: bool = False
    status: str = "No data"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VehicleProvider(ABC):
    name = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    @abstractmethod
    def read(self) -> VehicleData:
        raise NotImplementedError
