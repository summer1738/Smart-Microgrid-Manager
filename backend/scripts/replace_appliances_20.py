import asyncio

from sqlalchemy import delete, select

from app.database import async_session, init_db
from app.models import Appliance, User


APPLIANCES_20 = [
    # priority 1 (critical)
    ("clinic_fridge", "Clinic fridge", 180, 1, "scheduled"),
    ("comm_router", "Router + comms", 25, 1, "scheduled"),
    ("security_lights", "Security lights", 60, 1, "scheduled"),
    ("water_pump_small", "Water pump (small)", 370, 1, "on_demand"),
    ("pos_system", "POS / office PC", 120, 1, "scheduled"),
    # priority 2 (essential)
    ("lighting_indoor", "Indoor lighting", 90, 2, "scheduled"),
    ("tv_radio", "TV / radio", 85, 2, "scheduled"),
    ("phone_charging", "Phone charging hub", 45, 2, "scheduled"),
    ("laptop_charging", "Laptop charging", 95, 2, "scheduled"),
    ("freezer_small", "Small freezer", 220, 2, "scheduled"),
    ("fan_set", "Fans (x3)", 135, 2, "scheduled"),
    ("cctv", "CCTV system", 35, 2, "scheduled"),
    ("internet_backup", "Internet backup modem", 15, 2, "scheduled"),
    # priority 3 (non-essential / deferrable)
    ("washing_machine", "Washing machine", 500, 3, "on_demand"),
    ("heater_water", "Water heater", 1200, 3, "on_demand"),
    ("iron", "Electric iron", 1000, 3, "on_demand"),
    ("shop_tools", "Workshop tools", 800, 3, "on_demand"),
    ("music_system", "Music system", 140, 3, "scheduled"),
    ("signage", "Shop signage", 70, 3, "scheduled"),
    ("extra_outlets", "Extra outlets (misc)", 250, 3, "on_demand"),
]


async def main() -> None:
    await init_db()
    async with async_session() as session:
        r = await session.execute(select(User).order_by(User.id))
        user = r.scalars().first()
        if user is None:
            raise RuntimeError("No users found in DB; start backend once to seed users.")

        await session.execute(delete(Appliance))

        for ext_id, name, watts, priority, usage_mode in APPLIANCES_20:
            session.add(
                Appliance(
                    user_id=user.id,
                    external_id=ext_id,
                    name=name,
                    priority=int(priority),
                    rated_watts=float(watts),
                    usage_mode=usage_mode,
                    default_run_minutes=30 if usage_mode == "scheduled" else 45,
                    schedule_prefs=None,
                    relay_topic=None,
                    is_on=True,
                )
            )

        await session.commit()
        print(f"Replaced appliances: inserted {len(APPLIANCES_20)} for user_id={user.id} ({user.name}).")


if __name__ == "__main__":
    asyncio.run(main())

