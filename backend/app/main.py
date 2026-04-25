"""
Smart Microgrid Manager API. Run with: uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api import appliances, forecast, health, schedule, status, system_settings
from app.config import settings
from app.database import init_db
from app.logging_config import setup_logging

import logging
import time

log = logging.getLogger("app")


async def seed_default_user():
    """Create default user and appliances so simulation and API work out of the box."""
    from app.database import async_session
    from app.models import User
    from app.services.simulator_service import ensure_default_user_and_appliances
    async with async_session() as session:
        await ensure_default_user_and_appliances(session)
        await session.commit()


async def seed_system_settings():
    """Ensure system_settings row exists (defaults from env on first run)."""
    from app.database import async_session
    from app.services.system_settings_service import ensure_system_settings_row
    async with async_session() as session:
        await ensure_system_settings_row(session)
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level, color=settings.log_color)
    log.info(
        "Starting backend (mode=%s, db=%s)",
        "simulation" if settings.use_hardware_simulation else "hardware_ingest",
        settings.database_url,
    )
    await init_db()
    log.info("Database initialized")
    await seed_default_user()
    log.info("Default user/appliances ensured")
    await seed_system_settings()
    log.info("System settings ensured")
    controller = None
    auto_trainer = None
    mqtt_ingest = None
    usb_fallback_bridge = None
    if settings.use_hardware_simulation and settings.controller_loop_enabled:
        from app.services.controller_loop import ControllerLoop
        controller = ControllerLoop()
        await controller.start()
        log.info("Controller loop started")
    if not settings.use_hardware_simulation:
        from app.services.mqtt_ingest_service import MqttIngestLoop
        mqtt_ingest = MqttIngestLoop()
        await mqtt_ingest.start()
        log.info("MQTT ingest loop started (host=%s port=%s prefix=%s)", settings.mqtt_host, settings.mqtt_port, settings.mqtt_topic_prefix)
        if settings.esp32_usb_fallback_enabled:
            from app.services.esp32_usb_fallback_service import Esp32UsbFallbackBridge
            usb_fallback_bridge = Esp32UsbFallbackBridge()
            started = await usb_fallback_bridge.start()
            if not started:
                log.warning("ESP32 USB fallback bridge was enabled but did not start (see prior warning).")
    from app.services.auto_train_service import AutoTrainLoop, set_global_auto_trainer
    auto_trainer = AutoTrainLoop()
    set_global_auto_trainer(auto_trainer)
    await auto_trainer.start()
    log.info("Auto-train loop started")
    yield
    log.info("Shutting down backend")
    if controller is not None:
        await controller.stop()
        log.info("Controller loop stopped")
    if auto_trainer is not None:
        await auto_trainer.stop()
        from app.services.auto_train_service import set_global_auto_trainer
        set_global_auto_trainer(None)
        log.info("Auto-train loop stopped")
    if mqtt_ingest is not None:
        await mqtt_ingest.stop()
        log.info("MQTT ingest loop stopped")
    if usb_fallback_bridge is not None:
        await usb_fallback_bridge.stop()
        log.info("ESP32 USB fallback bridge stopped")


app = FastAPI(
    title="Smart Microgrid Manager",
    description="Off-grid solar management: forecasting, IEBA, UCLPI. Hardware simulation mode when no physical devices.",
    version="0.1.0",
    lifespan=lifespan,
)


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.log_access:
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        log.info(
            'http %s %s -> %s (%.1fms)',
            request.method,
            request.url.path,
            response.status_code,
            dt_ms,
        )
        return response


app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(appliances.router)
app.include_router(status.router)
app.include_router(forecast.router)
app.include_router(schedule.router)
app.include_router(health.router)
app.include_router(system_settings.router)


@app.get("/")
async def root():
    return {
        "service": "Smart Microgrid Manager API",
        "docs": "/docs",
        "status": "/status",
        "appliances": "/appliances",
        "forecast": "/forecast",
        "training_status": "/forecast/training-status",
        "weather_insights": "/forecast/weather-insights",
        "schedule": "/schedule",
        "health_mqtt": "/health/mqtt",
        "system_settings": "/system/settings",
    }
