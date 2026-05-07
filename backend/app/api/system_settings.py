"""Persisted server settings (MySQL), editable from the web UI."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_min_role
from app.database import get_db
from app.services.system_settings_service import ensure_system_settings_row

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_min_role("admin"))],
)


class SystemSettingsOut(BaseModel):
    auto_train_enabled: bool
    auto_ieba_enabled: bool
    auto_ieba_interval_minutes: int
    weather_forecast_enabled: bool
    weather_latitude: float
    weather_longitude: float
    weather_pv_capacity_kw: float
    weather_panel_derate: float
    inverter_capacity_kw: float
    battery_capacity_kwh: float
    soc_min_percent: float


class SystemSettingsPatch(BaseModel):
    auto_train_enabled: Optional[bool] = None
    auto_ieba_enabled: Optional[bool] = None
    auto_ieba_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    weather_forecast_enabled: Optional[bool] = None
    weather_latitude: Optional[float] = None
    weather_longitude: Optional[float] = None
    weather_pv_capacity_kw: Optional[float] = None
    weather_panel_derate: Optional[float] = None
    inverter_capacity_kw: Optional[float] = None
    battery_capacity_kwh: Optional[float] = None
    soc_min_percent: Optional[float] = None


@router.get("/settings", response_model=SystemSettingsOut)
async def get_system_settings(db: AsyncSession = Depends(get_db)) -> SystemSettingsOut:
    row = await ensure_system_settings_row(db)
    return SystemSettingsOut(
        auto_train_enabled=bool(row.auto_train_enabled),
        auto_ieba_enabled=bool(row.auto_ieba_enabled),
        auto_ieba_interval_minutes=int(row.auto_ieba_interval_minutes),
        weather_forecast_enabled=bool(row.weather_forecast_enabled),
        weather_latitude=float(row.weather_latitude),
        weather_longitude=float(row.weather_longitude),
        weather_pv_capacity_kw=float(row.weather_pv_capacity_kw),
        weather_panel_derate=float(row.weather_panel_derate),
        inverter_capacity_kw=float(row.inverter_capacity_kw),
        battery_capacity_kwh=float(row.battery_capacity_kwh),
        soc_min_percent=float(row.soc_min_percent),
    )


@router.put("/settings", response_model=SystemSettingsOut)
async def put_system_settings(
    body: SystemSettingsPatch,
    db: AsyncSession = Depends(get_db),
) -> SystemSettingsOut:
    row = await ensure_system_settings_row(db)
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return SystemSettingsOut(
        auto_train_enabled=bool(row.auto_train_enabled),
        auto_ieba_enabled=bool(row.auto_ieba_enabled),
        auto_ieba_interval_minutes=int(row.auto_ieba_interval_minutes),
        weather_forecast_enabled=bool(row.weather_forecast_enabled),
        weather_latitude=float(row.weather_latitude),
        weather_longitude=float(row.weather_longitude),
        weather_pv_capacity_kw=float(row.weather_pv_capacity_kw),
        weather_panel_derate=float(row.weather_panel_derate),
        inverter_capacity_kw=float(row.inverter_capacity_kw),
        battery_capacity_kwh=float(row.battery_capacity_kwh),
        soc_min_percent=float(row.soc_min_percent),
    )
