"""MQTT ingest loop for hardware/Pi gateway mode."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Appliance, BatteryReading, LoadReading, PvReading
from app.services.mqtt_topics import (
    ack_relay_topic,
    command_relay_topic,
    parse_sensor_load_topic,
    sensor_battery_topic,
    sensor_pv_topic,
)

import logging

log = logging.getLogger("app.mqtt")

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional dependency at runtime
    mqtt = None

_mqtt_health: dict[str, Any] = {
    "mqtt_available": mqtt is not None,
    "running": False,
    "connected": False,
    "broker_host": settings.mqtt_host,
    "broker_port": int(settings.mqtt_port),
    "last_message_at": None,
    "last_pv_at": None,
    "last_battery_at": None,
    "last_load_at": {},
    "last_relay_ack_at": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_mqtt_health() -> dict[str, Any]:
    # Return shallow copy for API responses.
    out = dict(_mqtt_health)
    out["last_load_at"] = dict(_mqtt_health.get("last_load_at", {}))
    return out


def _parse_ts(payload: dict[str, Any]) -> datetime:
    raw = payload.get("timestamp")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _persist_pv(payload: dict[str, Any]) -> None:
    ts = _parse_ts(payload)
    async with async_session() as session:
        session.add(
            PvReading(
                timestamp=ts,
                power_kw=float(payload.get("power_kw", 0.0)),
                voltage=float(payload.get("voltage", 0.0)),
                current_a=float(payload.get("current_a", 0.0)),
            )
        )
        await session.commit()


async def _persist_battery(payload: dict[str, Any]) -> None:
    ts = _parse_ts(payload)
    async with async_session() as session:
        session.add(
            BatteryReading(
                timestamp=ts,
                soc_percent=float(payload.get("soc_percent", 0.0)),
                voltage=float(payload.get("voltage", 0.0)),
                current_a=float(payload.get("current_a", 0.0)),
            )
        )
        await session.commit()


async def _persist_load(appliance_external_id: str, payload: dict[str, Any]) -> None:
    ts = _parse_ts(payload)
    async with async_session() as session:
        r = await session.execute(
            select(Appliance.id).where(Appliance.external_id == appliance_external_id)
        )
        app_id = r.scalar_one_or_none()
        if app_id is None:
            return
        session.add(
            LoadReading(
                timestamp=ts,
                appliance_id=app_id,
                power_kw=float(payload.get("power_kw", 0.0)),
                state=str(payload.get("state", "on")),
            )
        )
        await session.commit()


async def publish_relay_command(appliance_external_id: str, is_on: bool) -> None:
    """
    Publish a relay command to the Pi/gateway.
    This is used by the schedule executor in hardware mode.
    """
    if mqtt is None:
        return
    prefix = settings.mqtt_topic_prefix
    topic = command_relay_topic(prefix, appliance_external_id)
    payload = json.dumps(
        {
            "appliance_id": appliance_external_id,
            "is_on": bool(is_on),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    def _publish_once() -> None:
        client = mqtt.Client(client_id=f"{settings.mqtt_client_id}-publisher", protocol=mqtt.MQTTv311)
        client.connect(settings.mqtt_host, int(settings.mqtt_port), 30)
        client.publish(topic, payload, qos=1, retain=False)
        client.disconnect()

    await asyncio.to_thread(_publish_once)


class MqttIngestLoop:
    """Subscribe to sensor topics and persist incoming telemetry."""

    def __init__(self) -> None:
        self._client: Optional[mqtt.Client] = None if mqtt is not None else None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        if self._running or mqtt is None:
            return
        self._loop = asyncio.get_running_loop()
        prefix = settings.mqtt_topic_prefix
        client = mqtt.Client(client_id=f"{settings.mqtt_client_id}-ingest", protocol=mqtt.MQTTv311)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect(settings.mqtt_host, int(settings.mqtt_port), 30)
        client.subscribe(sensor_pv_topic(prefix), qos=1)
        client.subscribe(sensor_battery_topic(prefix), qos=1)
        client.subscribe(f"{prefix}/sensors/load/+", qos=1)
        client.subscribe(f"{prefix}/ack/relay/+", qos=0)
        client.loop_start()
        self._client = client
        self._running = True
        _mqtt_health["running"] = True
        log.info("MQTT ingest started host=%s port=%s prefix=%s", settings.mqtt_host, settings.mqtt_port, settings.mqtt_topic_prefix)

    async def stop(self) -> None:
        if not self._running or self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._running = False
        self._client = None
        _mqtt_health["running"] = False
        _mqtt_health["connected"] = False
        log.info("MQTT ingest stopped")

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        # Subscriptions are already set in start(); this callback exists for reconnect behavior.
        if rc != 0:
            _mqtt_health["connected"] = False
            log.warning("MQTT connect failed rc=%s", rc)
            return
        _mqtt_health["connected"] = True
        log.info("MQTT connected")
        prefix = settings.mqtt_topic_prefix
        client.subscribe(sensor_pv_topic(prefix), qos=1)
        client.subscribe(sensor_battery_topic(prefix), qos=1)
        client.subscribe(f"{prefix}/sensors/load/+", qos=1)
        client.subscribe(f"{prefix}/ack/relay/+", qos=0)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        if self._loop is None:
            return
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            log.debug("MQTT message invalid json topic=%s", topic)
            return
        prefix = settings.mqtt_topic_prefix
        _mqtt_health["last_message_at"] = _now_iso()
        if topic == sensor_pv_topic(prefix):
            _mqtt_health["last_pv_at"] = _now_iso()
            asyncio.run_coroutine_threadsafe(_persist_pv(payload), self._loop)
            return
        if topic == sensor_battery_topic(prefix):
            _mqtt_health["last_battery_at"] = _now_iso()
            asyncio.run_coroutine_threadsafe(_persist_battery(payload), self._loop)
            return
        ext_id = parse_sensor_load_topic(prefix, topic)
        if ext_id is not None:
            _mqtt_health.setdefault("last_load_at", {})
            _mqtt_health["last_load_at"][ext_id] = _now_iso()
            asyncio.run_coroutine_threadsafe(_persist_load(ext_id, payload), self._loop)
            return
        # Ack topic is currently informational only.
        ack_base = f"{prefix}/ack/relay/"
        if topic.startswith(ack_base):
            _mqtt_health["last_relay_ack_at"] = _now_iso()
            return

