"""CRUD API for appliances (UCLPI)."""
from typing import List
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Appliance
from app.schemas import ApplianceCreate, ApplianceOut, ApplianceUpdate

router = APIRouter(prefix="/appliances", tags=["appliances"])


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
