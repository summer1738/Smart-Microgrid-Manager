"""
Forecast service: 24–48h ahead for PV generation and total consumption.
Uses Open-Meteo weather when enabled; otherwise clear-sky PV curve.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.config import settings
from app.services.weather_open_meteo import (
    build_hour_index,
    fetch_hourly_weather,
    lookup_hour,
)
from app.services.system_settings_service import get_weather_settings
from app.services.ml_forecast_service import try_model_forecast

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


def _consumption_pattern_kw(ts: datetime) -> float:
    hour = ts.hour + ts.minute / 60.0
    if 7 <= hour <= 9 or 17 <= hour <= 21:
        demand = 0.4 + 0.3 * (1.0 if 17 <= hour <= 21 else 0.7)
    else:
        demand = 0.15 + 0.1 * (hour / 24.0)
    return round(demand, 4)


def _pv_from_shortwave_kw(
    shortwave_wm2: float,
    capacity_kw: float,
    derate: float,
) -> float:
    """Map hourly mean irradiance (W/m²) to array power; STC 1000 W/m² ≈ nameplate."""
    if shortwave_wm2 <= 0:
        return 0.0
    raw = capacity_kw * (shortwave_wm2 / 1000.0) * derate
    return max(0.0, min(capacity_kw * 1.15, raw))


async def generate_forecast_with_weather(
    horizon_hours: int = 24,
    resolution_hours: float = 1.0,
    pv_capacity_kw: Optional[float] = None,
    base_ts: Optional[datetime] = None,
) -> Tuple[List[str], List[float], List[float], str]:
    """
    PV from Open-Meteo (shortwave + cloud) when enabled; else clear-sky simulation.
    Returns (timestamps_iso, generation_kw, consumption_kw, message).
    """
    # Prefer persisted system settings (UI configurable). Fall back to env defaults.
    if pv_capacity_kw is None:
        try:
            from app.database import async_session

            async with async_session() as session:
                ws = await get_weather_settings(session)
            cap = float(ws["weather_pv_capacity_kw"])
            derate = float(ws["weather_panel_derate"])
            enabled = bool(ws["weather_forecast_enabled"])
            lat = float(ws["weather_latitude"])
            lon = float(ws["weather_longitude"])
        except Exception:
            cap = float(settings.weather_pv_capacity_kw)
            derate = float(settings.weather_panel_derate)
            enabled = bool(settings.weather_forecast_enabled)
            lat = float(settings.weather_latitude)
            lon = float(settings.weather_longitude)
    else:
        cap = float(pv_capacity_kw)
        derate = float(settings.weather_panel_derate)
        enabled = bool(settings.weather_forecast_enabled)
        lat = float(settings.weather_latitude)
        lon = float(settings.weather_longitude)
    base_ts = base_ts or datetime.now(timezone.utc)
    steps = max(1, int(horizon_hours / resolution_hours))

    if not enabled:
        ts, gen, cons = generate_simulated_forecast(
            horizon_hours=horizon_hours,
            resolution_hours=resolution_hours,
            pv_capacity_kw=cap,
            cloud_factor=0.9,
            base_ts=base_ts,
        )
        return ts, gen, cons, "Weather API disabled; using clear-sky PV curve (set MICROGRID_WEATHER_FORECAST_ENABLED=true)."

    wx = await fetch_hourly_weather(
        lat,
        lon,
        forecast_hours=horizon_hours + 24,
    )
    if wx is None:
        ts, gen, cons = generate_simulated_forecast(
            horizon_hours=horizon_hours,
            resolution_hours=resolution_hours,
            pv_capacity_kw=cap,
            cloud_factor=0.9,
            base_ts=base_ts,
        )
        return ts, gen, cons, "Weather fetch failed; using clear-sky PV fallback."

    idx, _tmin, _tmax = build_hour_index(wx["times"], wx["shortwave_radiation"], wx["cloud_cover"])

    timestamps: List[str] = []
    generation_kw: List[float] = []
    consumption_kw: List[float] = []
    used_weather = 0

    for i in range(steps):
        ts = base_ts + timedelta(hours=i * resolution_hours)
        timestamps.append(ts.isoformat())
        looked = lookup_hour(idx, ts)
        if looked is not None:
            sw, _cc = looked
            gen = _pv_from_shortwave_kw(sw, cap, derate)
            generation_kw.append(round(gen, 4))
            used_weather += 1
        else:
            clear_shape = pv_power_kw(ts, cap, 0.85)
            generation_kw.append(round(clear_shape, 4))
        consumption_kw.append(_consumption_pattern_kw(ts))

    msg = (
        f"PV from Open-Meteo hourly forecast (lat={lat}, lon={lon}); "
        f"{used_weather}/{steps} hours mapped from shortwave radiation."
    )
    return timestamps, generation_kw, consumption_kw, msg


async def generate_hybrid_forecast(
    horizon_hours: int = 24,
    resolution_hours: float = 1.0,
    base_ts: Optional[datetime] = None,
) -> Tuple[List[str], List[float], List[float], str]:
    """
    Hybrid forecast:
    - PV generation: prefer weather-based PV (Open-Meteo) when enabled; fallback to LSTM PV if present.
    - Consumption: prefer LSTM demand if present; fallback to simple pattern.
    """
    base_ts = base_ts or datetime.now(timezone.utc)

    model = try_model_forecast(horizon_hours=horizon_hours, resolution_hours=resolution_hours, base_ts=base_ts)
    w_ts, w_gen, w_cons, w_msg = await generate_forecast_with_weather(
        horizon_hours=horizon_hours, resolution_hours=resolution_hours, base_ts=base_ts
    )

    if model is None:
        return w_ts, w_gen, w_cons, w_msg

    m_ts, m_gen, m_load, m_msg = model
    # Align on timestamps length (hourly). If mismatch, keep model series as-is.
    use_weather_pv = len(w_gen) == len(m_gen) and "PV from Open-Meteo" in (w_msg or "")
    gen = w_gen if use_weather_pv else m_gen
    cons = m_load
    msg = f"Hybrid forecast: PV={'Open-Meteo' if use_weather_pv else 'LSTM'}; load=LSTM. {w_msg if use_weather_pv else m_msg}"
    return m_ts, gen, cons, msg
