"""
Simulated PV array output. Uses time-of-day and optional cloud factor.
No real irradiance API required; can be replaced later with weather data.
"""
from datetime import datetime
import math


def pv_power_kw(
    dt: datetime,
    capacity_kw: float = 1.0,
    cloud_factor: float = 1.0,
    latitude_deg: float = -17.8,
) -> float:
    """
    Simple clear-sky style curve: zero at night, peak near solar noon.
    capacity_kw: nominal peak power. cloud_factor in [0, 1] (1 = clear).
    """
    hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    # Approximate sunrise/sunset (simplified for Harare-ish latitude)
    sunrise, sunset = 6.0, 18.0
    if hour < sunrise or hour > sunset:
        return 0.0
    # Sine-like curve between sunrise and sunset
    noon = (sunrise + sunset) / 2.0
    half_day = (sunset - sunrise) / 2.0
    x = (hour - noon) / half_day  # -1 .. +1
    clear_sky = max(0.0, math.cos(x * math.pi / 2.0))
    return capacity_kw * clear_sky * cloud_factor
