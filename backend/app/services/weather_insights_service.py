"""Aggregate Open-Meteo extended forecast + compare to historical PV from DB."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import PvReading
from app.services.forecast_service import _pv_from_shortwave_kw
from app.services.system_settings_service import get_weather_settings
from app.services.weather_open_meteo import fetch_forecast_extended

# WMO Weather interpretation codes (Open-Meteo / ECMWF)
WMO_WEATHER_LABEL: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm hail",
    99: "Thunderstorm hail",
}


def weather_code_label(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"
    return WMO_WEATHER_LABEL.get(code, f"Code {code}")


def _mode_most_common(codes: List[Optional[int]]) -> Optional[int]:
    filtered = [c for c in codes if c is not None]
    if not filtered:
        return None
    return max(set(filtered), key=filtered.count)


async def build_weather_pv_insights(
    session: AsyncSession,
    forecast_days: int = 16,
    history_days: int = 30,
    include_hourly: bool = False,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Returns payload for /forecast/weather-insights and a human-readable message or error.
    """
    try:
        ws = await get_weather_settings(session)
        cap = float(ws["weather_pv_capacity_kw"])
        derate = float(ws["weather_panel_derate"])
        lat = float(ws["weather_latitude"])
        lon = float(ws["weather_longitude"])
        enabled = bool(ws["weather_forecast_enabled"])
    except Exception:
        cap = float(settings.weather_pv_capacity_kw)
        derate = float(settings.weather_panel_derate)
        lat = float(settings.weather_latitude)
        lon = float(settings.weather_longitude)
        enabled = bool(settings.weather_forecast_enabled)

    if not enabled:
        hist = await _historical_daily_pv_kwh(session, history_days)
        hist_list = [{"date": k, "actual_pv_kwh": v} for k, v in sorted(hist.items())]
        return (
            {
                "location": {"latitude": lat, "longitude": lon},
                "forecast_available": False,
                "message": "Weather forecast disabled in system settings.",
                "historical_daily_pv_kwh": hist_list,
                "daily_weather": [],
                "hourly_forecast": [],
                "comparison": None,
            },
            "Weather API disabled.",
        )

    wx = await fetch_forecast_extended(lat, lon, forecast_days=min(16, forecast_days))
    if wx is None:
        hist = await _historical_daily_pv_kwh(session, history_days)
        hist_list = [{"date": k, "actual_pv_kwh": v} for k, v in sorted(hist.items())]
        return (
            {
                "location": {"latitude": lat, "longitude": lon},
                "forecast_available": False,
                "message": "Could not fetch Open-Meteo forecast.",
                "historical_daily_pv_kwh": hist_list,
                "daily_weather": [],
                "hourly_forecast": [],
                "comparison": None,
            },
            "Open-Meteo request failed.",
        )

    times: List[datetime] = wx["times"]
    sw: List[float] = wx["shortwave_radiation"]
    cc: List[Optional[float]] = wx["cloud_cover"]
    raw_wc = wx.get("weather_code") or []
    wcode: List[Optional[int]] = []
    for i in range(len(times)):
        if i < len(raw_wc) and raw_wc[i] is not None:
            try:
                wcode.append(int(raw_wc[i]))
            except (TypeError, ValueError):
                wcode.append(None)
        else:
            wcode.append(None)

    pv_kw = [_pv_from_shortwave_kw(s, cap, derate) for s in sw]

    daily_weather: List[Dict[str, Any]] = []
    by_day: Dict[date, Dict[str, Any]] = {}
    for i, t in enumerate(times):
        d = t.astimezone(timezone.utc).date()
        if d not in by_day:
            by_day[d] = {
                "clouds": [],
                "shortwave": [],
                "codes": [],
                "pv_kwh": 0.0,
            }
        by_day[d]["clouds"].append(cc[i] if i < len(cc) else None)
        by_day[d]["shortwave"].append(sw[i] if i < len(sw) else 0.0)
        by_day[d]["codes"].append(wcode[i] if i < len(wcode) else None)
        by_day[d]["pv_kwh"] += pv_kw[i] * 1.0  # kW·h for hourly mean power

    for d in sorted(by_day.keys()):
        bucket = by_day[d]
        clouds = [c for c in bucket["clouds"] if c is not None]
        swd = bucket["shortwave"]
        mode_c = _mode_most_common(bucket["codes"])
        daily_weather.append(
            {
                "date": str(d),
                "avg_cloud_cover_pct": round(sum(clouds) / len(clouds), 1) if clouds else None,
                "max_shortwave_wm2": round(max(swd), 1) if swd else 0.0,
                "dominant_weather_code": mode_c,
                "dominant_weather_label": weather_code_label(mode_c),
                "expected_pv_kwh": round(bucket["pv_kwh"], 3),
            }
        )

    hourly_forecast: List[Dict[str, Any]] = []
    if include_hourly:
        hourly_forecast = [
            {
                "timestamp": times[i].isoformat(),
                "shortwave_wm2": round(sw[i], 1) if i < len(sw) else 0.0,
                "cloud_cover_pct": round(cc[i], 1) if i < len(cc) and cc[i] is not None else None,
                "weather_code": wcode[i] if i < len(wcode) else None,
                "weather_label": weather_code_label(wcode[i] if i < len(wcode) else None),
                "expected_pv_kw": round(pv_kw[i], 4),
            }
            for i in range(len(times))
        ]

    hist = await _historical_daily_pv_kwh(session, history_days)
    hist_list = [{"date": k, "actual_pv_kwh": v} for k, v in sorted(hist.items())]

    # Comparison: sum first 14 days of forecast vs last 14 days of actual (if present)
    comp: Optional[Dict[str, Any]] = None
    days_14 = min(14, len(daily_weather))
    if daily_weather and hist:
        next14_kwh = sum(d["expected_pv_kwh"] for d in daily_weather[:14])
        # last 14 calendar days of history
        sorted_dates = sorted(hist.keys(), reverse=True)
        prev14 = sorted_dates[:14]
        prev14_kwh = sum(hist.get(d, 0.0) for d in prev14)
        comp = {
            "next_14d_forecast_pv_kwh": round(next14_kwh, 2),
            "last_14d_actual_pv_kwh": round(prev14_kwh, 2),
            "ratio_forecast_over_actual": round(next14_kwh / prev14_kwh, 3) if prev14_kwh > 0 else None,
        }

    payload = {
        "location": {"latitude": lat, "longitude": lon},
        "forecast_available": True,
        "forecast_days": wx.get("forecast_days", len(by_day)),
        "period_start": times[0].isoformat() if times else None,
        "period_end": times[-1].isoformat() if times else None,
        "message": None,
        "daily_weather": daily_weather,
        "hourly_forecast": hourly_forecast,
        "historical_daily_pv_kwh": hist_list,
        "comparison": comp,
    }
    msg = (
        f"Open-Meteo forecast ({len(daily_weather)} days) at {lat:.4f}, {lon:.4f}; "
        f"historical PV from DB ({len(hist_list)} days with data)."
    )
    return payload, msg


async def _historical_daily_pv_kwh(session: AsyncSession, days_back: int) -> Dict[str, float]:
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    r = await session.execute(
        select(PvReading.timestamp, PvReading.power_kw)
        .where(PvReading.timestamp >= since)
        .order_by(PvReading.timestamp)
    )
    rows = list(r.all())
    if not rows:
        return {}

    by_day: Dict[date, List[Tuple[datetime, float]]] = defaultdict(list)
    for ts, kw in rows:
        d = ts.astimezone(timezone.utc).date()
        by_day[d].append((ts, float(kw)))

    out: Dict[str, float] = {}
    for d, pts in sorted(by_day.items()):
        pts.sort(key=lambda x: x[0])
        energy = 0.0
        if len(pts) == 1:
            energy = pts[0][1] * 6.0  # assume ~10min tick if single point; rough
        else:
            for i in range(len(pts) - 1):
                t0, p0 = pts[i]
                t1, p1 = pts[i + 1]
                dt_h = (t1 - t0).total_seconds() / 3600.0
                if dt_h > 0:
                    energy += 0.5 * (p0 + p1) * dt_h
        out[str(d)] = round(max(0.0, energy), 3)
    return out
