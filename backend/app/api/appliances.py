"""CRUD API for appliances (UCLPI)."""
from datetime import datetime, timedelta, timezone
from typing import List
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.database import get_db
from app.models import Appliance, BatteryReading, LoadReading, PvReading, ScheduleSlot
from app.schemas import ApplianceCreate, ApplianceOut, ApplianceRunDecisionOut, ApplianceRunRequest, ApplianceUpdate
from app.services.forecast_service import generate_hybrid_forecast
from app.services.system_settings_service import ensure_system_settings_row

router = APIRouter(
    prefix="/appliances",
    tags=["appliances"],
    dependencies=[Depends(require_min_role("operator"))],
)


async def _recommend_start_time(
    now: datetime,
    requested_kw: float,
    inverter_capacity_kw: float,
    current_total_load_kw: float,
    soc: float,
    soc_min_percent: float,
) -> datetime | None:
    """
    Look ahead up to 24h and return the earliest safer slot for an on-demand appliance.
    We use forecast PV and a simple current-load baseline to estimate headroom.
    """
    try:
        timestamps, generation_kw, _consumption_kw, _msg = await generate_hybrid_forecast(
            horizon_hours=24,
            resolution_hours=1.0,
            base_ts=now,
        )
    except Exception:
        return None

    # Keep it conservative: assume present load baseline remains similar.
    baseline_load_kw = max(0.0, float(current_total_load_kw))
    for i, pv_kw in enumerate(generation_kw):
        headroom_kw = max(0.0, float(inverter_capacity_kw) - baseline_load_kw)
        enough_pv = float(pv_kw) >= baseline_load_kw + requested_kw
        enough_inverter = headroom_kw >= requested_kw
        enough_soc = soc > soc_min_percent + 3.0
        if enough_inverter and (enough_pv or enough_soc):
            return now + timedelta(hours=i)
    return None


@router.get("", response_model=List[ApplianceOut])
async def list_appliances(db: AsyncSession = Depends(get_db)) -> List[ApplianceOut]:
    result = await db.execute(select(Appliance).order_by(Appliance.priority, Appliance.id))
    return list(result.scalars().all())


@router.post("", response_model=ApplianceOut, status_code=201)
async def create_appliance(
    body: ApplianceCreate,
    db: AsyncSession = Depends(get_db),
) -> ApplianceOut:
    # Generate external_id if not provided: slugified name + short random suffix.
    ext_id = body.external_id
    if not ext_id:
        base = re.sub(r"[^a-z0-9]+", "_", body.name.strip().lower())
        base = base.strip("_") or "appliance"
        suffix = secrets.token_hex(3)
        ext_id = f"{base}_{suffix}"
    r = await db.execute(select(Appliance).where(Appliance.external_id == ext_id))
    if r.scalar_one_or_none() is not None:
        raise HTTPException(400, "Appliance with this external_id already exists")
    # Default user id 1 for simulation
    app = Appliance(
        user_id=1,
        external_id=ext_id,
        name=body.name,
        priority=body.priority,
        rated_watts=body.rated_watts,
        usage_mode=body.usage_mode,
        default_run_minutes=body.default_run_minutes,
        schedule_prefs=body.schedule_prefs,
        relay_topic=body.relay_topic,
    )
    db.add(app)
    await db.flush()
    await db.refresh(app)
    return app


@router.get("/{appliance_id}", response_model=ApplianceOut)
async def get_appliance(
    appliance_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApplianceOut:
    r = await db.execute(select(Appliance).where(Appliance.id == appliance_id))
    app = r.scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Appliance not found")
    return app


@router.patch("/{appliance_id}", response_model=ApplianceOut)
async def update_appliance(
    appliance_id: int,
    body: ApplianceUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApplianceOut:
    r = await db.execute(select(Appliance).where(Appliance.id == appliance_id))
    app = r.scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Appliance not found")
    if body.name is not None:
        app.name = body.name
    if body.priority is not None:
        app.priority = body.priority
    if body.rated_watts is not None:
        app.rated_watts = body.rated_watts
    if body.usage_mode is not None:
        app.usage_mode = body.usage_mode
    if body.default_run_minutes is not None:
        app.default_run_minutes = body.default_run_minutes
    if body.schedule_prefs is not None:
        app.schedule_prefs = body.schedule_prefs
    if body.relay_topic is not None:
        app.relay_topic = body.relay_topic
    if body.is_on is not None:
        app.is_on = body.is_on
    await db.flush()
    await db.refresh(app)
    return app


@router.delete("/{appliance_id}", status_code=204)
async def delete_appliance(
    appliance_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    r = await db.execute(select(Appliance).where(Appliance.id == appliance_id))
    app = r.scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Appliance not found")
    await db.delete(app)
    return None


@router.post("/{appliance_id}/request-run", response_model=ApplianceRunDecisionOut)
async def request_run_appliance(
    appliance_id: int,
    body: ApplianceRunRequest,
    db: AsyncSession = Depends(get_db),
) -> ApplianceRunDecisionOut:
    now = datetime.now(timezone.utc)
    r = await db.execute(select(Appliance).where(Appliance.id == appliance_id))
    app = r.scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Appliance not found")
    if app.usage_mode != "on_demand":
        raise HTTPException(400, "This appliance is not configured as on-demand.")

    bat = await db.execute(select(BatteryReading).order_by(desc(BatteryReading.timestamp)).limit(1))
    bat_row = bat.scalar_one_or_none()
    pv = await db.execute(select(PvReading).order_by(desc(PvReading.timestamp)).limit(1))
    pv_row = pv.scalar_one_or_none()
    load_agg = await db.execute(select(LoadReading.timestamp, LoadReading.power_kw).order_by(desc(LoadReading.timestamp)).limit(200))
    latest_by_ts = {}
    for ts, kw in load_agg.all():
        latest_by_ts.setdefault(ts, []).append(float(kw))
    current_total_load_kw = sum(next(iter(latest_by_ts.values()), []))

    sys_row = await ensure_system_settings_row(db)
    inverter_capacity_kw = float(sys_row.inverter_capacity_kw)
    soc_min_percent = float(sys_row.soc_min_percent)

    pv_kw = float(pv_row.power_kw) if pv_row else 0.0
    soc = float(bat_row.soc_percent) if bat_row else 0.0
    requested_kw = float(app.rated_watts) / 1000.0
    headroom_kw = max(0.0, inverter_capacity_kw - current_total_load_kw)

    if soc <= soc_min_percent and pv_kw < current_total_load_kw + requested_kw:
        return ApplianceRunDecisionOut(
            ok=False,
            appliance_id=app.id,
            appliance_name=app.name,
            decision="rejected",
            message="Battery is at or below the minimum SOC and current PV is not enough for this on-demand load.",
            duration_minutes=body.duration_minutes,
        )

    if headroom_kw >= requested_kw and (pv_kw >= current_total_load_kw + requested_kw or soc > soc_min_percent + 5):
        end_ts = now + timedelta(minutes=body.duration_minutes)
        # Remove overlapping future slots for this appliance in the request window.
        await db.execute(
            delete(ScheduleSlot).where(
                and_(
                    ScheduleSlot.appliance_id == app.id,
                    ScheduleSlot.end_ts > now,
                    ScheduleSlot.start_ts < end_ts,
                )
            )
        )
        db.add(ScheduleSlot(appliance_id=app.id, start_ts=now, end_ts=end_ts, planned_state="on", status="pending"))
        db.add(ScheduleSlot(appliance_id=app.id, start_ts=end_ts, end_ts=end_ts + timedelta(hours=1), planned_state="off", status="pending"))
        app.is_on = True
        await db.flush()
        return ApplianceRunDecisionOut(
            ok=True,
            appliance_id=app.id,
            appliance_name=app.name,
            decision="approved_now",
            message="Approved. Appliance can run now for the requested duration.",
            duration_minutes=body.duration_minutes,
            scheduled_start_ts=now,
            scheduled_end_ts=end_ts,
        )

    recommended = await _recommend_start_time(
        now=now,
        requested_kw=requested_kw,
        inverter_capacity_kw=inverter_capacity_kw,
        current_total_load_kw=current_total_load_kw,
        soc=soc,
        soc_min_percent=soc_min_percent,
    )
    return ApplianceRunDecisionOut(
        ok=False,
        appliance_id=app.id,
        appliance_name=app.name,
        decision="deferred",
        message=(
            "Not enough safe headroom right now. "
            + (
                f"Best recommended start: {recommended.isoformat()}."
                if recommended is not None
                else "No suitable slot found in the next 24 hours."
            )
        ),
        duration_minutes=body.duration_minutes,
        recommended_start_ts=recommended,
    )
