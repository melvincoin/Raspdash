from __future__ import annotations

import math
import time

from raspdash.providers.base import VehicleData, VehicleProvider


class SimulatedProvider(VehicleProvider):
    name = "simulated"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.started_at = time.monotonic()

    def read(self) -> VehicleData:
        elapsed = time.monotonic() - self.started_at
        oil = 88 + math.sin(elapsed / 3.8) * 7
        dsg = 72 + math.sin(elapsed / 4.8 + 1.4) * 5
        voltage = 14.1 + math.sin(elapsed / 2.6) * 0.22
        speed = round(max(0, math.sin(elapsed / 3.2)) * 82, 0)
        consumption = round(6.5 + math.sin(elapsed / 2.1) * 2.1, 1)
        oil_level_test_values = (55.0, 25.0, 15.0)
        oil_level_pct = oil_level_test_values[int(elapsed // 10) % len(oil_level_test_values)]
        return VehicleData(
            oil_temp_c=round(oil, 0),
            oil_pan_temp_c=round(oil - 2, 0),
            dsg_temp_c=round(dsg, 0),
            transmission_fluid_temp_c=round(dsg, 0),
            tcu_module_temp_c=round(dsg - 4, 0),
            transmission_input_speed_rpm=1420,
            selector_lever_position_raw="08",
            displayed_gear_raw="04",
            absolute_intake_pressure_kpa=118,
            ambient_air_pressure_kpa=101,
            absolute_intake_pressure_bar=1.18,
            ambient_air_pressure_bar=1.01,
            boost_estimated_bar=0.17,
            engine_oil_pressure_actual_bar=2.35,
            engine_oil_pressure_setpoint_bar=2.50,
            transmission_oil_pressure_actual_bar=8.4,
            battery_voltage_v=round(voltage, 1),
            coolant_temp_c=round(86 + math.sin(elapsed / 4.4 + 0.7) * 4, 0),
            intake_temp_c=round(28 + math.sin(elapsed / 3.6 + 2.0) * 5, 0),
            boost_bar=round(0.2 + max(0, math.sin(elapsed / 1.8)) * 0.8, 2),
            rpm=round(820 + max(0, math.sin(elapsed / 1.6)) * 1600, 0),
            speed_kmh=speed,
            throttle_pct=round(12 + max(0, math.sin(elapsed / 2.4 + 1.0)) * 42, 0),
            engine_load_pct=round(18 + max(0, math.sin(elapsed / 2.8 + 0.2)) * 55, 0),
            fuel_rate_lph=round(consumption * max(speed, 3) / 100, 2),
            fuel_consumption_l_per_100km=consumption,
            act_active=(int(elapsed // 5) % 2 == 0),
            oil_level_available=True,
            oil_level_status_raw="00 00",
            oil_level_method_1_pct=oil_level_pct,
            oil_level_method_2_pct=oil_level_pct,
            oil_level_method_3_pct=oil_level_pct,
            oil_level_max_relative_pct=100.0,
            oil_level_min_relative_pct=0.0,
            oil_level_current_pct=oil_level_pct,
            oil_level_warning_raw=0 if oil_level_pct >= 20 else 1,
            map_kpa=118,
            barometric_pressure_kpa=101,
            act_intake_position_raw="0A" if int(elapsed // 5) % 2 == 0 else "00",
            act_exhaust_position_raw="0A" if int(elapsed // 5) % 2 == 0 else "00",
            dtc_alerts=[
                {"module": "Engine", "code": "P0301", "status": "pending"},
                {"module": "Transmission", "code": "P17BF", "status": "confirmed"},
            ],
            provider=self.name,
            connected=True,
            status="Simulator active",
        )
