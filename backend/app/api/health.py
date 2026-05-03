"""Health endpoints for runtime diagnostics."""

from fastapi import APIRouter, Depends

from app.auth import require_min_role
from app.config import settings
from app.services.mqtt_ingest_service import get_mqtt_health

router = APIRouter(
    prefix="/health",
    tags=["health"],
    dependencies=[Depends(require_min_role("viewer"))],
)


@router.get("/mqtt")
async def mqtt_health() -> dict:
    return {
        "mode": "simulation" if settings.use_hardware_simulation else "hardware_ingest",
        "mqtt": get_mqtt_health(),
    }
