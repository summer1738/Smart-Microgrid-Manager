"""Persisted server settings (MySQL), editable from the web UI."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.system_settings_service import ensure_system_settings_row

router = APIRouter(prefix="/system", tags=["system"])


class SystemSettingsOut(BaseModel):
    auto_train_enabled: bool
    weather_forecast_enabled: bool
    weather_latitude: float
    weather_longitude: float
    weather_pv_capacity_kw: float
    weather_panel_derate: float
    inverter_capacity_kw: float
    battery_capacity_kwh: float
    soc_min_percent: float


class SystemSettingsPatch(BaseModel):
    auto_train_enabled: bool
    weather_forecast_enabled: bool
    weather_latitude: float
    weather_longitude: float
    weather_pv_capacity_kw: float
    weather_panel_derate: float
    inverter_capacity_kw: float
    battery_capacity_kwh: float
    soc_min_percent: float


@router.get("/settings", response_model=SystemSettingsOut)
async def get_system_settings(db: AsyncSession = Depends(get_db)) -> SystemSettingsOut:
    row = await ensure_system_settings_row(db)
    return SystemSettingsOut(
        auto_train_enabled=bool(row.auto_train_enabled),
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
    row.auto_train_enabled = body.auto_train_enabled
    row.weather_forecast_enabled = body.weather_forecast_enabled
    row.weather_latitude = body.weather_latitude
    row.weather_longitude = body.weather_longitude
    row.weather_pv_capacity_kw = body.weather_pv_capacity_kw
    row.weather_panel_derate = body.weather_panel_derate
    row.inverter_capacity_kw = body.inverter_capacity_kw
    row.battery_capacity_kwh = body.battery_capacity_kwh
    row.soc_min_percent = body.soc_min_percent
    await db.commit()
    await db.refresh(row)
    return SystemSettingsOut(
        auto_train_enabled=bool(row.auto_train_enabled),
        weather_forecast_enabled=bool(row.weather_forecast_enabled),
        weather_latitude=float(row.weather_latitude),
        weather_longitude=float(row.weather_longitude),
        weather_pv_capacity_kw=float(row.weather_pv_capacity_kw),
        weather_panel_derate=float(row.weather_panel_derate),
        inverter_capacity_kw=float(row.inverter_capacity_kw),
        battery_capacity_kwh=float(row.battery_capacity_kwh),
        soc_min_percent=float(row.soc_min_percent),
    )
