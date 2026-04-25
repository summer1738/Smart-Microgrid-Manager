"""Ensure appliance external IDs used by ESP32 relay control exist in DB.

Usage:
  cd backend
  PYTHONPATH=.. ../.venv/bin/python scripts/align_esp32_appliance_ids.py
"""

import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models import Appliance, User


TARGETS = [
    ("proto_led_a", "ESP32 Relay A", 15.0),
    ("proto_led_b", "ESP32 Relay B", 10.0),
]


async def main() -> None:
    async with async_session() as session:
        user = (await session.execute(select(User).order_by(User.id))).scalars().first()
        if user is None:
            raise RuntimeError("No user found. Start backend once to seed default user.")

        for ext_id, name, watts in TARGETS:
            existing = (await session.execute(select(Appliance).where(Appliance.external_id == ext_id))).scalar_one_or_none()
            if existing is None:
                session.add(
                    Appliance(
                        user_id=user.id,
                        external_id=ext_id,
                        name=name,
                        priority=2,
                        rated_watts=watts,
                        usage_mode="scheduled",
                        default_run_minutes=30,
                        is_on=True,
                    )
                )
                print(f"created {ext_id}")
            else:
                print(f"exists  {ext_id}")

        await session.commit()
        print("done")


if __name__ == "__main__":
    asyncio.run(main())

