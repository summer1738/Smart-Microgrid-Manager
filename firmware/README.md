# ESP32 gateway firmware

Sketch: **`esp32_doit_gateway/`** — connects your **DOIT ESP32** breadboard build to the backend over **MQTT**, using the same topics as `simulator/pi_emulator.py`.

## What it does

- Publishes **PV** and **battery** telemetry (demo waveforms until you attach real hardware).
- Publishes **`…/sensors/environment`** with **DHT11** temperature/humidity and **digital light DO** (backend shows this on the **Dashboard** under “Ambient (ESP32)”).
- Publishes **load** telemetry for four appliances: two LEDs and two buzzer drivers.
- Subscribes to **relay commands** from the backend and drives GPIO **HIGH/LOW** for those loads.
- Prints DHT/light on **Serial** (115200 baud).

## Arduino IDE setup

1. Install **ESP32** board support (Boards Manager: esp32 by Espressif).
2. Libraries (Library Manager):
   - **PubSubClient** (Nick O’Leary)
   - **DHT sensor library** (Adafruit) — classic `DHT.h` / DHT11
3. Copy secrets and edit:

```bash
cp firmware/esp32_doit_gateway/secrets.h.example firmware/esp32_doit_gateway/secrets.h
```

Set **`WIFI_SSID`**, **`WIFI_PASSWORD`**, **`MQTT_HOST`** (IP of the machine running **Mosquitto**), and **`MQTT_PORT`** (usually `1883`). **`MQTT_TOPIC_PREFIX`** must match the backend (`microgrid` by default).

4. Open **`firmware/esp32_doit_gateway/esp32_doit_gateway.ino`**, select your **DOIT ESP32** board and port, upload.

## Wi‑Fi and MQTT (how the ESP32 connects)

The sketch already connects **through Wi‑Fi** using **`WiFi.begin(WIFI_SSID, WIFI_PASSWORD)`** in `setupWifiMqtt()` — there is no separate “Ethernet” path for this prototype.

1. **Same network as your PC** — The ESP32 must join the same **LAN** as the computer running Mosquitto (or a reachable broker). Use your home/office **SSID** and **password** in `secrets.h` (same router the PC uses).

2. **2.4 GHz** — Most ESP32 boards only support **2.4 GHz** Wi‑Fi. If your router has separate SSIDs for **5 GHz** and **2.4 GHz**, pick the **2.4 GHz** one.

3. **`MQTT_HOST` is not `localhost`** — From the ESP32’s point of view, **localhost** is the ESP32 itself. Set **`MQTT_HOST`** to the **PC’s LAN IP** (e.g. `192.168.1.50`). On Linux: `hostname -I`; on Windows: `ipconfig`. The PC and ESP32 must be able to **ping** each other (same subnet, no client isolation).

4. **Mosquitto must accept LAN clients** — On the PC, the broker should listen on **`0.0.0.0:1883`**, not only `127.0.0.1`, or the ESP32 cannot connect. See `scripts/mosquitto-listener-dev.conf.example` in the repo.

5. **Serial** — Open **115200 baud** after upload; you should see Wi‑Fi connection, then IP, then MQTT subscribe lines.

6. **Firewall** — Allow **TCP 1883** on the PC if you use `ufw` or similar.

## Backend and database

1. Run **Mosquitto** on the same network so the ESP32 can reach **`MQTT_HOST:MQTT_PORT`**.
2. In **`backend/.env`** set:
   - `MICROGRID_USE_HARDWARE_SIMULATION=false` so the backend uses MQTT ingest instead of the simulator.
   - `MICROGRID_MQTT_HOST` / `MICROGRID_MQTT_PORT` / `MICROGRID_MQTT_TOPIC_PREFIX` consistent with the ESP32.
3. Restart the backend.

## Register the four appliances

The sketch expects these **`external_id`** values (or change the `#define` lines in the `.ino`):

| `external_id` | GPIO | Role |
|---------------|------|------|
| `proto_led_a` | 25 | LED1 |
| `proto_led_b` | 26 | LED2 |
| `proto_buzz_a` | 27 | Buzzer1 (transistor base) |
| `proto_buzz_b` | 14 | Buzzer2 (transistor base) |

In the **Web UI → Appliances**, add four appliances with exactly those **external IDs** and rated power (any reasonable watts). The backend only stores load MQTT if the **`external_id`** exists in the database.

## Verify

- Serial Monitor at **115200**: WiFi IP, MQTT subscribe lines, DHT/light readings.
- **`GET /health/mqtt`** on the backend: should show MQTT connected and recent message times.
- **Dashboard**: PV/battery/load activity should update when telemetry runs and when you run **IEBA** / schedule so the backend publishes relay commands.

## Next steps (optional)

- Replace demo PV/battery JSON with real inverter/BMS fields when you have hardware.
- Ambient samples are **persisted** (`environment_readings`) and shown on the **Dashboard** as a 24h chart (`GET /status/history` → `ambient_points`).
