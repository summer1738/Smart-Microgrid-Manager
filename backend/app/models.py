"""SQLAlchemy models for Smart Microgrid Manager."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(50), default="viewer")

    appliances: Mapped[List["Appliance"]] = relationship("Appliance", back_populates="user")
    sessions: Mapped[List["SessionToken"]] = relationship("SessionToken", back_populates="user")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class Appliance(Base):
    __tablename__ = "appliances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # e.g. fridge_01
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1=critical, 2=essential, 3=non-essential
    rated_watts: Mapped[float] = mapped_column(Float, nullable=False)
    usage_mode: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled / on_demand
    default_run_minutes: Mapped[int] = mapped_column(Integer, default=30)
    schedule_prefs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: preferred windows
    relay_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_on: Mapped[bool] = mapped_column(Boolean, default=True)
    manual_override_active: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="appliances")


class PvReading(Base):
    __tablename__ = "pv_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    voltage: Mapped[float] = mapped_column(Float, nullable=False)
    current_a: Mapped[float] = mapped_column(Float, nullable=False)


class BatteryReading(Base):
    __tablename__ = "battery_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    soc_percent: Mapped[float] = mapped_column(Float, nullable=False)
    voltage: Mapped[float] = mapped_column(Float, nullable=False)
    current_a: Mapped[float] = mapped_column(Float, nullable=False)


class LoadReading(Base):
    __tablename__ = "load_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id"), nullable=False, index=True)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="on")  # on / off / shedded


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appliance_id: Mapped[int] = mapped_column(ForeignKey("appliances.id"), nullable=False, index=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    planned_state: Mapped[str] = mapped_column(String(20), nullable=False)  # on / off
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / applied / skipped



# TempHumidityReading model
class TempHumidityReading(Base):
    __tablename__ = "temp_humidity_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_percent: Mapped[float] = mapped_column(Float, nullable=False)

# LightReading model
class LightReading(Base):
    __tablename__ = "light_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    is_sunny: Mapped[bool] = mapped_column(Boolean, nullable=False)

# SystemSettings model
class SystemSettings(Base):
    """Single-row persisted settings (id=1). Env vars seed defaults on first run only."""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    auto_train_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_ieba_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_ieba_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    weather_forecast_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weather_latitude: Mapped[float] = mapped_column(Float, default=-17.8)
    weather_longitude: Mapped[float] = mapped_column(Float, default=31.05)
    weather_pv_capacity_kw: Mapped[float] = mapped_column(Float, default=1.0)
    weather_panel_derate: Mapped[float] = mapped_column(Float, default=0.85)

    # Microgrid sizing for IEBA / scheduling (defaults should suit typical deployments).
    inverter_capacity_kw: Mapped[float] = mapped_column(Float, default=3.0)  # default 3 kW system
    battery_capacity_kwh: Mapped[float] = mapped_column(Float, default=5.0)
    soc_min_percent: Mapped[float] = mapped_column(Float, default=40.0)
