// Local secrets for ESP32.
// This file is intentionally NOT checked into git. Keep it private.
#pragma once

// --- Wi‑Fi (2.4 GHz networks only on most ESP32; use your router SSID/password) ---
#define WIFI_SSID "kande2"
#define WIFI_PASSWORD "kingjaypaddy011322"

// #define WIFI_SSID "Chisedzi 2"
// #define WIFI_PASSWORD "3475mash@"

// --- MQTT broker (must be reachable over Wi‑Fi from the ESP32) ---
// IMPORTANT: Set this to the LAN IP of the PC running Mosquitto (e.g. 192.168.1.10) — NOT localhost.
// You can find it on the PC with: hostname -I
#define MQTT_HOST "192.168.1.89"
#define MQTT_PORT 1883

// Must match backend MICROGRID_MQTT_TOPIC_PREFIX (default: microgrid).
#define MQTT_TOPIC_PREFIX "microgrid"

// If the digital light sensor is not wired, uncomment to disable it:
// #define LIGHT_SENSOR_ENABLED 0

