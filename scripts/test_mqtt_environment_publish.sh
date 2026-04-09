#!/usr/bin/env bash
# Publish one sample environment JSON to the same topic the ESP32 uses.
# Requires: mosquitto-clients (mosquitto_pub)
#
# Usage (from project root):
#   ./scripts/test_mqtt_environment_publish.sh
#   MQTT_HOST=192.168.1.10 ./scripts/test_mqtt_environment_publish.sh   # broker elsewhere
#
# After running, curl http://localhost:8001/status and check ambient_* / esp32_gateway,
# or GET /health/mqtt → last_environment_at.

set -euo pipefail
HOST="${MQTT_HOST:-127.0.0.1}"
PORT="${MQTT_PORT:-1883}"
PREFIX="${MQTT_TOPIC_PREFIX:-microgrid}"
TOPIC="${PREFIX}/sensors/environment"

PAYLOAD='{"temperature_c":22.5,"humidity_percent":55.0,"light_digital":1,"dht_ok":true,"light_ok":true,"wifi_rssi_dbm":-48,"free_heap_bytes":200000,"uptime_ms":12345,"pins":{"dht":4,"light_do":21,"led_a":25,"led_b":26,"buzz_a":27,"buzz_b":14},"timestamp":""}'

echo "Publishing to ${HOST}:${PORT} topic ${TOPIC}"
mosquitto_pub -h "$HOST" -p "$PORT" -t "$TOPIC" -m "$PAYLOAD"
echo "Done. If the backend is in hardware_ingest mode, /status should show ambient values within a few seconds."
