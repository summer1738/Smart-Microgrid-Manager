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
            loads_out = []
            for load in reading["loads"]:
                r = await db.execute(select(Appliance).where(Appliance.external_id == load["appliance_id"]))
                app = r.scalar_one_or_none()
                name = app.name if app else load["appliance_id"]
                loads_out.append(LoadSnapshot(
                    appliance_id=load["appliance_id"],
                    name=name,
                    power_kw=load["power_kw"],
                    state=load["state"],
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
        for lr, app in load_rows.all():
            if app.id in seen:
                continue
            seen.add(app.id)
            loads_out.append(LoadSnapshot(
                appliance_id=app.external_id,
                name=app.name,
                power_kw=lr.power_kw,
                state=lr.state,
            ))
            total += lr.power_kw
        ts = datetime.now(timezone.utc)
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
    for lr, app in load_rows.scalars().all():
        if app.id in seen:
            continue
        seen.add(app.id)
        loads_out.append(LoadSnapshot(
            appliance_id=app.external_id,
            name=app.name,
            power_kw=lr.power_kw,
            state=lr.state,
        ))
        total += lr.power_kw
    ts = datetime.now(timezone.utc)
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
        )
        for ts in timestamps
    ]
    return StatusHistoryOut(points=points, hours=hours)
