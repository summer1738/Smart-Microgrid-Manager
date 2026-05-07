"""Shared IEBA schedule generation/persistence logic for API and background automation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appliance, BatteryReading, ScheduleSlot
from app.schemas import ScheduleOut, ScheduleSlotOut
from app.services.forecast_service import generate_hybrid_forecast
from app.services.ieba_service import run_ieba
from app.services.system_settings_service import ensure_system_settings_row

HORIZON_HOURS = 24
RESOLUTION_HOURS = 1.0


async def run_and_persist_schedule(
    db: AsyncSession,
    now: datetime | None = None,
) -> ScheduleOut:
    """
    Run IEBA and replace future schedule slots. Manual overrides are treated as fixed states.
    """
    now = now or datetime.now(timezone.utc)

    r = await db.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
    bat = r.scalar_one_or_none()
    initial_soc = bat.soc_percent if bat else 70.0

    sys_row = await ensure_system_settings_row(db)
    capacity_kwh = float(sys_row.battery_capacity_kwh)
    soc_min_percent = float(sys_row.soc_min_percent)
    inverter_capacity_kw = float(sys_row.inverter_capacity_kw)

    r = await db.execute(select(Appliance).order_by(Appliance.priority, Appliance.id))
    appliances_db = [a for a in r.scalars().all() if getattr(a, "usage_mode", "scheduled") != "on_demand"]
    if not appliances_db:
        raise HTTPException(400, "No scheduled appliances registered. Add scheduled appliances first.")

    appliances: List[Dict[str, Any]] = []
    for a in appliances_db:
        appliance_payload: Dict[str, Any] = {
            "id": a.external_id,
            "db_id": a.id,
            "name": a.name,
            "priority": a.priority,
            "rated_watts": float(a.rated_watts),
            "schedule_prefs": a.schedule_prefs,
        }
        if bool(getattr(a, "manual_override_active", False)):
            appliance_payload["fixed_state"] = bool(a.is_on)
        appliances.append(appliance_payload)

    _timestamps, generation_kw, consumption_kw, _forecast_msg = await generate_hybrid_forecast(
        horizon_hours=HORIZON_HOURS,
        resolution_hours=RESOLUTION_HOURS,
        base_ts=now,
    )

    raw_slots = run_ieba(
        forecast_generation_kw=generation_kw,
        forecast_consumption_kw=consumption_kw,
        appliances=appliances,
        initial_soc_percent=initial_soc,
        capacity_kwh=capacity_kwh,
        soc_min_percent=soc_min_percent,
        time_resolution_hours=RESOLUTION_HOURS,
        base_ts=now,
        inverter_capacity_kw=inverter_capacity_kw,
    )

    await db.execute(delete(ScheduleSlot).where(ScheduleSlot.start_ts >= now))
    for s in raw_slots:
        db_id = s.get("appliance_db_id")
        if db_id is None:
            continue
        db.add(
            ScheduleSlot(
                appliance_id=db_id,
                start_ts=s["start_ts"],
                end_ts=s["end_ts"],
                planned_state=s["planned_state"],
                status=s.get("status", "pending"),
            )
        )
    await db.flush()
    return await get_schedule_out(db, now=now)


async def get_schedule_out(db: AsyncSession, now: datetime | None = None) -> ScheduleOut:
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleSlot, Appliance)
        .join(Appliance, ScheduleSlot.appliance_id == Appliance.id)
        .where(ScheduleSlot.start_ts >= now)
        .order_by(ScheduleSlot.start_ts)
        .limit(500)
    )
    slots: List[ScheduleSlotOut] = []
    for slot, app in result.all():
        slots.append(
            ScheduleSlotOut(
                appliance_id=slot.appliance_id,
                appliance_name=app.name,
                start_ts=slot.start_ts,
                end_ts=slot.end_ts,
                planned_state=slot.planned_state,
                status=slot.status,
            )
        )
    return ScheduleOut(
        generated_at=now,
        slots=slots,
        message=None if slots else "No schedule yet. POST /schedule/run to run IEBA.",
    )
