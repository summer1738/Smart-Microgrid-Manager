"""
Simulated Battery Energy Storage System (BESS).
State-of-charge (SOC) evolves from generation and load; clamped to [0, 100].
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BatteryState:
    soc_percent: float
    voltage: float
    current_a: float
    timestamp: datetime


def update_soc(
    soc_percent: float,
    pv_power_kw: float,
    load_power_kw: float,
    dt_seconds: float,
    capacity_kwh: float = 2.4,
    efficiency_charge: float = 0.95,
    efficiency_discharge: float = 0.95,
) -> float:
    """
    Update SOC given PV generation and load over dt_seconds.
    capacity_kwh: usable capacity (e.g. 12V 100Ah -> ~1.2 kWh usable if 40-80% SOC window).
    """
    net_kw = pv_power_kw - load_power_kw
    if net_kw >= 0:
        energy_delta_kwh = net_kw * (dt_seconds / 3600.0) * efficiency_charge
    else:
        energy_delta_kwh = net_kw * (dt_seconds / 3600.0) / efficiency_discharge
    soc_delta = 100.0 * (energy_delta_kwh / capacity_kwh)
    new_soc = soc_percent + soc_delta
    return max(0.0, min(100.0, new_soc))
