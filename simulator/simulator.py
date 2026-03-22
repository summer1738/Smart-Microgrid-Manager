"""
Unified hardware simulator: PV + BESS + multiple loads.
Produces readings compatible with backend schema (timestamps, power, SOC, etc.).
"""
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .pv_simulator import pv_power_kw
from .battery_simulator import update_soc
from .load_simulator import load_power_kw


# Appliance sim config: id, name, priority, rated_watts, activity 0-1 by hour (optional)
ApplianceSpec = Dict[str, Any]


def default_appliances() -> List[ApplianceSpec]:
    # Defaults used before DB-backed appliances are synced in.
    return [
        {"id": "fridge_01", "name": "Clinic Fridge", "priority": 1, "rated_watts": 80},
        {"id": "pump_01", "name": "Water Pump", "priority": 2, "rated_watts": 400},
        {"id": "lights_01", "name": "Lighting", "priority": 2, "rated_watts": 50},
        {"id": "misc_01", "name": "Misc Load", "priority": 3, "rated_watts": 200},
    ]


class HardwareSimulator:
    """
    Runs in-memory simulation of PV, battery, and loads.
    Call tick(dt) every interval (e.g. 60s) to advance state and get readings.
    """

    def __init__(
        self,
        pv_capacity_kw: float = 1.0,
        battery_capacity_kwh: float = 2.4,
        initial_soc_percent: float = 70.0,
        appliances: Optional[List[ApplianceSpec]] = None,
        cloud_factor: float = 1.0,
    ):
        self.pv_capacity_kw = pv_capacity_kw
        self.battery_capacity_kwh = battery_capacity_kwh
        self.soc_percent = initial_soc_percent
        self.appliances = list(appliances) if appliances is not None else default_appliances()
        self.cloud_factor = cloud_factor
        self._last_dt: Optional[datetime] = None

    def set_appliances(self, appliances: List[ApplianceSpec]) -> None:
        """
        Replace the current appliance list. Called from the backend to sync
        simulator with DB-registered appliances.
        """
        self.appliances = list(appliances)

    def _activity_factor(self, appliance: ApplianceSpec, dt: datetime) -> float:
        """Simple schedule: priority 1 always 1.0; others higher in day."""
        p = appliance.get("priority", 2)
        if p == 1:
            return 1.0
        hour = dt.hour + dt.minute / 60.0
        if 7 <= hour <= 21:
            return 0.7
        return 0.3

    def tick(
        self,
        dt: Optional[datetime] = None,
        appliance_states: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """
        Advance simulation by one step (e.g. 60 s). Returns one combined reading
        suitable for DB insert: pv, battery, loads.
        appliance_states: optional map external_id -> is_on; if provided, off appliances draw 0 power.
        """
        dt = dt or datetime.now(timezone.utc)
        if self._last_dt is None:
            self._last_dt = dt
        step_seconds = (dt - self._last_dt).total_seconds()
        if step_seconds <= 0:
            step_seconds = 60.0

        # PV
        pv_kw = pv_power_kw(dt, self.pv_capacity_kw, self.cloud_factor)
        pv_voltage = 24.0
        pv_current_a = (pv_kw * 1000.0 / pv_voltage) if pv_voltage else 0.0

        # Loads: respect appliance_states (from IEBA schedule) when provided
        total_load_kw = 0.0
        load_readings = []
        for app in self.appliances:
            ext_id = app["id"]
            is_on = appliance_states.get(ext_id, True) if appliance_states is not None else True
            if not is_on:
                load_readings.append({"appliance_id": ext_id, "power_kw": 0.0, "state": "off"})
                continue
            af = self._activity_factor(app, dt)
            kw = load_power_kw(dt, app.get("rated_watts", 100), af, noise=0.08)
            total_load_kw += kw
            load_readings.append({
                "appliance_id": ext_id,
                "power_kw": round(kw, 4),
                "state": "on",
            })

        # Battery
        self.soc_percent = update_soc(
            self.soc_percent,
            pv_kw,
            total_load_kw,
            step_seconds,
            self.battery_capacity_kwh,
        )
        battery_voltage = 12.0
        net_current = (pv_kw - total_load_kw) * 1000.0 / battery_voltage if battery_voltage else 0.0

        self._last_dt = dt

        return {
            "timestamp": dt.isoformat(),
            "pv": {
                "power_kw": round(pv_kw, 4),
                "voltage": pv_voltage,
                "current_a": round(pv_current_a, 4),
            },
            "battery": {
                "soc_percent": round(self.soc_percent, 2),
                "voltage": battery_voltage,
                "current_a": round(net_current, 4),
            },
            "loads": load_readings,
            "total_load_kw": round(total_load_kw, 4),
        }
