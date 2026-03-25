#!/usr/bin/env python3
"""
Raspberry Pi gateway emulator:
- publishes PV/battery/load telemetry to MQTT
- subscribes to relay command topics and updates load states
- publishes command acknowledgements

Run from project root:
  python -m simulator.pi_emulator --host localhost --port 1883
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Dict

import paho.mqtt.client as mqtt

from simulator.simulator import HardwareSimulator, default_appliances


def sensor_pv_topic(prefix: str) -> str:
    return f"{prefix}/sensors/pv"


def sensor_battery_topic(prefix: str) -> str:
    return f"{prefix}/sensors/battery"


def sensor_load_topic(prefix: str, appliance_external_id: str) -> str:
    return f"{prefix}/sensors/load/{appliance_external_id}"


def relay_cmd_wildcard(prefix: str) -> str:
    return f"{prefix}/cmd/relay/+"


def relay_ack_topic(prefix: str, appliance_external_id: str) -> str:
    return f"{prefix}/ack/relay/{appliance_external_id}"


def parse_relay_topic(prefix: str, topic: str) -> str | None:
    base = f"{prefix}/cmd/relay/"
    if not topic.startswith(base):
        return None
    appliance_id = topic[len(base) :]
    return appliance_id or None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic-prefix", default="microgrid")
    p.add_argument("--interval-seconds", type=int, default=5)
    p.add_argument("--pv-capacity-kw", type=float, default=1.0)
    p.add_argument("--battery-capacity-kwh", type=float, default=2.4)
    p.add_argument("--initial-soc-percent", type=float, default=70.0)
    p.add_argument("--cloud-factor", type=float, default=0.9)
    args = p.parse_args()

    prefix = args.topic_prefix.strip().strip("/")
    simulator = HardwareSimulator(
        pv_capacity_kw=args.pv_capacity_kw,
        battery_capacity_kwh=args.battery_capacity_kwh,
        initial_soc_percent=args.initial_soc_percent,
        appliances=default_appliances(),
        cloud_factor=args.cloud_factor,
    )
    appliance_states: Dict[str, bool] = {a["id"]: True for a in default_appliances()}

    client = mqtt.Client(client_id="smart-microgrid-pi-emulator", protocol=mqtt.MQTTv311)

    def on_connect(c: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc == 0:
            c.subscribe(relay_cmd_wildcard(prefix), qos=1)

    def on_message(c: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        appliance_id = parse_relay_topic(prefix, msg.topic)
        if appliance_id is None:
            return
        try:
            body = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        is_on = bool(body.get("is_on", True))
        appliance_states[appliance_id] = is_on
        ack = {
            "appliance_id": appliance_id,
            "applied_state": "on" if is_on else "off",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        c.publish(relay_ack_topic(prefix, appliance_id), json.dumps(ack), qos=0, retain=False)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, int(args.port), 30)
    client.loop_start()

    try:
        while True:
            now = datetime.now(timezone.utc)
            reading = simulator.tick(now, appliance_states=appliance_states)
            ts = reading["timestamp"]
            pv = dict(reading["pv"])
            pv["timestamp"] = ts
            battery = dict(reading["battery"])
            battery["timestamp"] = ts
            client.publish(sensor_pv_topic(prefix), json.dumps(pv), qos=1, retain=False)
            client.publish(sensor_battery_topic(prefix), json.dumps(battery), qos=1, retain=False)
            for load in reading["loads"]:
                payload = {
                    "appliance_id": load["appliance_id"],
                    "power_kw": load["power_kw"],
                    "state": load["state"],
                    "timestamp": ts,
                }
                client.publish(
                    sensor_load_topic(prefix, load["appliance_id"]),
                    json.dumps(payload),
                    qos=1,
                    retain=False,
                )
            time.sleep(max(1, int(args.interval_seconds)))
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
