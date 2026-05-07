"""
Schedule executor: apply current IEBA schedule to appliance states (and later to relays/MQTT).
"""
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Appliance, ScheduleSlot
from app.services.mqtt_ingest_service import publish_relay_command


async def apply_schedule(session: AsyncSession, now: Optional[datetime] = None) -> Tuple[int, int]:
    """
    Apply the latest due pending slot for each appliance.

    Expired pending rows are marked as skipped so missed controller ticks do not
    leave stale schedule rows behind. The newest still-active pending row per
    appliance is applied.

    Returns (slots_applied, appliances_updated).
    """
    now = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(ScheduleSlot)
        .where(
            and_(
                ScheduleSlot.start_ts <= now,
                ScheduleSlot.status == "pending",
            )
        )
        .order_by(ScheduleSlot.appliance_id, ScheduleSlot.start_ts.desc())
    )
    slots = list(result.scalars().all())
    if not slots:
        return 0, 0

    active_slots: list[ScheduleSlot] = []
    seen_appliance_ids: set[int] = set()
    for slot in slots:
        # Ensure slot.end_ts is timezone-aware for comparison
        end_ts = slot.end_ts
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=timezone.utc)
        if end_ts <= now:
            slot.status = "skipped"
            continue
        if slot.appliance_id in seen_appliance_ids:
            slot.status = "skipped"
            continue
        seen_appliance_ids.add(slot.appliance_id)
        active_slots.append(slot)

    if not active_slots:
        await session.flush()
        return 0, 0

    # Group by appliance_id; take latest planned_state if multiple slots are due.
    app_id_to_state: dict[int, str] = {}
    for slot in active_slots:
        app_id_to_state[slot.appliance_id] = slot.planned_state

    # Update appliances
    r = await session.execute(select(Appliance).where(Appliance.id.in_(app_id_to_state)))
    appliances = {a.id: a for a in r.scalars().all()}
    updated = 0
    for app_id, planned_state in app_id_to_state.items():
        app = appliances.get(app_id)
        if app is None:
            continue
        if bool(getattr(app, "manual_override_active", False)):
            continue
        new_on = planned_state.lower() == "on"
        if app.is_on != new_on:
            app.is_on = new_on
            updated += 1
            if not settings.use_hardware_simulation:
                await publish_relay_command(app.external_id, new_on)

    # Mark chosen active rows as applied.
    for slot in active_slots:
        slot.status = "applied"

    await session.flush()
    return len(active_slots), updated
