"""
Forecast service: 24–48h ahead for PV generation and total consumption.
Uses simulator curves when no LSTM model is available (simulated forecast).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# Simulator lives at project root; run with PYTHONPATH=..
from simulator.pv_simulator import pv_power_kw


def generate_simulated_forecast(
    horizon_hours: int = 24,
    resolution_hours: float = 1.0,
    pv_capacity_kw: float = 1.0,
    cloud_factor: float = 0.9,
    base_ts: Optional[datetime] = None,
) -> tuple[List[str], List[float], List[float]]:
    """
    Return (timestamps, generation_kw, consumption_kw) using PV curve and
    a simple demand pattern (morning/evening peaks). No LSTM.
    """
    base_ts = base_ts or datetime.now(timezone.utc)
    steps = max(1, int(horizon_hours / resolution_hours))
    timestamps = []
    generation_kw = []
    consumption_kw = []

    for i in range(steps):
        ts = base_ts + timedelta(hours=i * resolution_hours)
        timestamps.append(ts.isoformat())
        generation_kw.append(pv_power_kw(ts, pv_capacity_kw, cloud_factor))

        # Simple demand pattern: base + peaks in 7–9 and 17–21
        hour = ts.hour + ts.minute / 60.0
        if 7 <= hour <= 9 or 17 <= hour <= 21:
            demand = 0.4 + 0.3 * (1.0 if 17 <= hour <= 21 else 0.7)
        else:
            demand = 0.15 + 0.1 * (hour / 24.0)
        consumption_kw.append(round(demand, 4))

    return timestamps, generation_kw, consumption_kw
