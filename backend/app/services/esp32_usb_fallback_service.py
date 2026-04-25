"""ESP32 USB fallback bridge.

Reads Serial lines from the ESP32 like:
  [USB] {"source":"usb_fallback", ...}
and republishes mapped telemetry to MQTT topics so normal ingest paths continue
working when Wi-Fi/MQTT from the board is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings
from app.services.mqtt_topics import sensor_battery_topic, sensor_load_topic, sensor_pv_topic

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    serial = None

try:
    import paho.mqtt.client as mqtt
except Exception:  # pragma: no cover - optional runtime dependency
    mqtt = None

log = logging.getLogger("app.usb")


class Esp32UsbFallbackBridge:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._ser = None
        self._mqtt = None

    async def start(self) -> bool:
        if self._running:
            return True
        if serial is None:
            log.warning("USB fallback disabled: pyserial is not installed.")
            return False
        if mqtt is None:
            log.warning("USB fallback disabled: paho-mqtt is not installed.")
            return False

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="esp32-usb-fallback-bridge")
        log.info(
            "ESP32 USB fallback bridge started (port=%s baud=%s -> mqtt=%s:%s)",
            settings.esp32_usb_port,
            settings.esp32_usb_baudrate,
            settings.mqtt_host,
            settings.mqtt_port,
        )
        return True

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        try:
            if self._mqtt is not None:
                self._mqtt.disconnect()
        except Exception:
            pass
        self._mqtt = None
        log.info("ESP32 USB fallback bridge stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                if self._ser is None:
                    self._ser = serial.Serial(
                        settings.esp32_usb_port,
                        settings.esp32_usb_baudrate,
                        timeout=1.0,
                    )
                    log.info("USB opened %s @ %s", settings.esp32_usb_port, settings.esp32_usb_baudrate)

                if self._mqtt is None:
                    c = mqtt.Client(client_id=f"{settings.mqtt_client_id}-usb-fallback", protocol=mqtt.MQTTv311)
                    c.connect(settings.mqtt_host, int(settings.mqtt_port), 30)
                    self._mqtt = c
                    log.info("USB bridge connected to MQTT %s:%s", settings.mqtt_host, settings.mqtt_port)

                # Blocking read happens in thread to keep event loop responsive.
                raw = await asyncio.to_thread(self._ser.readline)
                if not raw:
                    await asyncio.sleep(0.05)
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("[USB] "):
                    continue
                payload_str = line[6:].strip()
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    log.debug("USB fallback invalid JSON: %s", payload_str)
                    continue
                self._publish_mapped(payload)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("USB fallback bridge error: %s", e)
                try:
                    if self._ser is not None:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                try:
                    if self._mqtt is not None:
                        self._mqtt.disconnect()
                except Exception:
                    pass
                self._mqtt = None
                await asyncio.sleep(2.0)

    def _publish_mapped(self, p: dict[str, Any]) -> None:
        if self._mqtt is None:
            return
        prefix = settings.mqtt_topic_prefix
        ts = p.get("timestamp")
        if not isinstance(ts, str) or not ts:
            ts = datetime.now(timezone.utc).isoformat()

        pv_w = _to_float(p.get("pv_power_w"))
        batt_soc = _to_float(p.get("battery_soc_percent"))
        load_w = _to_float(p.get("load_power_w"))
        relay1 = bool(p.get("relay1", False))
        relay2 = bool(p.get("relay2", False))

        pv_payload = {
            "timestamp": ts,
            "power_kw": (pv_w or 0.0) / 1000.0,
            "voltage": 48.0,
            "current_a": ((pv_w or 0.0) / 48.0),
            "source": "usb_fallback",
            "reason": p.get("reason"),
        }
        self._mqtt.publish(sensor_pv_topic(prefix), json.dumps(pv_payload), qos=1, retain=False)

        battery_payload = {
            "timestamp": ts,
            "soc_percent": batt_soc or 0.0,
            "voltage": 48.0,
            "current_a": (((pv_w or 0.0) - (load_w or 0.0)) / 48.0),
            "source": "usb_fallback",
            "reason": p.get("reason"),
        }
        self._mqtt.publish(sensor_battery_topic(prefix), json.dumps(battery_payload), qos=1, retain=False)

        # Keep ext_ids aligned with firmware relay mapping.
        load1_kw = 0.015 if relay1 else 0.0
        load2_kw = 0.010 if relay2 else 0.0
        l1_payload = {"timestamp": ts, "power_kw": load1_kw, "state": "on" if relay1 else "off", "source": "usb_fallback"}
        l2_payload = {"timestamp": ts, "power_kw": load2_kw, "state": "on" if relay2 else "off", "source": "usb_fallback"}
        self._mqtt.publish(sensor_load_topic(prefix, "proto_led_a"), json.dumps(l1_payload), qos=1, retain=False)
        self._mqtt.publish(sensor_load_topic(prefix, "proto_led_b"), json.dumps(l2_payload), qos=1, retain=False)

        log.info("USB fallback bridged -> MQTT (reason=%s, pv_w=%.1f, soc=%.1f)", p.get("reason"), pv_w or 0.0, batt_soc or 0.0)


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None

