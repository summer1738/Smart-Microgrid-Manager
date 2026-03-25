"""
Fetch hourly weather from Open-Meteo (free, no API key).

https://open-meteo.com/en/docs — hourly cloud_cover (%), shortwave_radiation (W/m²).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _parse_hourly_time(s: str) -> datetime:
    # "2024-01-15T12:00" or with Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def fetch_hourly_weather(
    latitude: float,
    longitude: float,
    forecast_hours: int,
) -> Optional[Dict[str, Any]]:
    """
    Returns dict with keys: times (list[datetime] UTC), cloud_cover, shortwave_radiation (same length).
    None on HTTP error or missing data.
    """
    days = min(16, max(1, int((forecast_hours + 23) // 24) + 1))
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "cloud_cover,shortwave_radiation",
        "forecast_days": days,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    hourly = data.get("hourly") or {}
    times_raw = hourly.get("time") or []
    cc = hourly.get("cloud_cover") or []
    sw = hourly.get("shortwave_radiation") or []
    if not times_raw or not sw:
        return None

    times: List[datetime] = []
    cloud_cover: List[Optional[float]] = []
    shortwave: List[float] = []
    for i, t in enumerate(times_raw):
        try:
            dt = _parse_hourly_time(str(t))
        except Exception:
            continue
        times.append(dt)
        if i < len(cc) and cc[i] is not None:
            cloud_cover.append(float(cc[i]))
        else:
            cloud_cover.append(None)
        if i < len(sw) and sw[i] is not None:
            shortwave.append(float(sw[i]))
        else:
            shortwave.append(0.0)

    if len(times) != len(shortwave):
        return None

    return {"times": times, "cloud_cover": cloud_cover, "shortwave_radiation": shortwave}


async def fetch_forecast_extended(
    latitude: float,
    longitude: float,
    forecast_days: int = 16,
) -> Optional[Dict[str, Any]]:
    """
    Up to 16 days of hourly data (Open-Meteo limit) including WMO weather_code for UI summaries.
    """
    days = min(16, max(1, forecast_days))
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "cloud_cover,shortwave_radiation,weather_code",
        "forecast_days": days,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    hourly = data.get("hourly") or {}
    times_raw = hourly.get("time") or []
    cc = hourly.get("cloud_cover") or []
    sw = hourly.get("shortwave_radiation") or []
    wc = hourly.get("weather_code") or []
    if not times_raw or not sw:
        return None

    times: List[datetime] = []
    cloud_cover: List[Optional[float]] = []
    shortwave: List[float] = []
    weather_code: List[Optional[int]] = []
    for i, t in enumerate(times_raw):
        try:
            dt = _parse_hourly_time(str(t))
        except Exception:
            continue
        times.append(dt)
        if i < len(cc) and cc[i] is not None:
            cloud_cover.append(float(cc[i]))
        else:
            cloud_cover.append(None)
        if i < len(sw) and sw[i] is not None:
            shortwave.append(float(sw[i]))
        else:
            shortwave.append(0.0)
        if i < len(wc) and wc[i] is not None:
            try:
                weather_code.append(int(wc[i]))
            except (TypeError, ValueError):
                weather_code.append(None)
        else:
            weather_code.append(None)

    if len(times) != len(shortwave):
        return None

    return {
        "times": times,
        "cloud_cover": cloud_cover,
        "shortwave_radiation": shortwave,
        "weather_code": weather_code,
        "forecast_days": days,
    }


def build_hour_index(
    times: List[datetime],
    shortwave: List[float],
    cloud_cover: List[Optional[float]],
) -> Tuple[Dict[Tuple[int, int, int, int], Tuple[float, Optional[float]]], datetime, datetime]:
    """
    Map (year, month, day, hour) UTC -> (shortwave W/m², cloud % or None).
    """
    idx: Dict[Tuple[int, int, int, int], Tuple[float, Optional[float]]] = {}
    for i, t in enumerate(times):
        h = (t.year, t.month, t.day, t.hour)
        cc = cloud_cover[i] if i < len(cloud_cover) else None
        idx[h] = (shortwave[i], cc)
    return idx, min(times), max(times)


def lookup_hour(
    idx: Dict[Tuple[int, int, int, int], Tuple[float, Optional[float]]],
    ts: datetime,
) -> Optional[Tuple[float, Optional[float]]]:
    t = ts.astimezone(timezone.utc)
    return idx.get((t.year, t.month, t.day, t.hour))
