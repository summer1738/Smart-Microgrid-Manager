"""Generate human-readable microgrid insights from forecasts, live metrics, and schedule data."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appliance, BatteryReading, LoadReading, PvReading, ScheduleSlot
from app.services.forecast_service import generate_hybrid_forecast
from app.services.ml_forecast_service import try_model_forecast
from app.services.system_settings_service import get_microgrid_sizing_settings
from app.services.weather_insights_service import build_weather_pv_insights


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_ts(iso_or_dt: Optional[Any]) -> str:
    if iso_or_dt is None:
        return "unknown time"
    if isinstance(iso_or_dt, str):
        try:
            dt = datetime.fromisoformat(iso_or_dt.replace("Z", "+00:00"))
        except ValueError:
            return str(iso_or_dt)
    elif isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        return str(iso_or_dt)
    dt = _to_utc(dt)
    return dt.strftime("%H:%M UTC")


def _format_number(value: Optional[float], unit: str, decimals: int = 1) -> str:
    if value is None:
        return "n/a"
    if unit == "%":
        return f"{float(value):.{decimals}f}%"
    if not unit:
        return f"{float(value):.{decimals}f}"
    return f"{float(value):.{decimals}f} {unit}"


def _evidence(label: str, value: str) -> Dict[str, str]:
    return {"label": label, "value": value}


def _severity_rank(level: str) -> int:
    return {
        "critical": 4,
        "warning": 3,
        "success": 2,
        "info": 1,
    }.get(level, 0)


def _compute_pair_metrics(
    actual: List[Optional[float]],
    pred: List[Optional[float]],
    eps: float = 1e-6,
    min_y_kw: float = 0.02,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    paired_actual: List[float] = []
    paired_pred: List[float] = []
    for i in range(min(len(actual), len(pred))):
        av = actual[i]
        pv = pred[i]
        if av is None or pv is None:
            continue
        paired_actual.append(float(av))
        paired_pred.append(float(pv))

    if not paired_actual:
        return None, None, None

    a_arr = np.array(paired_actual)
    p_arr = np.array(paired_pred)
    smape = float(np.mean(2.0 * np.abs(a_arr - p_arr) / (np.abs(a_arr) + np.abs(p_arr) + eps)) * 100.0)
    mae = float(np.mean(np.abs(a_arr - p_arr)))
    mask = np.abs(a_arr) >= min_y_kw
    if np.sum(mask) >= 3:
        mape_masked = float(np.mean(np.abs(a_arr[mask] - p_arr[mask]) / (np.abs(a_arr[mask]) + eps)) * 100.0)
    else:
        mape_masked = None
    return smape, mape_masked, mae


async def compute_live_forecast_metrics(
    session: AsyncSession,
    now: Optional[datetime] = None,
    hours: int = 24,
) -> Dict[str, Optional[float]]:
    """
    Compare a 24h model rollout anchored in the past against actual DB history.
    """
    now = _to_utc(now or datetime.now(timezone.utc))
    base_ts = (now - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
    past_forecast = try_model_forecast(horizon_hours=hours, resolution_hours=1.0, base_ts=base_ts)
    if past_forecast is None:
        return {
            "hours": None,
            "live_smape_gen": None,
            "live_smape_load": None,
            "live_mape_masked_gen": None,
            "live_mape_masked_load": None,
            "live_mae_gen": None,
            "live_mae_load": None,
        }

    since = now - timedelta(hours=hours)
    bat = await session.execute(
        select(BatteryReading.timestamp)
        .where(BatteryReading.timestamp >= since)
        .order_by(BatteryReading.timestamp)
    )
    battery_ts = [_to_utc(ts) for (ts,) in bat.all()]
    if not battery_ts:
        return {
            "hours": None,
            "live_smape_gen": None,
            "live_smape_load": None,
            "live_mape_masked_gen": None,
            "live_mape_masked_load": None,
            "live_mae_gen": None,
            "live_mae_load": None,
        }

    pv_rows = await session.execute(
        select(PvReading.timestamp, PvReading.power_kw).where(PvReading.timestamp >= since)
    )
    pv_by_ts = {_to_utc(ts): float(kw) for ts, kw in pv_rows.all()}

    load_rows = await session.execute(
        select(LoadReading.timestamp, func.sum(LoadReading.power_kw))
        .where(LoadReading.timestamp >= since)
        .group_by(LoadReading.timestamp)
    )
    load_by_ts = {}
    for ts, kw in load_rows.all():
        load_by_ts[_to_utc(ts)] = float(kw) if kw is not None else 0.0

    bucket_pv: Dict[datetime, List[float]] = defaultdict(list)
    bucket_load: Dict[datetime, List[float]] = defaultdict(list)
    for ts in battery_ts:
        bucket = ts.replace(minute=0, second=0, microsecond=0)
        pv = pv_by_ts.get(ts)
        if pv is not None:
            bucket_pv[bucket].append(pv)
        ld = load_by_ts.get(ts)
        if ld is not None:
            bucket_load[bucket].append(ld)

    actual_gen: List[Optional[float]] = []
    actual_load: List[Optional[float]] = []
    for h in range(hours):
        bucket = base_ts + timedelta(hours=h)
        actual_gen.append(float(np.mean(bucket_pv[bucket])) if bucket_pv[bucket] else None)
        actual_load.append(float(np.mean(bucket_load[bucket])) if bucket_load[bucket] else None)

    _ts_hist, pred_gen, pred_load, _ = past_forecast
    live_smape_gen, live_mape_masked_gen, live_mae_gen = _compute_pair_metrics(actual_gen, pred_gen)
    live_smape_load, live_mape_masked_load, live_mae_load = _compute_pair_metrics(actual_load, pred_load)
    return {
        "hours": hours,
        "live_smape_gen": round(live_smape_gen, 2) if live_smape_gen is not None else None,
        "live_smape_load": round(live_smape_load, 2) if live_smape_load is not None else None,
        "live_mape_masked_gen": round(live_mape_masked_gen, 2) if live_mape_masked_gen is not None else None,
        "live_mape_masked_load": round(live_mape_masked_load, 2) if live_mape_masked_load is not None else None,
        "live_mae_gen": round(live_mae_gen, 4) if live_mae_gen is not None else None,
        "live_mae_load": round(live_mae_load, 4) if live_mae_load is not None else None,
    }


async def build_descriptive_insights(
    session: AsyncSession,
    horizon_hours: int = 24,
    now: Optional[datetime] = None,
    forecast_bundle: Optional[Tuple[List[str], List[float], List[float], str]] = None,
    live_metrics: Optional[Dict[str, Optional[float]]] = None,
    include_weather_context: bool = True,
    model_active: Optional[bool] = None,
) -> Dict[str, Any]:
    now = _to_utc(now or datetime.now(timezone.utc))
    forecast_bundle = forecast_bundle or await generate_hybrid_forecast(
        horizon_hours=horizon_hours,
        resolution_hours=1.0,
        base_ts=now,
    )
    timestamps, generation_kw, consumption_kw, forecast_message = forecast_bundle
    live_metrics = live_metrics or await compute_live_forecast_metrics(session, now=now, hours=min(24, horizon_hours))
    sizing = await get_microgrid_sizing_settings(session)
    reserve_floor = float(sizing["soc_min_percent"])

    latest = await _load_latest_snapshot(session)
    upcoming_schedule = await _load_schedule_window(session, now=now, horizon_hours=horizon_hours)

    weather_payload = None
    if include_weather_context:
        weather_payload, _summary = await build_weather_pv_insights(
            session,
            forecast_days=max(1, min(3, int((horizon_hours + 23) // 24))),
            history_days=14,
            include_hourly=True,
        )

    peak_idx = int(np.argmax(generation_kw)) if generation_kw else 0
    peak_kw = float(generation_kw[peak_idx]) if generation_kw else 0.0
    peak_ts = timestamps[peak_idx] if timestamps else None
    preview_hours = min(6, len(generation_kw), len(consumption_kw))
    next_6h_net_kwh = sum(generation_kw[:preview_hours]) - sum(consumption_kw[:preview_hours])

    insights: List[Dict[str, Any]] = []
    battery_insight = _battery_insight(
        latest_soc=latest["soc_percent"],
        reserve_floor=reserve_floor,
        next_6h_net_kwh=next_6h_net_kwh,
        latest_pv_kw=latest["pv_kw"],
        latest_load_kw=latest["total_load_kw"],
        peak_ts=peak_ts,
    )
    if battery_insight is not None:
        insights.append(battery_insight)

    forecast_insight = _forecast_accuracy_insight(
        live_metrics=live_metrics,
        forecast_message=forecast_message,
        model_active=model_active,
        weather_payload=weather_payload,
    )
    if forecast_insight is not None:
        insights.append(forecast_insight)

    solar_insight = _solar_outlook_insight(
        weather_payload=weather_payload,
        peak_ts=peak_ts,
        peak_kw=peak_kw,
        horizon_hours=horizon_hours,
    )
    if solar_insight is not None:
        insights.append(solar_insight)

    schedule_insight = _schedule_alignment_insight(
        schedule_rows=upcoming_schedule,
        peak_ts=peak_ts,
        latest_soc=latest["soc_percent"],
        reserve_floor=reserve_floor,
        peak_kw=peak_kw,
    )
    if schedule_insight is not None:
        insights.append(schedule_insight)

    insights.sort(key=lambda item: _severity_rank(item["severity"]), reverse=True)
    summary = _build_summary(insights)
    return {
        "generated_at": now,
        "forecast_horizon_hours": horizon_hours,
        "battery_reserve_target_percent": reserve_floor,
        "summary": summary,
        "insights": insights[:4],
    }


async def _load_latest_snapshot(session: AsyncSession) -> Dict[str, Optional[float]]:
    pv_row = (
        await session.execute(select(PvReading).order_by(desc(PvReading.timestamp)).limit(1))
    ).scalar_one_or_none()
    bat_row = (
        await session.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
    ).scalar_one_or_none()
    load_rows = await session.execute(
        select(LoadReading, Appliance)
        .join(Appliance, LoadReading.appliance_id == Appliance.id)
        .order_by(desc(LoadReading.timestamp))
    )

    seen: set[int] = set()
    total_load = 0.0
    for load_row, app in load_rows.all():
        if app.id in seen:
            continue
        seen.add(app.id)
        total_load += float(load_row.power_kw)

    return {
        "pv_kw": float(pv_row.power_kw) if pv_row is not None else None,
        "soc_percent": float(bat_row.soc_percent) if bat_row is not None else None,
        "total_load_kw": round(total_load, 4) if seen else None,
    }


async def _load_schedule_window(
    session: AsyncSession,
    now: datetime,
    horizon_hours: int,
) -> List[Tuple[ScheduleSlot, Appliance]]:
    end_ts = now + timedelta(hours=horizon_hours)
    result = await session.execute(
        select(ScheduleSlot, Appliance)
        .join(Appliance, ScheduleSlot.appliance_id == Appliance.id)
        .where(
            ScheduleSlot.start_ts >= now,
            ScheduleSlot.start_ts <= end_ts,
            ScheduleSlot.planned_state == "on",
            ScheduleSlot.status.in_(["pending", "applied"]),
        )
        .order_by(ScheduleSlot.start_ts)
    )
    return list(result.all())


def _battery_insight(
    latest_soc: Optional[float],
    reserve_floor: float,
    next_6h_net_kwh: float,
    latest_pv_kw: Optional[float],
    latest_load_kw: Optional[float],
    peak_ts: Optional[str],
) -> Optional[Dict[str, Any]]:
    if latest_soc is None:
        return None

    evidence = [
        _evidence("SOC", _format_number(latest_soc, "%")),
        _evidence("Reserve floor", _format_number(reserve_floor, "%")),
        _evidence("Next 6h net energy", _format_number(next_6h_net_kwh, "kWh", 2)),
    ]
    if latest_pv_kw is not None:
        evidence.append(_evidence("Current PV", _format_number(latest_pv_kw, "kW", 2)))
    if latest_load_kw is not None:
        evidence.append(_evidence("Current load", _format_number(latest_load_kw, "kW", 2)))

    if latest_soc <= reserve_floor:
        return {
            "category": "battery",
            "severity": "critical",
            "title": "Battery reserve is below the configured floor",
            "message": (
                f"State of charge is {latest_soc:.1f}%, below the reserve target of {reserve_floor:.1f}%. "
                f"The next 6 hours are forecast to {'consume' if next_6h_net_kwh < 0 else 'recover'} "
                f"{abs(next_6h_net_kwh):.2f} kWh {'more than they generate' if next_6h_net_kwh < 0 else 'of surplus energy'}."
            ),
            "recommendation": "Keep non-essential appliances off and rerun scheduling after solar production improves.",
            "evidence": evidence,
        }

    if latest_soc <= reserve_floor + 5.0 and next_6h_net_kwh < 0:
        return {
            "category": "battery",
            "severity": "warning",
            "title": "Battery reserve is tightening",
            "message": (
                f"SOC is {latest_soc:.1f}%, only {latest_soc - reserve_floor:.1f} percentage points above the reserve floor, "
                f"and the next 6 hours are forecast to run a {abs(next_6h_net_kwh):.2f} kWh energy deficit."
            ),
            "recommendation": f"Shift flexible loads closer to the expected PV peak around {_format_ts(peak_ts)}.",
            "evidence": evidence,
        }

    if next_6h_net_kwh > 0.5 and latest_soc < 95.0:
        return {
            "category": "battery",
            "severity": "success",
            "title": "Upcoming solar should rebuild battery reserve",
            "message": (
                f"The forecast shows a {next_6h_net_kwh:.2f} kWh surplus over the next 6 hours, "
                f"which should help lift SOC from its current {latest_soc:.1f}%."
            ),
            "recommendation": "Use the midday window for discretionary loads before the evening discharge period.",
            "evidence": evidence,
        }

    return {
        "category": "battery",
        "severity": "info",
        "title": "Battery reserve is stable",
        "message": (
            f"SOC is {latest_soc:.1f}%, comfortably above the {reserve_floor:.1f}% reserve floor, "
            f"with a short-term energy balance of {next_6h_net_kwh:.2f} kWh."
        ),
        "recommendation": "Continue normal scheduling while monitoring the next forecast refresh.",
        "evidence": evidence,
    }


def _forecast_accuracy_insight(
    live_metrics: Dict[str, Optional[float]],
    forecast_message: str,
    model_active: Optional[bool],
    weather_payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    gen_smape = live_metrics.get("live_smape_gen")
    load_smape = live_metrics.get("live_smape_load")
    hours = live_metrics.get("hours")
    avg_cloud = None
    if weather_payload and weather_payload.get("daily_weather"):
        avg_cloud = weather_payload["daily_weather"][0].get("avg_cloud_cover_pct")

    evidence = []
    if gen_smape is not None:
        evidence.append(_evidence("PV sMAPE", _format_number(gen_smape, "%", 2)))
    if load_smape is not None:
        evidence.append(_evidence("Load sMAPE", _format_number(load_smape, "%", 2)))
    if avg_cloud is not None:
        evidence.append(_evidence("Cloud cover", _format_number(avg_cloud, "%", 1)))
    if hours is not None:
        evidence.append(_evidence("Lookback", f"{int(hours)} h"))

    if gen_smape is not None and gen_smape >= 25.0:
        weather_clause = ""
        if avg_cloud is not None and avg_cloud >= 60.0:
            weather_clause = f" Cloudier conditions ({avg_cloud:.0f}% average cloud cover) are also making solar output less predictable."
        return {
            "category": "forecast",
            "severity": "warning",
            "title": "PV forecast uncertainty is elevated",
            "message": (
                f"The generation model is running at {gen_smape:.2f}% sMAPE over the last {int(hours or 24)} hours."
                f"{weather_clause}"
            ),
            "recommendation": "Keep a wider battery reserve and prefer flexible loads near the solar peak until accuracy improves.",
            "evidence": evidence,
        }

    if load_smape is not None and load_smape >= 20.0:
        return {
            "category": "forecast",
            "severity": "warning",
            "title": "Demand behavior has become less predictable",
            "message": (
                f"Recent load error is {load_smape:.2f}% sMAPE, which suggests appliance usage has shifted away from the training pattern."
            ),
            "recommendation": "Retrain the model after more recent usage data accumulates, or keep more conservative schedule margins.",
            "evidence": evidence,
        }

    if gen_smape is not None or load_smape is not None:
        msg_parts = []
        if gen_smape is not None:
            msg_parts.append(f"PV sMAPE is {gen_smape:.2f}%")
        if load_smape is not None:
            msg_parts.append(f"load sMAPE is {load_smape:.2f}%")
        return {
            "category": "forecast",
            "severity": "success",
            "title": "Recent forecast accuracy is within a manageable range",
            "message": f"Over the last {int(hours or 24)} hours, " + " and ".join(msg_parts) + ".",
            "recommendation": "The controller can rely on the current forecast with normal reserve settings.",
            "evidence": evidence,
        }

    mode = "hybrid" if "Hybrid forecast" in (forecast_message or "") else "forecast"
    if model_active is True:
        mode = "LSTM"
    elif model_active is False and "Open-Meteo" in (forecast_message or ""):
        mode = "weather-assisted"

    return {
        "category": "forecast",
        "severity": "info",
        "title": "Forecast explanation is available even without live error history",
        "message": f"The operational {mode} forecast is running, but there is not yet enough overlapping hourly history to compute recent error metrics.",
        "recommendation": "Let the simulator or hardware run longer to unlock live accuracy narratives in the monitor.",
        "evidence": [_evidence("Forecast mode", forecast_message or mode)],
    }


def _solar_outlook_insight(
    weather_payload: Optional[Dict[str, Any]],
    peak_ts: Optional[str],
    peak_kw: float,
    horizon_hours: int,
) -> Optional[Dict[str, Any]]:
    if weather_payload and weather_payload.get("forecast_available") and weather_payload.get("daily_weather"):
        today = weather_payload["daily_weather"][0]
        clouds = today.get("avg_cloud_cover_pct")
        condition = today.get("dominant_weather_label") or "Mixed conditions"
        expected_pv = today.get("expected_pv_kwh")
        evidence = [
            _evidence("Expected PV today", _format_number(expected_pv, "kWh", 2)),
            _evidence("Peak hour", _format_ts(peak_ts)),
            _evidence("Peak power", _format_number(peak_kw, "kW", 2)),
        ]
        if clouds is not None:
            evidence.append(_evidence("Average cloud cover", _format_number(clouds, "%", 1)))

        if clouds is not None and clouds >= 70.0:
            return {
                "category": "weather",
                "severity": "warning",
                "title": "Cloud cover is likely to flatten the solar window",
                "message": (
                    f"{condition} is expected to dominate with about {clouds:.0f}% average cloud cover, "
                    f"so generation may stay concentrated around {_format_ts(peak_ts)} instead of holding a long midday plateau."
                ),
                "recommendation": "Run high-power appliances as close to the peak window as possible instead of spreading them across the afternoon.",
                "evidence": evidence,
            }

        if peak_ts is not None:
            return {
                "category": "weather",
                "severity": "success",
                "title": "The next solar peak gives a clear shifting window",
                "message": (
                    f"Expected PV for the day is about {expected_pv:.2f} kWh, with the strongest output near {_format_ts(peak_ts)} "
                    f"at roughly {peak_kw:.2f} kW."
                ),
                "recommendation": "Use that peak window for water heating, laundry, or other flexible daytime loads.",
                "evidence": evidence,
            }

    if peak_ts is None:
        return None

    return {
        "category": "weather",
        "severity": "info",
        "title": "The forecast includes a usable solar peak window",
        "message": (
            f"Across the next {horizon_hours} hours, generation is expected to peak around {_format_ts(peak_ts)} "
            f"at approximately {peak_kw:.2f} kW."
        ),
        "recommendation": "Concentrate flexible loads near that window to reduce battery cycling.",
        "evidence": [
            _evidence("Peak hour", _format_ts(peak_ts)),
            _evidence("Peak power", _format_number(peak_kw, "kW", 2)),
        ],
    }


def _schedule_alignment_insight(
    schedule_rows: List[Tuple[ScheduleSlot, Appliance]],
    peak_ts: Optional[str],
    latest_soc: Optional[float],
    reserve_floor: float,
    peak_kw: float,
) -> Optional[Dict[str, Any]]:
    if not schedule_rows:
        return {
            "category": "schedule",
            "severity": "info",
            "title": "No scheduled appliance actions are queued yet",
            "message": "The next 24 hours do not contain any future ON slots, so there is nothing for the controller to explain yet.",
            "recommendation": "Run IEBA to populate the schedule before using the narrative schedule panel in your demo.",
            "evidence": [],
        }

    peak_dt = None
    if peak_ts is not None:
        try:
            peak_dt = datetime.fromisoformat(peak_ts.replace("Z", "+00:00"))
        except ValueError:
            peak_dt = None
    if peak_dt is not None:
        peak_dt = _to_utc(peak_dt)

    flexible = [(slot, app) for slot, app in schedule_rows if int(app.priority) >= 3]
    target_rows = flexible or schedule_rows

    if peak_dt is not None and target_rows:
        nearest_slot, nearest_app = min(
            target_rows,
            key=lambda row: abs((_to_utc(row[0].start_ts) - peak_dt).total_seconds()),
        )
        start_dt = _to_utc(nearest_slot.start_ts)
        delta_h = abs((start_dt - peak_dt).total_seconds()) / 3600.0
        evidence = [
            _evidence("Appliance", nearest_app.name),
            _evidence("Scheduled start", _format_ts(start_dt)),
            _evidence("PV peak", _format_ts(peak_dt)),
            _evidence("Expected peak PV", _format_number(peak_kw, "kW", 2)),
        ]
        if delta_h <= 2.0:
            return {
                "category": "schedule",
                "severity": "success",
                "title": "The schedule is already aligning flexible load with solar output",
                "message": (
                    f"{nearest_app.name} is scheduled for {_format_ts(start_dt)}, which is close to the expected PV peak at {_format_ts(peak_dt)}."
                ),
                "recommendation": "This alignment should reduce evening battery discharge and make the schedule easy to defend in your presentation.",
                "evidence": evidence,
            }
        if latest_soc is not None and latest_soc <= reserve_floor + 5.0 and start_dt > peak_dt + timedelta(hours=2):
            return {
                "category": "schedule",
                "severity": "warning",
                "title": "A discretionary load is falling after the strongest solar window",
                "message": (
                    f"{nearest_app.name} starts at {_format_ts(start_dt)}, which is well after the PV peak at {_format_ts(peak_dt)} while SOC is only {latest_soc:.1f}%."
                ),
                "recommendation": "Re-run IEBA or move that appliance closer to the midday solar window to protect battery reserve.",
                "evidence": evidence,
            }

    if latest_soc is not None and latest_soc <= reserve_floor + 5.0 and not flexible:
        return {
            "category": "schedule",
            "severity": "success",
            "title": "The current schedule is protecting battery reserve",
            "message": "There are no low-priority appliance starts queued while battery reserve is tight, which is the right conservative behavior.",
            "recommendation": "Add flexible loads only after the battery has recovered or the weather outlook improves.",
            "evidence": [],
        }

    next_slot, next_app = schedule_rows[0]
    return {
        "category": "schedule",
        "severity": "info",
        "title": "The next scheduled appliance action is ready for explanation",
        "message": f"{next_app.name} is the next appliance planned to turn on at {_format_ts(next_slot.start_ts)}.",
        "recommendation": "Use the solar and battery cards above to explain whether that timing is strategic or should be rescheduled.",
        "evidence": [
            _evidence("Appliance", next_app.name),
            _evidence("Scheduled start", _format_ts(next_slot.start_ts)),
        ],
    }


def _build_summary(insights: List[Dict[str, Any]]) -> str:
    if not insights:
        return "No descriptive insights are available yet."
    if len(insights) == 1:
        return insights[0]["message"]
    lead = insights[0]["message"].rstrip(".")
    follow = insights[1]["message"]
    return f"{lead}. {follow}"
