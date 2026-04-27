# Hardware Mode Setup Guide

Quick reference for running Smart Microgrid Manager with real ESP32 hardware (MQTT ingest mode).

## Prerequisites

✅ ESP32 gateway running firmware with MQTT (see `README.md` in this directory)  
✅ MQTT broker running (Mosquitto or Docker)  
✅ Backend MySQL database set up  
✅ Network connectivity between ESP32, MQTT broker, and backend server  

## Step 1: Configure MQTT Broker

### Option A: Local Mosquitto (Linux/Mac)

```bash
# Install
sudo apt install mosquitto mosquitto-clients

# Start
sudo systemctl start mosquitto
sudo systemctl enable mosquitto  # Auto-start on boot

# Verify running
mosquitto -v &  # or check with `ps aux | grep mosquitto`

# Allow external connections (edit /etc/mosquitto/mosquitto.conf):
# Add or uncomment:
listener 1883
protocol mqtt
allow_anonymous true
```

### Option B: Docker

```bash
docker run -d -p 1883:1883 --name mosquitto eclipse-mosquitto

# Verify
docker logs mosquitto
```

### Option C: Other Systems

Check: https://mosquitto.org/download/

## Step 2: Configure Backend for Hardware Mode

Edit `backend/.env`:

```bash
# Enable hardware mode (disable simulator)
MICROGRID_USE_HARDWARE_SIMULATION=false

# Keep controller loop running
MICROGRID_CONTROLLER_LOOP_ENABLED=true

# MQTT Configuration
MICROGRID_MQTT_HOST=192.168.1.100    # Your MQTT broker IP (or "localhost" if on same machine)
MICROGRID_MQTT_PORT=1883
MICROGRID_MQTT_TOPIC_PREFIX=microgrid

# Database (must be running)
MICROGRID_DATABASE_URL=mysql+aiomysql://microgrid:your_password@localhost:3306/smart_microgrid

# Keep other settings as needed
MICROGRID_WEATHER_FORECAST_ENABLED=true
MICROGRID_WEATHER_LATITUDE=-17.8
MICROGRID_WEATHER_LONGITUDE=31.05
```

## Step 3: Configure ESP32 Firmware

Edit `esp32_gateway.ino`:

```cpp
const char* SSID           = "Chisedzi";
const char* PASSWORD       = "3475mash@";
const char* MQTT_BROKER    = "192.168.1.100";  // Your MQTT broker
const int   MQTT_PORT      = 1883;
const char* MQTT_PREFIX    = "microgrid";
```

Upload to ESP32 (see firmware `README.md`).

## Step 4: Start Services

### Terminal 1: MQTT Broker

```bash
# Ensure Mosquitto is running
sudo systemctl start mosquitto

# Or run in Docker
docker run -d -p 1883:1883 eclipse-mosquitto
```

### Terminal 2: Backend

```bash
cd /home/lester/Documents/smart-microgrid-manager
source .venv/bin/activate
cd backend

# Run with hardware mode enabled
PYTHONPATH=.. uvicorn app.main:app --reload --port 8001
```

Watch for:
```
[INFO] Starting backend (mode=hardware_ingest, db=mysql+...)
[INFO] MQTT ingest: connecting to 192.168.1.100:1883
[INFO] MQTT ingest: subscribed to microgrid/sensors/#
```

### Terminal 3: Web UI

```bash
cd /home/lester/Documents/smart-microgrid-manager/webui
npm run dev
```

### Terminal 4: Monitor MQTT (Optional)

```bash
mosquitto_sub -h 192.168.1.100 -t "microgrid/#" -v
```

Watch for readings from ESP32:
```
microgrid/sensors/pv {"timestamp":"2026-04-21T10:30:45Z","power_kw":0.15,"voltage":40.0,"current_a":3.75}
microgrid/sensors/battery {"timestamp":"2026-04-21T10:30:45Z","soc_percent":85.0,"voltage":48.0,"current_a":2.5}
microgrid/sensors/load/load_01 {"timestamp":"2026-04-21T10:30:45Z","power_kw":0.015,"state":"on"}
```

## Step 5: Verify Data Flow

### Check Backend Status Endpoint

```bash
curl http://localhost:8001/status
```

Should return:
```json
{
  "pv_power_kw": 0.15,
  "battery_soc_percent": 85.0,
  "total_load_kw": 0.025,
  "timestamp": "2026-04-21T10:30:45Z"
}
```

### Check MQTT Health

```bash
curl http://localhost:8001/health
```

Should show:
```json
{
  "mqtt": {
    "connected": true,
    "broker_host": "192.168.1.100",
    "broker_port": 1883,
    "last_message_at": "2026-04-21T10:30:45Z"
  }
}
```

### View History

```bash
curl http://localhost:8001/status/history?hours=1
```

Returns time-series data from last hour.

## Step 6: Test Relay Control

### From Web UI

Visit: `http://localhost:5173`  
→ **Appliances** page  
→ Toggle appliance on/off  
→ Check ESP32 serial monitor for relay commands

### From Command Line

```bash
# Send relay command
mosquitto_pub -h 192.168.1.100 -t "microgrid/cmd/relay/load_01" -m '{"state":false}'

# Monitor relay acknowledgment
mosquitto_sub -h 192.168.1.100 -t "microgrid/ack/relay/load_01" -v
```

## Troubleshooting

### Backend Can't Connect to MQTT

```
ERROR: MQTT broker unreachable at 192.168.1.100:1883
```

**Fix:**
- Verify Mosquitto is running: `sudo systemctl status mosquitto`
- Check IP address: `mosquitto -v` should show what it's listening on
- Test manually: `mosquitto_sub -h 192.168.1.100 -t "test" -v` (should block, waiting for messages)
- Check firewall: `sudo ufw allow 1883`

### ESP32 Connected but No Data Reaching Backend

**Check:**
1. Verify ESP32 publishes: `mosquitto_sub -h <MQTT_IP> -t "microgrid/sensors/#" -v`
2. Check backend log: Look for "MQTT ingest" messages and timestamps
3. Verify backend `.env`: `MICROGRID_USE_HARDWARE_SIMULATION=false`
4. Confirm database is running: `mysql -u microgrid -p -h localhost -e "SELECT COUNT(*) FROM smart_microgrid.pv_readings;"`

### Relay Commands Not Reaching ESP32

**Check:**
1. Monitor ESP32 subscription: `mosquitto_sub -h <MQTT_IP> -t "microgrid/cmd/relay/#" -v`
2. Send test command: `mosquitto_pub -h <MQTT_IP> -t "microgrid/cmd/relay/load_01" -m '{"state":true}'`
3. Check ESP32 serial output for ACK (acknowledgment should appear)

### Data Not Being Saved to Database

**Check:**
1. MySQL connection: `mysql -u microgrid -p -h localhost smart_microgrid`
2. Tables exist: `SHOW TABLES;` (should list `pv_readings`, `battery_readings`, `load_readings`)
3. Database URL is correct in `.env`: `MICROGRID_DATABASE_URL=mysql+...`
4. Backend logs show "Persisted PV/Battery/Load reading"

## Network Diagram

```
┌─────────────┐     WiFi      ┌──────────────┐      MQTT      ┌────────────────┐
│   ESP32     │──────────────→ │ WiFi Router  │──────────────→ │   MQTT Broker  │
│  (Gateway)  │                │              │  ← Relay Cmds  │ (Mosquitto)    │
└─────────────┘                └──────────────┘                └────────────────┘
       │                                                               │
       │ Sensors                                                      │
       │ (DHT11, Light)                                         MQTT Subscriptions
       ▼                                                               │
  Publishes:                                                          │
  • PV readings                                                       ▼
  • Battery SOC                                   ┌──────────────────────────────┐
  • Load status                                   │ Backend (FastAPI + SQLAlchemy)
                                                  ├──────────────────────────────┤
                                                  │ • MQTT Ingest Service        │
                                                  │ • Persists to MySQL          │
                                                  │ • Runs IEBA Scheduler        │
                                                  │ • API: /status, /forecast    │
                                                  └──────────────────────────────┘
                                                          │
                                                          │ HTTP
                                                          ▼
                                                  ┌──────────────────────────────┐
                                                  │  Web UI (React + Vite)       │
                                                  │  • Dashboard                 │
                                                  │  • Forecast                  │
                                                  │  • Schedule & Control        │
                                                  └──────────────────────────────┘
```

## Next Steps

1. **Monitor in real-time**: Use web UI Dashboard to watch PV/battery/load data stream
2. **Run IEBA scheduler**: Visit `/schedule` → Click "Run IEBA" to optimize appliance scheduling
3. **Check forecasts**: `/forecast` shows 24h generation/consumption prediction
4. **Enable scheduled training**: `/training` page to auto-retrain LSTM models
5. **Production hardening**: Add alerts, monitoring, logging (see backend docs)

## Support

For issues:
- Check ESP32 Serial Monitor (115200 baud)
- Review backend logs: `PYTHONPATH=.. uvicorn app.main:app --log-level debug`
- Test MQTT independently: `mosquitto_sub` / `mosquitto_pub`
- Verify network connectivity: `ping <ESP32_IP>`, `ping <MQTT_IP>`
