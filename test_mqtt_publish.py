#!/usr/bin/env python3
"""
Test MQTT Publisher - Simulates ESP32 gateway publishing sensor data
Usage: python3 test_mqtt_publish.py [--interval 10] [--count 100]
"""

import json
import time
import argparse
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_PREFIX = "microgrid"

# Global state
client = None
message_count = 0

def get_iso_timestamp():
    """Get current time in ISO 8601 format"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def publish_pv_reading(power_kw=0.35, voltage=40.0):
    """Publish PV generation reading"""
    global client, message_count
    
    payload = {
        "timestamp": get_iso_timestamp(),
        "power_kw": power_kw,
        "voltage": voltage,
        "current_a": power_kw * 1000 / voltage if voltage > 0 else 0
    }
    
    topic = f"{MQTT_PREFIX}/sensors/pv"
    result = client.publish(topic, json.dumps(payload))
    message_count += 1
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"✅ PV: {power_kw:.2f} kW @ {voltage}V")
    else:
        print(f"❌ PV publish failed: {result.rc}")

def publish_battery_reading(soc_percent=75.0, voltage=48.0, current=-2.5):
    """Publish battery reading"""
    global client, message_count
    
    payload = {
        "timestamp": get_iso_timestamp(),
        "soc_percent": soc_percent,
        "voltage": voltage,
        "current_a": current
    }
    
    topic = f"{MQTT_PREFIX}/sensors/battery"
    result = client.publish(topic, json.dumps(payload))
    message_count += 1
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"✅ Battery: {soc_percent:.1f}% SOC, {voltage}V, {current:.1f}A")
    else:
        print(f"❌ Battery publish failed: {result.rc}")

def publish_load_reading(appliance_id, power_kw=0.015, state="on"):
    """Publish load reading"""
    global client, message_count
    
    payload = {
        "timestamp": get_iso_timestamp(),
        "power_kw": power_kw,
        "state": state
    }
    
    topic = f"{MQTT_PREFIX}/sensors/load/{appliance_id}"
    result = client.publish(topic, json.dumps(payload))
    message_count += 1
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"✅ Load ({appliance_id}): {power_kw:.3f} kW, state={state}")
    else:
        print(f"❌ Load publish failed: {result.rc}")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("🔌 Connected to MQTT broker")
    else:
        print(f"❌ MQTT connection failed: {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"⚠️  Unexpected MQTT disconnection: {rc}")
    else:
        print("🔌 Disconnected from MQTT broker")

def main():
    global client
    
    parser = argparse.ArgumentParser(description="Test MQTT publisher for microgrid")
    parser.add_argument("--interval", type=int, default=10, help="Publish interval in seconds")
    parser.add_argument("--count", type=int, default=100, help="Number of messages to publish (0=infinite)")
    parser.add_argument("--broker", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    args = parser.parse_args()
    
    # Create MQTT client
    client = mqtt.Client(client_id="test-publisher")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    print("=" * 60)
    print("🧪 MQTT Test Publisher - Microgrid Simulator")
    print("=" * 60)
    print(f"Broker: {args.broker}:{args.port}")
    print(f"Prefix: {MQTT_PREFIX}")
    print(f"Interval: {args.interval}s")
    print(f"Messages: {args.count if args.count > 0 else 'infinite'}")
    print("")
    
    # Connect
    try:
        client.connect(args.broker, args.port, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return
    
    # Wait for connection
    time.sleep(2)
    
    if not client.is_connected():
        print("❌ Failed to connect to MQTT broker")
        return
    
    print("Publishing sensor data...")
    print("-" * 60)
    
    iteration = 0
    try:
        while True:
            iteration += 1
            
            # Simulate dynamic data
            hour = (datetime.now().hour) % 24
            
            # PV: high during day, low at night
            if 6 <= hour <= 18:
                pv_power = 0.5 + 0.4 * (1 - abs(hour - 12) / 6)  # Peak at noon
                pv_voltage = 38 + 4 * (1 - abs(hour - 12) / 6)
            else:
                pv_power = 0.0
                pv_voltage = 0.0
            
            # Battery: discharge during day, charge at night
            base_soc = 70.0
            soc = base_soc + (0 if 6 <= hour <= 18 else 15)
            soc = min(100, max(10, soc))
            
            # Battery current: discharging during peak load
            if 6 <= hour <= 18:
                batt_current = -2.5  # Discharging
            else:
                batt_current = 1.5   # Charging
            
            # Publish all readings
            print(f"\n[{iteration}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            publish_pv_reading(pv_power, pv_voltage if pv_power > 0 else 0)
            publish_battery_reading(soc, 48.0, batt_current)
            publish_load_reading("load_01", 0.015, "on")
            publish_load_reading("load_02", 0.010, "on")
            
            # Check count
            if args.count > 0 and iteration >= args.count:
                print("\n" + "-" * 60)
                print(f"✅ Published {message_count} messages successfully")
                break
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")
    
    finally:
        print(f"\n📊 Total messages: {message_count}")
        client.loop_stop()
        client.disconnect()
        print("✅ Disconnected")

if __name__ == "__main__":
    main()
