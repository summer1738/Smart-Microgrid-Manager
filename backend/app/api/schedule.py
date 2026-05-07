"""IEBA schedule API: get schedule and run optimization."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.database import get_db
from app.models import ScheduleSlot
from app.schemas import ScheduleOut
from app.services.schedule_executor_service import apply_schedule
from app.services.schedule_service import get_schedule_out, run_and_persist_schedule

router = APIRouter(
    prefix="/schedule",
    tags=["schedule"],
    dependencies=[Depends(require_min_role("operator"))],
)

@router.get("", response_model=ScheduleOut)
async def get_schedule(db: AsyncSession = Depends(get_db)) -> ScheduleOut:
    """Return current IEBA-generated schedule (future slots only)."""
    now = datetime.now(timezone.utc)
    return await get_schedule_out(db, now=now)


@router.post("/run", response_model=ScheduleOut)
async def run_schedule(db: AsyncSession = Depends(get_db)) -> ScheduleOut:
    """
    Run IEBA: fetch forecast, latest SOC and appliances, solve MILP, persist schedule.
    """
    now = datetime.now(timezone.utc)
    return await run_and_persist_schedule(db, now=now)


@router.post("/apply")
async def apply_schedule_now(db: AsyncSession = Depends(get_db)):
    """
    Apply the current IEBA schedule for "now": set Appliance.is_on from active slots
    and mark those slots as applied. In simulation the next /status tick will use these states.
    """
    slots_applied, appliances_updated = await apply_schedule(db)
    return {"slots_applied": slots_applied, "appliances_updated": appliances_updated}
