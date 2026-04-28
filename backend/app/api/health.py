"""Health endpoints for runtime diagnostics."""

from fastapi import APIRouter, Depends

from app.auth import require_min_role
from app.config import settings
from app.services.mqtt_ingest_service import get_mqtt_health, get_sensor_pipeline_issues
from app.services.mqtt_topics import (
    ack_relay_topic,
    command_relay_topic,
    sensor_battery_topic,
    sensor_environment_topic,
    sensor_load_topic,
    sensor_pv_topic,
)

router = APIRouter(
    prefix="/health",
    tags=["health"],
    dependencies=[Depends(require_min_role("viewer"))],
)


@router.get("/mqtt")
async def mqtt_health() -> dict:
    prefix = settings.mqtt_topic_prefix
    pipeline_issues = get_sensor_pipeline_issues()
    return {
        "mode": "simulation" if settings.use_hardware_simulation else "hardware_ingest",
        "topic_prefix": prefix,
        "example_topics": {
            "pv": sensor_pv_topic(prefix),
            "battery": sensor_battery_topic(prefix),
            "environment": sensor_environment_topic(prefix),
            "load": sensor_load_topic(prefix, "{external_id}"),
            "relay_command": command_relay_topic(prefix, "{external_id}"),
            "relay_ack": ack_relay_topic(prefix, "{external_id}"),
        },
        "mqtt": get_mqtt_health(),
        "sensor_pipeline": {
            "issues": pipeline_issues,
            "live_sensors_ok": len(pipeline_issues) == 0,
        },
    }
