"""
Schedule executor: apply current IEBA schedule to appliance states (and later to relays/MQTT).
"""
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appliance, ScheduleSlot


async def apply_schedule(session: AsyncSession, now: Optional[datetime] = None) -> Tuple[int, int]:
    """
    Find schedule slots that are active now (start_ts <= now < end_ts), update
    Appliance.is_on from planned_state, and mark those slots as "applied".
    Returns (slots_applied, appliances_updated).
    """
    now = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(ScheduleSlot)
        .where(
            and_(
                ScheduleSlot.start_ts <= now,
                ScheduleSlot.end_ts > now,
                ScheduleSlot.status == "pending",
            )
        )
    )
    slots = list(result.scalars().all())
    if not slots:
        return 0, 0

    # Group by appliance_id; take latest planned_state if multiple slots (should be one per period)
    app_id_to_state: dict[int, str] = {}
    for slot in slots:
        app_id_to_state[slot.appliance_id] = slot.planned_state

    # Update appliances
    r = await session.execute(select(Appliance).where(Appliance.id.in_(app_id_to_state)))
    appliances = {a.id: a for a in r.scalars().all()}
    updated = 0
    for app_id, planned_state in app_id_to_state.items():
        app = appliances.get(app_id)
        if app is None:
            continue
        new_on = planned_state.lower() == "on"
        if app.is_on != new_on:
            app.is_on = new_on
            updated += 1

    # Mark slots as applied
    for slot in slots:
        slot.status = "applied"

    return len(slots), updated
