"""
Background controller loop (simulation mode):
- applies IEBA schedule for 'now'
- advances simulator by one tick and persists readings

This makes the system generate history continuously without needing UI refreshes.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.database import async_session
from app.services.schedule_executor_service import apply_schedule
from app.services.simulator_service import tick_simulator_and_persist


class ControllerLoop:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        interval = max(1, int(settings.simulator_interval_seconds))
        while not self._stop.is_set():
            try:
                async with async_session() as session:
                    await apply_schedule(session, now=datetime.now(timezone.utc))
                    await tick_simulator_and_persist(session, dt=datetime.now(timezone.utc))
                    await session.commit()
            except Exception:
                # Keep the loop alive; errors show in server logs
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

