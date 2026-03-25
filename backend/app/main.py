"""
Smart Microgrid Manager API. Run with: uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import appliances, forecast, health, schedule, status, system_settings
from app.config import settings
from app.database import init_db


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
    await init_db()
    await seed_default_user()
    await seed_system_settings()
    controller = None
    auto_trainer = None
    mqtt_ingest = None
    if settings.use_hardware_simulation and settings.controller_loop_enabled:
        from app.services.controller_loop import ControllerLoop
        controller = ControllerLoop()
        await controller.start()
    if not settings.use_hardware_simulation:
        from app.services.mqtt_ingest_service import MqttIngestLoop
        mqtt_ingest = MqttIngestLoop()
        await mqtt_ingest.start()
    from app.services.auto_train_service import AutoTrainLoop, set_global_auto_trainer
    auto_trainer = AutoTrainLoop()
    set_global_auto_trainer(auto_trainer)
    await auto_trainer.start()
    yield
    if controller is not None:
        await controller.stop()
    if auto_trainer is not None:
        await auto_trainer.stop()
        from app.services.auto_train_service import set_global_auto_trainer
        set_global_auto_trainer(None)
    if mqtt_ingest is not None:
        await mqtt_ingest.stop()


app = FastAPI(
    title="Smart Microgrid Manager",
    description="Off-grid solar management: forecasting, IEBA, UCLPI. Hardware simulation mode when no physical devices.",
    version="0.1.0",
    lifespan=lifespan,
)
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
