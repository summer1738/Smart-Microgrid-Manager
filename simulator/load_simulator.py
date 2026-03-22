"""
Simulated load consumption per appliance.
Uses time-of-day patterns (morning/evening peaks) and optional randomness.
"""
from datetime import datetime
import random
from typing import List, Optional


def load_power_kw(
    dt: datetime,
    rated_watts: float,
    activity_factor: float = 1.0,
    noise: float = 0.1,
    seed: Optional[int] = None,
) -> float:
    """
    rated_watts: appliance nameplate power.
    activity_factor: 0..1, typical usage at this time (from schedule pattern).
    noise: relative random variation (e.g. 0.1 = ±10%).
    """
    if seed is not None:
        random.seed(seed)
    hour = dt.hour + dt.minute / 60.0
    # Simple daily pattern: higher in morning (6–9) and evening (17–21)
    if 6 <= hour <= 9 or 17 <= hour <= 21:
        pattern = 0.9 + 0.1 * random.random()
    else:
        pattern = 0.3 + 0.4 * random.random()
    base = (rated_watts / 1000.0) * activity_factor * pattern
    if noise > 0:
        base *= 1.0 + (random.random() - 0.5) * 2.0 * noise
    return max(0.0, base)
