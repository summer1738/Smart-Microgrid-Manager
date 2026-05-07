"""
Background controller loop:
- optionally auto-runs IEBA on an admin-configured interval
- applies IEBA schedule for 'now'
- advances simulator by one tick when simulation mode is enabled

This makes the system generate history continuously without needing UI refreshes.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.database import async_session
from app.services.schedule_executor_service import apply_schedule
from app.services.schedule_service import run_and_persist_schedule
from app.services.simulator_service import tick_simulator_and_persist
from app.services.system_settings_service import ensure_system_settings_row


class ControllerLoop:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_auto_ieba_run_at: Optional[datetime] = None

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
                    now = datetime.now(timezone.utc)
                    sys_row = await ensure_system_settings_row(session)
                    if bool(sys_row.auto_ieba_enabled):
                        every_minutes = max(1, int(sys_row.auto_ieba_interval_minutes))
                        if (
                            self._last_auto_ieba_run_at is None
                            or (now - self._last_auto_ieba_run_at).total_seconds() >= every_minutes * 60
                        ):
                            await run_and_persist_schedule(session, now=now)
                            self._last_auto_ieba_run_at = now
                    await apply_schedule(session, now=now)
                    if settings.use_hardware_simulation:
                        await tick_simulator_and_persist(session, dt=now)
                    await session.commit()
            except Exception:
                # Keep the loop alive; errors show in server logs
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
