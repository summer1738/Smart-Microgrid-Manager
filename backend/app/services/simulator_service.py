"""
Runs the hardware simulator and writes readings to the database.
Used when use_hardware_simulation=True (no physical ESP32/MQTT).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, normalize_username
from app.models import Appliance, BatteryReading, LoadReading, PvReading, User

# Simulator lives at project root (smart-microgrid-manager/simulator). Run backend with:
#   cd backend && PYTHONPATH=.. uvicorn app.main:app --reload
from simulator.simulator import HardwareSimulator, default_appliances


_simulator: Optional[HardwareSimulator] = None


DEFAULT_DEV_USERS = (
    {
        "name": "Default User",
        "username": "admin",
        "role": "admin",
        "password": "admin123",
    },
    {
        "name": "Site Operator",
        "username": "operator",
        "role": "operator",
        "password": "operator123",
    },
    {
        "name": "Dashboard Viewer",
        "username": "viewer",
        "role": "viewer",
        "password": "viewer123",
    },
)


def get_simulator() -> HardwareSimulator:
    global _simulator
    if _simulator is None:
        _simulator = HardwareSimulator(
            pv_capacity_kw=1.0,
            battery_capacity_kwh=2.4,
            initial_soc_percent=70.0,
            appliances=default_appliances(),
            cloud_factor=0.9,
        )
    return _simulator


async def ensure_default_user_and_appliances(session: AsyncSession) -> None:
    """Create default user and appliances if DB is empty (for simulation)."""
    result = await session.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        return
    user = User(
        name="Default User",
        username="admin",
        password_hash=hash_password("admin123"),
        is_active=True,
        role="admin",
    )
    session.add(user)
    await session.flush()
    for spec in default_appliances():
        app = Appliance(
            user_id=user.id,
            external_id=spec["id"],
            name=spec["name"],
            priority=spec["priority"],
            rated_watts=float(spec["rated_watts"]),
        )
        session.add(app)
    await session.flush()


async def ensure_demo_role_users(session: AsyncSession) -> None:
    """Add operator and viewer demo accounts without clobbering existing rows."""
    for spec in DEFAULT_DEV_USERS[1:]:
        result = await session.execute(select(User).where(User.username == spec["username"]))
        if result.scalar_one_or_none() is None:
            session.add(
                User(
                    name=spec["name"],
                    username=spec["username"],
                    password_hash=hash_password(spec["password"]),
                    is_active=True,
                    role=spec["role"],
                )
            )
    await session.flush()


async def ensure_auth_seed_users(session: AsyncSession) -> None:
    """
    Backfill usernames/passwords for older rows so they can participate in session auth.
    """
    rows = list((await session.execute(select(User).order_by(User.id))).scalars().all())
    claimed_usernames = {u.username for u in rows if u.username}

    def unique_username(base: str) -> str:
        candidate = normalize_username(base) or "user"
        if candidate not in claimed_usernames:
            claimed_usernames.add(candidate)
            return candidate
        i = 2
        while f"{candidate}{i}" in claimed_usernames:
            i += 1
        resolved = f"{candidate}{i}"
        claimed_usernames.add(resolved)
        return resolved

    for user in rows:
        matched = next((spec for spec in DEFAULT_DEV_USERS if spec["name"] == user.name), None)
        if matched is not None:
            if not user.username:
                user.username = matched["username"]
            claimed_usernames.add(user.username)
            if not user.password_hash:
                user.password_hash = hash_password(matched["password"])
            if user.is_active is None:
                user.is_active = True
            if not user.role or user.role == "user":
                user.role = matched["role"]
            continue

        if not user.username:
            user.username = unique_username(user.name.replace(" ", "_"))
        if not user.password_hash:
            user.password_hash = hash_password(f"{user.username}123")
        if user.is_active is None:
            user.is_active = True
        if not user.role or user.role == "user":
            user.role = "viewer"
    await session.flush()


async def tick_simulator_and_persist(session: AsyncSession, dt: Optional[datetime] = None) -> dict:
    """
    Run one simulator step and persist PV, battery, and load readings.
    Respects Appliance.is_on (from IEBA schedule executor) when computing load.
    Returns the same reading dict for API use.
    """
    await ensure_default_user_and_appliances(session)
    # Sync simulator appliance list with all DB appliances
    r_all = await session.execute(select(Appliance))
    db_apps = list(r_all.scalars().all())
    sim = get_simulator()
    sim.set_appliances([
        {
            "id": a.external_id,
            "name": a.name,
            "priority": a.priority,
            "rated_watts": float(a.rated_watts),
        }
        for a in db_apps
    ])
    # Load current appliance states so simulator respects schedule
    r = await session.execute(select(Appliance.external_id, Appliance.is_on))
    appliance_states = {row[0]: row[1] for row in r.all()}
    dt = dt or datetime.now(timezone.utc)
    reading = sim.tick(dt, appliance_states=appliance_states if appliance_states else None)
    ts = datetime.fromisoformat(reading["timestamp"].replace("Z", "+00:00"))

    session.add(PvReading(
        timestamp=ts,
        power_kw=reading["pv"]["power_kw"],
        voltage=reading["pv"]["voltage"],
        current_a=reading["pv"]["current_a"],
    ))
    session.add(BatteryReading(
        timestamp=ts,
        soc_percent=reading["battery"]["soc_percent"],
        voltage=reading["battery"]["voltage"],
        current_a=reading["battery"]["current_a"],
    ))

    # Resolve appliance external_id -> id
    for load in reading["loads"]:
        r = await session.execute(
            select(Appliance.id).where(Appliance.external_id == load["appliance_id"])
        )
        app_id = r.scalar_one_or_none()
        if app_id is not None:
            session.add(LoadReading(
                timestamp=ts,
                appliance_id=app_id,
                power_kw=load["power_kw"],
                state=load["state"],
            ))
    return reading
