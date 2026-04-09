"""MQTT ingest loop for hardware/Pi gateway mode."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Appliance, BatteryReading, EnvironmentReading, LoadReading, PvReading
from app.services.mqtt_topics import (
    ack_relay_topic,
    command_relay_topic,
    parse_sensor_load_topic,
    sensor_battery_topic,
    sensor_environment_topic,
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
    "last_environment_at": None,
    "ingest_start_error": None,
}

# Latest DHT11 + digital light from MQTT (hardware gateway); thread-updated.
_ambient_state: dict[str, Any] = {
    "temperature_c": None,
    "humidity_percent": None,
    "light_digital": None,
    "updated_at": None,
    "esp32_gateway": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_mqtt_health() -> dict[str, Any]:
    # Return shallow copy for API responses.
    out = dict(_mqtt_health)
    out["last_load_at"] = dict(_mqtt_health.get("last_load_at", {}))
    return out


def get_sensor_pipeline_issues() -> list[dict[str, Any]]:
    """
    Human-readable blockers for live ESP32 sensor data reaching /status.
    Used by GET /health/mqtt and the web UI.
    """
    mh = get_mqtt_health()
    issues: list[dict[str, Any]] = []
    if settings.use_hardware_simulation:
        issues.append(
            {
                "code": "SIMULATION_MODE",
                "severity": "error",
                "message": "MQTT ingest is disabled because the backend runs in simulation mode.",
                "fix": "Set MICROGRID_USE_HARDWARE_SIMULATION=false in backend/.env, restart uvicorn, and ensure Mosquitto is running.",
            }
        )
        return issues
    if not mh.get("mqtt_available"):
        issues.append(
            {
                "code": "PAHO_MISSING",
                "severity": "error",
                "message": "The paho-mqtt package is not available; the MQTT client cannot start.",
                "fix": "Install dependencies: pip install -r backend/requirements.txt (includes paho-mqtt).",
            }
        )
        return issues
    err = mh.get("ingest_start_error")
    if not mh.get("running"):
        if err and ("connection refused" in err.lower() or "errno 111" in err.lower()):
            tail = (
                "No broker is accepting TCP connections on this host/port. "
                "Install and start Mosquitto (e.g. Debian/Ubuntu: sudo apt install mosquitto && sudo systemctl start mosquitto). "
                "The API will retry in the background every 15s; restart uvicorn is not required once the broker is up."
            )
        else:
            tail = (
                "Typical causes: broker not running, wrong MICROGRID_MQTT_HOST/PORT, or connection refused at startup. "
                "The API retries connecting every 15s in the background."
            )
        issues.append(
            {
                "code": "INGEST_NOT_RUNNING",
                "severity": "error",
                "message": "The MQTT ingest loop did not start or crashed.",
                "fix": f"{err + ' — ' if err else ''}{tail}",
            }
        )
        return issues
    if not mh.get("connected"):
        issues.append(
            {
                "code": "BROKER_DISCONNECTED",
                "severity": "error",
                "message": f"Not connected to MQTT broker at {settings.mqtt_host}:{settings.mqtt_port}.",
                "fix": "Start Mosquitto, open the port in the firewall, and confirm the host is correct for this machine.",
            }
        )
        return issues
    if not mh.get("last_environment_at"):
        env_topic = sensor_environment_topic(settings.mqtt_topic_prefix)
        load_map = mh.get("last_load_at") or {}
        other_traffic = bool(
            mh.get("last_pv_at") or mh.get("last_battery_at") or load_map
        )
        if other_traffic:
            issues.append(
                {
                    "code": "ENVIRONMENT_TOPIC_QUIET",
                    "severity": "warning",
                    "message": (
                        "MQTT is flowing (PV/battery/loads seen) but nothing has arrived on the "
                        "environment (sensors) topic yet."
                    ),
                    "fix": "\n".join(
                        [
                            f"The backend subscribes to `{env_topic}` (prefix "
                            f"`{settings.mqtt_topic_prefix}` = MICROGRID_MQTT_TOPIC_PREFIX). "
                            "ESP32 must publish exactly that topic.",
                            "1) Match ESP32 MQTT_TOPIC_PREFIX to the backend prefix above.",
                            "2) Confirm the sketch calls publishEnvironment() on its telemetry loop (see firmware/esp32_doit_gateway).",
                            "3) Quick test from this machine: bash scripts/test_mqtt_environment_publish.sh",
                        ]
                    ),
                }
            )
        else:
            issues.append(
                {
                    "code": "NO_ENVIRONMENT_TELEMETRY",
                    "severity": "warning",
                    "message": "Subscribed to the broker but no messages on the environment (sensors) topic yet.",
                    "fix": "\n".join(
                        [
                            f"1) ESP32 secrets: MQTT_HOST = this PC's LAN IP (not localhost). "
                            f"MQTT_TOPIC_PREFIX = '{settings.mqtt_topic_prefix}' → topic `{env_topic}`.",
                            "2) Mosquitto must accept LAN clients: listener on 0.0.0.0:1883 "
                            "(see scripts/mosquitto-listener-dev.conf.example).",
                            "3) Quick test (no ESP32): bash scripts/test_mqtt_environment_publish.sh — "
                            "then this warning clears if the backend receives the message.",
                            "4) Firewall: sudo ufw allow 1883/tcp if the board still cannot reach the broker.",
                            "5) After a backend restart, in-memory telemetry is empty until the next publish on that topic.",
                        ]
                    ),
                }
            )
    return issues


def get_ambient_state() -> dict[str, Any]:
    """Last values from MQTT .../sensors/environment (ESP32)."""
    out: dict[str, Any] = {
        "temperature_c": _ambient_state.get("temperature_c"),
        "humidity_percent": _ambient_state.get("humidity_percent"),
        "light_digital": _ambient_state.get("light_digital"),
        "updated_at": _ambient_state.get("updated_at"),
    }
    eg = _ambient_state.get("esp32_gateway")
    if eg:
        out["esp32_gateway"] = dict(eg)
    return out


def _apply_esp32_gateway_payload(payload: dict[str, Any], ts: datetime) -> None:
    gw: dict[str, Any] = {}
    if "wifi_rssi_dbm" in payload:
        try:
            gw["wifi_rssi_dbm"] = int(payload["wifi_rssi_dbm"])
        except (TypeError, ValueError):
            pass
    if "free_heap_bytes" in payload:
        try:
            gw["free_heap_bytes"] = int(payload["free_heap_bytes"])
        except (TypeError, ValueError):
            pass
    if "uptime_ms" in payload:
        try:
            gw["uptime_ms"] = int(payload["uptime_ms"])
        except (TypeError, ValueError):
            pass
    if "dht_ok" in payload:
        raw = payload["dht_ok"]
        if isinstance(raw, bool):
            gw["dht_ok"] = raw
        else:
            try:
                gw["dht_ok"] = bool(int(raw))
            except (TypeError, ValueError):
                pass
    if "light_ok" in payload:
        raw = payload["light_ok"]
        if isinstance(raw, bool):
            gw["light_ok"] = raw
        else:
            try:
                gw["light_ok"] = bool(int(raw))
            except (TypeError, ValueError):
                pass
    pins = payload.get("pins")
    if isinstance(pins, dict):
        out_pins: dict[str, int] = {}
        for k, v in pins.items():
            try:
                out_pins[str(k)] = int(v)
            except (TypeError, ValueError):
                pass
        if out_pins:
            gw["pins"] = out_pins
    if not gw:
        # Do not clear esp32_gateway: older or partial JSON may omit diagnostics fields.
        return
    prev = dict(_ambient_state.get("esp32_gateway") or {})
    prev.update(gw)
    prev["updated_at"] = ts
    _ambient_state["esp32_gateway"] = prev


def _parse_dht_ok_flag(payload: dict[str, Any]) -> Optional[bool]:
    """True/False when firmware reports DHT health; None if key absent."""
    if "dht_ok" not in payload:
        return None
    raw = payload["dht_ok"]
    if isinstance(raw, bool):
        return raw
    try:
        return bool(int(raw))
    except (TypeError, ValueError):
        return None


def _parse_light_ok_flag(payload: dict[str, Any]) -> Optional[bool]:
    """True/False when firmware reports light sensor present; None if key absent."""
    if "light_ok" not in payload:
        return None
    raw = payload["light_ok"]
    if isinstance(raw, bool):
        return raw
    try:
        return bool(int(raw))
    except (TypeError, ValueError):
        return None


def _apply_ambient_payload(payload: dict[str, Any]) -> None:
    ts = _parse_ts(payload)
    raw_t = payload.get("temperature_c")
    raw_h = payload.get("humidity_percent")
    raw_l = payload.get("light_digital")

    # When DHT read fails, firmware omits temperature_c / humidity_percent but still sends
    # light + diagnostics. Previously we only updated keys that were present, so stale T/RH
    # stayed in memory until restart.
    dht_ok_flag = _parse_dht_ok_flag(payload)
    if dht_ok_flag is False:
        _ambient_state["temperature_c"] = None
        _ambient_state["humidity_percent"] = None
    else:
        if "temperature_c" in payload:
            try:
                _ambient_state["temperature_c"] = float(raw_t) if raw_t is not None else None
            except (TypeError, ValueError):
                pass
        if "humidity_percent" in payload:
            try:
                _ambient_state["humidity_percent"] = float(raw_h) if raw_h is not None else None
            except (TypeError, ValueError):
                pass

    light_ok_flag = _parse_light_ok_flag(payload)
    if light_ok_flag is False:
        _ambient_state["light_digital"] = None
    elif "light_digital" in payload and raw_l is not None:
        if isinstance(raw_l, bool):
            _ambient_state["light_digital"] = raw_l
        else:
            try:
                _ambient_state["light_digital"] = bool(int(raw_l))
            except (TypeError, ValueError):
                pass
    _ambient_state["updated_at"] = ts
    _apply_esp32_gateway_payload(payload, ts)


def _parse_ts(payload: dict[str, Any]) -> datetime:
    raw = payload.get("timestamp")
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
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


async def _persist_environment(payload: dict[str, Any]) -> None:
    ts = _parse_ts(payload)
    raw_t = payload.get("temperature_c")
    raw_h = payload.get("humidity_percent")
    raw_l = payload.get("light_digital")
    tc = th = None
    if raw_t is not None:
        try:
            tc = float(raw_t)
        except (TypeError, ValueError):
            pass
    if raw_h is not None:
        try:
            th = float(raw_h)
        except (TypeError, ValueError):
            pass
    ld = None
    light_ok_flag = _parse_light_ok_flag(payload)
    if light_ok_flag is False:
        ld = None
    elif raw_l is not None:
        if isinstance(raw_l, bool):
            ld = raw_l
        else:
            try:
                ld = bool(int(raw_l))
            except (TypeError, ValueError):
                pass
    diag: dict[str, Any] = {}
    for k in ("wifi_rssi_dbm", "free_heap_bytes", "uptime_ms", "dht_ok", "light_ok", "pins"):
        if k in payload:
            diag[k] = payload[k]
    diag_json = json.dumps(diag, separators=(",", ":")) if diag else None

    async with async_session() as session:
        session.add(
            EnvironmentReading(
                timestamp=ts,
                temperature_c=tc,
                humidity_percent=th,
                light_digital=ld,
                esp32_diagnostics_json=diag_json,
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
        self._reconnect_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        _mqtt_health["ingest_start_error"] = None
        if self._running:
            return True
        if mqtt is None:
            log.error("MQTT ingest cannot start: paho-mqtt is not installed (pip install paho-mqtt)")
            _mqtt_health["ingest_start_error"] = "paho-mqtt not installed"
            return False
        self._loop = asyncio.get_running_loop()
        prefix = settings.mqtt_topic_prefix
        client = mqtt.Client(client_id=f"{settings.mqtt_client_id}-ingest", protocol=mqtt.MQTTv311)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        try:
            client.connect(settings.mqtt_host, int(settings.mqtt_port), 30)
        except Exception as e:  # noqa: BLE001 — surface broker errors to health API
            msg = str(e)
            _mqtt_health["ingest_start_error"] = msg
            log.exception("MQTT broker connection failed host=%s port=%s: %s", settings.mqtt_host, settings.mqtt_port, e)
            return False
        client.subscribe(sensor_pv_topic(prefix), qos=1)
        client.subscribe(sensor_battery_topic(prefix), qos=1)
        client.subscribe(sensor_environment_topic(prefix), qos=1)
        client.subscribe(f"{prefix}/sensors/load/+", qos=1)
        client.subscribe(f"{prefix}/ack/relay/+", qos=0)
        try:
            client.loop_start()
        except Exception as e:  # noqa: BLE001
            _mqtt_health["ingest_start_error"] = str(e)
            log.exception("MQTT loop_start failed: %s", e)
            try:
                client.disconnect()
            except Exception:
                pass
            return False
        self._client = client
        self._running = True
        _mqtt_health["running"] = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
        log.info("MQTT ingest started host=%s port=%s prefix=%s", settings.mqtt_host, settings.mqtt_port, settings.mqtt_topic_prefix)
        return True

    def schedule_reconnect_background(self) -> None:
        """If the broker was down at startup, retry ``start()`` periodically until it succeeds."""
        if mqtt is None or self._running:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return

        async def _worker() -> None:
            n = 0
            while not self._running:
                await asyncio.sleep(15)
                n += 1
                if n == 1 or n % 8 == 0:
                    log.warning(
                        "MQTT reconnect attempt %s → %s:%s (is Mosquitto running?)",
                        n,
                        settings.mqtt_host,
                        settings.mqtt_port,
                    )
                if await self.start():
                    return

        self._reconnect_task = asyncio.create_task(_worker())

    async def stop(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
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
        client.subscribe(sensor_environment_topic(prefix), qos=1)
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
        if topic == sensor_environment_topic(prefix):
            _mqtt_health["last_environment_at"] = _now_iso()
            _apply_ambient_payload(payload)
            asyncio.run_coroutine_threadsafe(_persist_environment(payload), self._loop)
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

