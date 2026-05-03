"""IEBA schedule API: get schedule and run optimization."""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.database import get_db
from app.models import Appliance, BatteryReading, ScheduleSlot
from app.schemas import ScheduleOut, ScheduleSlotOut
from app.services.forecast_service import generate_hybrid_forecast
from app.services.ieba_service import run_ieba
from app.services.schedule_executor_service import apply_schedule
from app.services.system_settings_service import ensure_system_settings_row

router = APIRouter(
    prefix="/schedule",
    tags=["schedule"],
    dependencies=[Depends(require_min_role("operator"))],
)

HORIZON_HOURS = 24
RESOLUTION_HOURS = 1.0


@router.get("", response_model=ScheduleOut)
async def get_schedule(db: AsyncSession = Depends(get_db)) -> ScheduleOut:
    """Return current IEBA-generated schedule (future slots only)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleSlot, Appliance)
        .join(Appliance, ScheduleSlot.appliance_id == Appliance.id)
        .where(ScheduleSlot.start_ts >= now)
        .order_by(ScheduleSlot.start_ts)
        .limit(500)
    )
    slots: List[ScheduleSlotOut] = []
    for slot, app in result.all():
        slots.append(ScheduleSlotOut(
            appliance_id=slot.appliance_id,
            appliance_name=app.name,
            start_ts=slot.start_ts,
            end_ts=slot.end_ts,
            planned_state=slot.planned_state,
            status=slot.status,
        ))
    return ScheduleOut(
        generated_at=now,
        slots=slots,
        message=None if slots else "No schedule yet. POST /schedule/run to run IEBA.",
    )


@router.post("/run", response_model=ScheduleOut)
async def run_schedule(db: AsyncSession = Depends(get_db)) -> ScheduleOut:
    """
    Run IEBA: fetch forecast, latest SOC and appliances, solve MILP, persist schedule.
    """
    now = datetime.now(timezone.utc)

    # Latest battery SOC
    r = await db.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
    bat = r.scalar_one_or_none()
    initial_soc = bat.soc_percent if bat else 70.0

    # Microgrid sizing (from DB settings; seeded defaults on first run)
    sys_row = await ensure_system_settings_row(db)
    capacity_kwh = float(sys_row.battery_capacity_kwh)
    soc_min_percent = float(sys_row.soc_min_percent)
    inverter_capacity_kw = float(sys_row.inverter_capacity_kw)

    # Appliances
    r = await db.execute(select(Appliance).order_by(Appliance.priority, Appliance.id))
    appliances_db = [a for a in r.scalars().all() if getattr(a, "usage_mode", "scheduled") != "on_demand"]
    if not appliances_db:
        raise HTTPException(400, "No scheduled appliances registered. Add scheduled appliances first.")
    appliances = [
        {
            "id": a.external_id,
            "db_id": a.id,
            "name": a.name,
            "priority": a.priority,
            "rated_watts": float(a.rated_watts),
            "schedule_prefs": a.schedule_prefs,
        }
        for a in appliances_db
    ]

    # Forecast (hybrid: PV from weather when enabled; demand from LSTM when available)
    timestamps, generation_kw, consumption_kw, _forecast_msg = await generate_hybrid_forecast(
        horizon_hours=HORIZON_HOURS,
        resolution_hours=RESOLUTION_HOURS,
        base_ts=now,
    )

    # Solve IEBA
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

    # Delete future slots and insert new ones
    await db.execute(delete(ScheduleSlot).where(ScheduleSlot.start_ts >= now))
    for s in raw_slots:
        db_id = s.get("appliance_db_id")
        if db_id is None:
            continue
        slot = ScheduleSlot(
            appliance_id=db_id,
            start_ts=s["start_ts"],
            end_ts=s["end_ts"],
            planned_state=s["planned_state"],
            status=s.get("status", "pending"),
        )
        db.add(slot)
    await db.flush()

    # Return same shape as GET
    result = await db.execute(
        select(ScheduleSlot, Appliance)
        .join(Appliance, ScheduleSlot.appliance_id == Appliance.id)
        .where(ScheduleSlot.start_ts >= now)
        .order_by(ScheduleSlot.start_ts)
        .limit(500)
    )
    out_slots = []
    for slot, app in result.all():
        out_slots.append(ScheduleSlotOut(
            appliance_id=slot.appliance_id,
            appliance_name=app.name,
            start_ts=slot.start_ts,
            end_ts=slot.end_ts,
            planned_state=slot.planned_state,
            status=slot.status,
        ))
    return ScheduleOut(generated_at=now, slots=out_slots, message=None)


@router.post("/apply")
async def apply_schedule_now(db: AsyncSession = Depends(get_db)):
    """
    Apply the current IEBA schedule for "now": set Appliance.is_on from active slots
    and mark those slots as applied. In simulation the next /status tick will use these states.
    """
    slots_applied, appliances_updated = await apply_schedule(db)
    return {"slots_applied": slots_applied, "appliances_updated": appliances_updated}
