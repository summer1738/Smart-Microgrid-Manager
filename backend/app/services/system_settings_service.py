"""Read/write persisted system settings (SQLite)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import SystemSettings


async def ensure_system_settings_row(session: AsyncSession) -> SystemSettings:
    r = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
    row = r.scalar_one_or_none()
    if row is None:
        row = SystemSettings(
            id=1,
            auto_train_enabled=bool(settings.auto_train_enabled),
            weather_forecast_enabled=bool(settings.weather_forecast_enabled),
            weather_latitude=float(settings.weather_latitude),
            weather_longitude=float(settings.weather_longitude),
            weather_pv_capacity_kw=float(settings.weather_pv_capacity_kw),
            weather_panel_derate=float(settings.weather_panel_derate),
        )
        session.add(row)
        await session.flush()
    return row


async def get_auto_train_enabled() -> bool:
    try:
        async with async_session() as session:
            r = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
            row = r.scalar_one_or_none()
            if row is None:
                return bool(settings.auto_train_enabled)
            return bool(row.auto_train_enabled)
    except Exception:
        return bool(settings.auto_train_enabled)


async def set_auto_train_enabled(enabled: bool) -> bool:
    async with async_session() as session:
        row = await ensure_system_settings_row(session)
        row.auto_train_enabled = bool(enabled)
        await session.commit()
        return bool(row.auto_train_enabled)


async def get_weather_settings(session: AsyncSession) -> dict:
    row = await ensure_system_settings_row(session)
    return {
        "weather_forecast_enabled": bool(row.weather_forecast_enabled),
        "weather_latitude": float(row.weather_latitude),
        "weather_longitude": float(row.weather_longitude),
        "weather_pv_capacity_kw": float(row.weather_pv_capacity_kw),
        "weather_panel_derate": float(row.weather_panel_derate),
    }


