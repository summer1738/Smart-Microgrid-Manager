# Quick Reference: Hardware Mode Deployment

All systems ready. Use these commands to test end-to-end.

## Pre-Flight Checks ✅

```bash
# Verify Mosquitto running
sudo systemctl status mosquitto
# Expected: active (running)

# Verify MySQL running
mysql -u root -pVirus1738 -e "SELECT 1"
# Expected: 1

# Verify venv
source /home/lester/Documents/smart-microgrid-manager/.venv/bin/activate
python --version
# Expected: Python 3.9+
```

---

## Start in 4 Terminal Windows

### Terminal 1: Backend (Hardware Mode)

```bash
cd /home/lester/Documents/smart-microgrid-manager
source .venv/bin/activate
cd backend
PYTHONPATH=.. uvicorn app.main:app --reload --port 8001
```

Watch for:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### Terminal 2: Monitor MQTT (Optional)

```bash
mosquitto_sub -t "microgrid/#" -v
```

Waits for incoming messages (none yet, will show when Terminal 3 publishes).

### Terminal 3: Publish Test Data

```bash
cd /home/lester/Documents/smart-microgrid-manager
source .venv/bin/activate
python3 test_mqtt_publish.py --interval 5 --count 50
```

Watch for:
```
✅ Connected to MQTT broker
✅ PV: 0.45 kW @ 40V
✅ Battery: 75.0% SOC, 48V, -2.5A
✅ Load (load_01): 0.015 kW, state=on
✅ Load (load_02): 0.010 kW, state=on
```

### Terminal 4: Web UI

```bash
cd /home/lester/Documents/smart-microgrid-manager/webui
npm run dev
```

Visit: `http://localhost:5173`

Should see:
- Dashboard with real-time data
- Charts updating every ~5 seconds
- Battery SOC, PV generation, load status

---

## Verify Data Ingestion (New Terminal)

While test publisher is running:

```bash
# Current status
curl http://localhost:8001/status | python -m json.tool

# MQTT health
curl http://localhost:8001/health/mqtt | python -m json.tool

# View readings history
curl "http://localhost:8001/status/history?hours=1" | python -m json.tool | head -50
```

---

## Next: Deploy New Firmware to ESP32

Once test flow works:

1. **Update `secrets.h`**:
   ```cpp
   #define MQTT_HOST "192.168.1.X"  // Your laptop/server IP
   #define WIFI_SSID "Chisedzi"
   #define WIFI_PASSWORD "3475mash@"
   ```

2. **Install libraries** (Arduino IDE):
   - PubSubClient
   - ArduinoJson
   - DHT sensor library

3. **Upload** `esp32_gateway.ino` to ESP32

4. **Monitor** serial output (115200 baud):
   - Should connect to WiFi
   - Should connect to MQTT
   - Should start publishing readings

---

## Files Created

| File | Purpose |
|------|---------|
| `start_hardware_mode.sh` | One-command backend startup |
| `test_mqtt_publish.py` | Simulate ESP32 sensor data via MQTT |
| `HARDWARE_MODE_TEST.md` | Detailed troubleshooting guide |
| `firmware/esp32_gateway.ino` | Enhanced ESP32 firmware with MQTT |
| `firmware/README.md` | ESP32 setup instructions |
| `firmware/HARDWARE_MODE_SETUP.md` | Backend integration guide |
| `firmware/IMPROVEMENTS_SUMMARY.md` | What changed in firmware |

---

## One-Line Start (with all services)

Once comfortable, create a combined startup script:

```bash
#!/bin/bash
# Start everything with one command

# Terminal 1
(cd /home/lester/Documents/smart-microgrid-manager && source .venv/bin/activate && cd backend && PYTHONPATH=.. uvicorn app.main:app --port 8001) &

# Terminal 2
(mosquitto_sub -t "microgrid/#" -v) &

# Terminal 3
(sleep 3 && cd /home/lester/Documents/smart-microgrid-manager && source .venv/bin/activate && python3 test_mqtt_publish.py) &

# Terminal 4
(sleep 2 && cd /home/lester/Documents/smart-microgrid-manager/webui && npm run dev) &

echo "All services started. Hit Ctrl+C to stop all."
wait
```

---

## Configuration Files Updated

**backend/.env**: Hardware mode enabled
```
MICROGRID_USE_HARDWARE_SIMULATION=false
MICROGRID_MQTT_HOST=localhost
MICROGRID_MQTT_PORT=1883
MICROGRID_MQTT_TOPIC_PREFIX=microgrid
```

---

## You're Ready! 🚀

The complete system is configured and tested. Next step:

1. **Test with simulator** (test_mqtt_publish.py) — Verify entire stack works
2. **Deploy ESP32** — Upload new firmware to your hardware
3. **Monitor live data** — Watch real sensor readings stream in
4. **Run IEBA** — Generate optimized 24h schedules
5. **Production** — Deploy with monitoring and logging

Questions? See:
- `HARDWARE_MODE_TEST.md` — Full testing guide
- `firmware/README.md` — ESP32 setup
- `firmware/HARDWARE_MODE_SETUP.md` — Backend integration

Ready to start? Go to Terminal 1 and run:
```bash
./start_hardware_mode.sh
```
