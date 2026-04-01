"""Live status and history from simulator or real hardware."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Appliance, BatteryReading, LoadReading, PvReading
from app.schemas import BatterySnapshot, HistoryPoint, LoadSnapshot, PvSnapshot, StatusHistoryOut, StatusOut
from app.services.schedule_executor_service import apply_schedule
from app.services.simulator_service import tick_simulator_and_persist

router = APIRouter(prefix="/status", tags=["status"])


FULL_BATTERY_SOC_PERCENT = 99.5
UNEXPECTED_LOAD_THRESHOLD_KW = 0.03


def _available_export_kw(pv_kw: float, total_load_kw: float, soc_percent: float) -> float:
    """
    Surplus generation available for grid export only after:
    1. current load has been served, and
    2. the battery is effectively full.
    """
    if float(soc_percent) < FULL_BATTERY_SOC_PERCENT:
        return 0.0
    return round(max(0.0, float(pv_kw) - float(total_load_kw)), 4)


def _battery_status(pv_kw: float, total_load_kw: float, soc_percent: float, battery_current_a: float) -> tuple[bool, str, str]:
    """
    Determine whether the battery is charging and whether the dashboard should warn.
    Levels: success / warning / neutral
    """
    current_a = float(battery_current_a)
    soc = float(soc_percent)
    pv = float(pv_kw)
    load = float(total_load_kw)

    if soc >= FULL_BATTERY_SOC_PERCENT:
        if pv > load:
            return False, "Battery full. Extra PV can be exported.", "neutral"
        return False, "Battery full.", "neutral"
    if current_a > 0.5:
        return True, f"Charging at {current_a:.1f} A.", "success"
    if pv <= 0.05:
        return False, "Warning: battery is not charging because PV generation is too low.", "warning"
    if pv <= load:
        return False, "Warning: battery is not charging because all PV is being used by the load.", "warning"
    return False, "Warning: battery is not charging.", "warning"


def _manual_override_flag(expected_on: bool, measured_power_kw: float, measured_state: str) -> bool:
    if expected_on:
        return False
    state_on = str(measured_state).lower() == "on"
    return state_on or float(measured_power_kw) > UNEXPECTED_LOAD_THRESHOLD_KW


@router.get("", response_model=StatusOut)
async def get_status(db: AsyncSession = Depends(get_db)) -> StatusOut:
    """
    Return latest system status. In simulation mode, runs one simulator tick
    and then returns the latest readings (so each request advances simulated time).
    """
    if settings.use_hardware_simulation:
        # If controller loop is enabled, it is already advancing simulation.
        # If not, we can advance one tick per request (legacy behavior).
        if settings.controller_tick_on_status_request:
            await apply_schedule(db)
            reading = await tick_simulator_and_persist(db)
            ts = datetime.fromisoformat(reading["timestamp"].replace("Z", "+00:00"))
            battery_is_charging, battery_status_label, battery_status_level = _battery_status(
                reading["pv"]["power_kw"],
                reading["total_load_kw"],
                reading["battery"]["soc_percent"],
                reading["battery"]["current_a"],
            )
            loads_out = []
            manual_override_messages = []
            for load in reading["loads"]:
                r = await db.execute(select(Appliance).where(Appliance.external_id == load["appliance_id"]))
                app = r.scalar_one_or_none()
                name = app.name if app else load["appliance_id"]
                unexpected_override = _manual_override_flag(
                    bool(app.is_on) if app else True,
                    float(load["power_kw"]),
                    str(load["state"]),
                )
                if unexpected_override:
                    manual_override_messages.append(f"{name} appears to be ON outside the planned schedule.")
                loads_out.append(LoadSnapshot(
                    appliance_id=load["appliance_id"],
                    name=name,
                    power_kw=load["power_kw"],
                    state=load["state"],
                    unexpected_override=unexpected_override,
                ))
            return StatusOut(
                timestamp=ts,
                pv=PvSnapshot(
                    power_kw=reading["pv"]["power_kw"],
                    voltage=reading["pv"]["voltage"],
                    current_a=reading["pv"]["current_a"],
                    timestamp=ts,
                ),
                battery=BatterySnapshot(
                    soc_percent=reading["battery"]["soc_percent"],
                    voltage=reading["battery"]["voltage"],
                    current_a=reading["battery"]["current_a"],
                    timestamp=ts,
                ),
                loads=loads_out,
                total_load_kw=reading["total_load_kw"],
                available_export_kw=_available_export_kw(
                    reading["pv"]["power_kw"],
                    reading["total_load_kw"],
                    reading["battery"]["soc_percent"],
                ),
                battery_is_charging=battery_is_charging,
                battery_status_label=battery_status_label,
                battery_status_level=battery_status_level,
                manual_override_detected=bool(manual_override_messages),
                manual_override_messages=manual_override_messages,
                simulated=True,
            )

        # Controller loop mode: read latest from DB (same as hardware path)
        pv = await db.execute(select(PvReading).order_by(desc(PvReading.timestamp)).limit(1))
        pv_row = pv.scalar_one_or_none()
        bat = await db.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
        bat_row = bat.scalar_one_or_none()
        load_rows = await db.execute(
            select(LoadReading, Appliance)
            .join(Appliance, LoadReading.appliance_id == Appliance.id)
            .order_by(desc(LoadReading.timestamp))
        )
        seen = set()
        loads_out = []
        total = 0.0
        manual_override_messages = []
        for lr, app in load_rows.all():
            if app.id in seen:
                continue
            seen.add(app.id)
            unexpected_override = _manual_override_flag(bool(app.is_on), float(lr.power_kw), str(lr.state))
            if unexpected_override:
                manual_override_messages.append(f"{app.name} appears to be ON outside the planned schedule.")
            loads_out.append(LoadSnapshot(
                appliance_id=app.external_id,
                name=app.name,
                power_kw=lr.power_kw,
                state=lr.state,
                unexpected_override=unexpected_override,
            ))
            total += lr.power_kw
        ts = datetime.now(timezone.utc)
        battery_is_charging, battery_status_label, battery_status_level = _battery_status(
            pv_row.power_kw if pv_row else 0,
            total,
            bat_row.soc_percent if bat_row else 0,
            bat_row.current_a if bat_row else 0,
        )
        return StatusOut(
            timestamp=pv_row.timestamp if pv_row else ts,
            pv=PvSnapshot(
                power_kw=pv_row.power_kw if pv_row else 0,
                voltage=pv_row.voltage if pv_row else 0,
                current_a=pv_row.current_a if pv_row else 0,
                timestamp=pv_row.timestamp if pv_row else ts,
            ),
            battery=BatterySnapshot(
                soc_percent=bat_row.soc_percent if bat_row else 0,
                voltage=bat_row.voltage if bat_row else 0,
                current_a=bat_row.current_a if bat_row else 0,
                timestamp=bat_row.timestamp if bat_row else ts,
            ),
            loads=loads_out,
            total_load_kw=total,
            available_export_kw=_available_export_kw(
                pv_row.power_kw if pv_row else 0,
                total,
                bat_row.soc_percent if bat_row else 0,
            ),
            battery_is_charging=battery_is_charging,
            battery_status_label=battery_status_label,
            battery_status_level=battery_status_level,
            manual_override_detected=bool(manual_override_messages),
            manual_override_messages=manual_override_messages,
            simulated=True,
        )

    # Real hardware: read latest from DB
    pv = await db.execute(select(PvReading).order_by(desc(PvReading.timestamp)).limit(1))
    pv_row = pv.scalar_one_or_none()
    bat = await db.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
    bat_row = bat.scalar_one_or_none()
    load_rows = await db.execute(
        select(LoadReading, Appliance)
        .join(Appliance, LoadReading.appliance_id == Appliance.id)
        .order_by(desc(LoadReading.timestamp))
    )
    # Deduplicate by appliance (latest per appliance)
    seen = set()
    loads_out = []
    total = 0.0
    manual_override_messages = []
    for lr, app in load_rows.all():
        if app.id in seen:
            continue
        seen.add(app.id)
        unexpected_override = _manual_override_flag(bool(app.is_on), float(lr.power_kw), str(lr.state))
        if unexpected_override:
            manual_override_messages.append(f"{app.name} appears to be ON outside the planned schedule.")
        loads_out.append(LoadSnapshot(
            appliance_id=app.external_id,
            name=app.name,
            power_kw=lr.power_kw,
            state=lr.state,
            unexpected_override=unexpected_override,
        ))
        total += lr.power_kw
    ts = datetime.now(timezone.utc)
    battery_is_charging, battery_status_label, battery_status_level = _battery_status(
        pv_row.power_kw if pv_row else 0,
        total,
        bat_row.soc_percent if bat_row else 0,
        bat_row.current_a if bat_row else 0,
    )
    return StatusOut(
        timestamp=pv_row.timestamp if pv_row else ts,
        pv=PvSnapshot(
            power_kw=pv_row.power_kw if pv_row else 0,
            voltage=pv_row.voltage if pv_row else 0,
            current_a=pv_row.current_a if pv_row else 0,
            timestamp=pv_row.timestamp if pv_row else ts,
        ),
        battery=BatterySnapshot(
            soc_percent=bat_row.soc_percent if bat_row else 0,
            voltage=bat_row.voltage if bat_row else 0,
            current_a=bat_row.current_a if bat_row else 0,
            timestamp=bat_row.timestamp if bat_row else ts,
        ),
        loads=loads_out,
        total_load_kw=total,
        available_export_kw=_available_export_kw(
            pv_row.power_kw if pv_row else 0,
            total,
            bat_row.soc_percent if bat_row else 0,
        ),
        battery_is_charging=battery_is_charging,
        battery_status_label=battery_status_label,
        battery_status_level=battery_status_level,
        manual_override_detected=bool(manual_override_messages),
        manual_override_messages=manual_override_messages,
        simulated=False,
    )


@router.get("/history", response_model=StatusHistoryOut)
async def get_status_history(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
) -> StatusHistoryOut:
    """
    Return time-series of PV, battery SOC, and total load for the last `hours` hours.
    Aligned by timestamp (one point per simulator tick). For dashboard charts and LSTM export.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    # Get battery readings (one per tick) and join PV + load for same timestamp
    bat = await db.execute(
        select(BatteryReading.timestamp, BatteryReading.soc_percent)
        .where(BatteryReading.timestamp >= since)
        .order_by(BatteryReading.timestamp)
    )
    battery_rows = bat.all()
    if not battery_rows:
        return StatusHistoryOut(points=[], hours=hours)
    timestamps = [r[0] for r in battery_rows]
    soc_by_ts = {r[0]: r[1] for r in battery_rows}
    pv_by_ts = {}
    pv_readings = await db.execute(
        select(PvReading.timestamp, PvReading.power_kw).where(PvReading.timestamp >= since)
    )
    for ts, kw in pv_readings.all():
        pv_by_ts[ts] = kw
    load_by_ts = {}
    load_agg = await db.execute(
        select(LoadReading.timestamp, func.sum(LoadReading.power_kw))
        .where(LoadReading.timestamp >= since)
        .group_by(LoadReading.timestamp)
    )
    for ts, kw in load_agg.all():
        load_by_ts[ts] = float(kw) if kw is not None else 0.0
    points = [
        HistoryPoint(
            timestamp=ts,
            power_kw=pv_by_ts.get(ts),
            soc_percent=soc_by_ts.get(ts),
            total_load_kw=load_by_ts.get(ts),
            available_export_kw=_available_export_kw(
                pv_by_ts.get(ts) or 0.0,
                load_by_ts.get(ts) or 0.0,
                soc_by_ts.get(ts) or 0.0,
            ),
        )
        for ts in timestamps
    ]
    return StatusHistoryOut(points=points, hours=hours)
