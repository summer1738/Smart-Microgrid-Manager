# Hardware Mode End-to-End Test Guide

Complete walkthrough to test MQTT-based hardware mode without physical ESP32.

## Status Check ✅

Your system is configured and ready:
- ✅ Mosquitto running on `localhost:1883`
- ✅ Backend configured for hardware mode (MQTT ingest)
- ✅ MySQL database running
- ✅ LSTM models trained and ready
- ✅ Test publisher script created

---

## Quick Start (5 minutes)

### Terminal 1: Start Backend

```bash
cd /home/lester/Documents/smart-microgrid-manager
source .venv/bin/activate
./start_hardware_mode.sh
```

Watch for:
```
[INFO] MQTT ingest: connecting to localhost:1883
[INFO] MQTT ingest: subscribed to microgrid/sensors/#
```

### Terminal 2: Monitor MQTT (optional)

```bash
mosquitto_sub -t "microgrid/#" -v
```

Watch for incoming messages every 10 seconds.

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
...
```

### Terminal 4: Start Web UI

```bash
cd /home/lester/Documents/smart-microgrid-manager/webui
npm run dev
```

Visit: `http://localhost:5173`

---

## Verify Data Flow

### 1. Check Backend Status Endpoint

```bash
curl http://localhost:8001/status | jq
```

Expected output:
```json
{
  "pv_power_kw": 0.45,
  "battery_soc_percent": 75.0,
  "total_load_kw": 0.025,
  "timestamp": "2026-04-21T10:30:45Z"
}
```

### 2. Check MQTT Health

```bash
curl http://localhost:8001/health | jq '.mqtt'
```

Expected output:
```json
{
  "connected": true,
  "broker_host": "localhost",
  "broker_port": 1883,
  "last_message_at": "2026-04-21T10:30:45Z",
  "last_pv_at": "2026-04-21T10:30:40Z",
  "last_battery_at": "2026-04-21T10:30:40Z"
}
```

### 3. View Readings History

```bash
curl "http://localhost:8001/status/history?hours=1" | jq '.pv_series | .[0:3]'
```

Expected output:
```json
[
  {
    "timestamp": "2026-04-21T10:25:00Z",
    "power_kw": 0.35,
    "voltage": 40.0,
    "current_a": 8.75
  },
  ...
]
```

### 4. Watch Dashboard in Real-Time

Open `http://localhost:5173` in browser:
- Battery SOC should update every 10 seconds
- PV generation should show variability
- Charts should plot incoming data
- Load indicators should show status

---

## Testing Scenarios

### Scenario 1: Stable Generation (Day)

Run test publisher with default settings:
```bash
python3 test_mqtt_publish.py --interval 5 --count 100
```

Expected: PV power stays high (0.4-0.6 kW), battery charges, SOC rises.

### Scenario 2: Low Battery Alert

Modify test script to simulate low battery:
```python
# In test_mqtt_publish.py, change:
soc = min(100, max(10, 15.0))  # Force low battery
```

Then run. Watch for:
- ⚠️ Battery indicator turns red
- 🔔 LED warning triggered (if connected)

### Scenario 3: Night Time (No Generation)

Modify test script:
```python
# Force nighttime simulation
hour = 20  # 8 PM
```

Expected: PV = 0 kW, battery discharges, SOC drops.

### Scenario 4: Relay Commands

Test relay command path (once real ESP32 connected):
```bash
# Send relay ON
mosquitto_pub -t "microgrid/cmd/relay/load_01" -m '{"state":true}'

# Send relay OFF
mosquitto_pub -t "microgrid/cmd/relay/load_01" -m '{"state":false}'
```

### Scenario 5: Run IEBA Scheduler

Once data is flowing:
```bash
curl -X POST http://localhost:8001/schedule/run
```

Expected: 24-hour appliance schedule generated and stored.

View result:
```bash
curl http://localhost:8001/schedule | jq '.schedule_slots | .[0:5]'
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check Python venv
source .venv/bin/activate
python --version  # Should be 3.9+

# Check dependencies
pip list | grep -i fastapi sqlalchemy

# Check port 8001 is free
lsof -i :8001
# If occupied: kill -9 <PID>
```

### No MQTT Connection

```bash
# Verify Mosquitto
sudo systemctl status mosquitto

# Test MQTT manually
mosquitto_pub -t test -m "hello"
mosquitto_sub -t test -v
# Should see: test hello

# Check firewall
sudo ufw status | grep 1883
```

### No Data in Dashboard

```bash
# Monitor MQTT traffic
mosquitto_sub -t "microgrid/#" -v

# Check backend log
# Should show: "MQTT ingest: message received"

# Verify database
mysql -u microgrid -pVirus1738 smart_microgrid -e "SELECT COUNT(*) as readings FROM pv_readings;"
```

### Web UI Not Loading

```bash
# Check Node.js
node --version  # Should be 16+

# Reinstall if needed
cd webui
rm -rf node_modules package-lock.json
npm install
npm run dev
```

---

## Next Steps After Verification

### 1. Deploy New Firmware to ESP32

Once data flow works:
1. Upload `esp32_gateway.ino` to your physical ESP32
2. Verify in Serial Monitor it connects to WiFi & MQTT
3. Watch data flow from real hardware

### 2. Configure Real Sensors

Current firmware simulates readings. Replace with real sensors:
- ADC for PV voltage/current
- INA219 for battery current
- DHT11 for temperature
- GPIO for light sensor

### 3. Set Up Relay Hardware

Connect actual relays to GPIO 25 & 33 for real load control.

### 4. Enable Scheduled Training

Web UI → Training page:
- Enable "Scheduled retraining"
- Set interval (e.g., every 6 hours)
- Monitor model performance

### 5. Run in Production

Once tested:
```bash
# Disable reload mode (faster, production-ready)
cd backend
PYTHONPATH=.. uvicorn app.main:app --port 8001

# Keep running with systemd
sudo nano /etc/systemd/system/microgrid.service
# [Service]
# ExecStart=/home/lester/Documents/smart-microgrid-manager/.venv/bin/uvicorn app.main:app --port 8001
# WorkingDirectory=/home/lester/Documents/smart-microgrid-manager/backend
# Environment="PYTHONPATH=.."
```

---

## Performance Baseline

With test publisher running:

| Metric | Expected |
|--------|----------|
| MQTT messages/second | 0.4 (1 per 2.5s × 4 topics) |
| Backend response time | <100ms |
| Database write latency | <50ms |
| Web dashboard update | <2s |
| Memory usage (backend) | ~200MB |
| CPU usage (backend) | <5% |

---

## Monitoring Dashboard

Once running, useful endpoints:

```bash
# Real-time status
watch -n 1 'curl -s http://localhost:8001/status | jq'

# Health check
curl -s http://localhost:8001/health | jq

# Recent history (last hour)
curl -s "http://localhost:8001/status/history?hours=1" | jq '.pv_series | length'

# Appliances status
curl -s http://localhost:8001/appliances | jq '.appliances | .[] | {id, name, is_on}'

# Schedule status
curl -s http://localhost:8001/schedule | jq '.schedule_slots | length'
```

---

## Common Commands

```bash
# Stop all services
pkill -f uvicorn
pkill -f "npm run dev"
pkill -f mosquitto_sub

# View real-time MQTT
mosquitto_sub -h localhost -t "microgrid/#" -v

# Publish test data
mosquitto_pub -h localhost -t "microgrid/sensors/pv" -m '{"power_kw": 0.5}'

# Monitor backend
tail -f ~/.pm2/logs/backend-error.log

# Clear test data
mysql -u microgrid -pVirus1738 smart_microgrid -e "DELETE FROM pv_readings WHERE DATE(timestamp) = CURDATE();"

# Reset database
mysql -u microgrid -pVirus1738 -e "DROP DATABASE smart_microgrid; CREATE DATABASE smart_microgrid;"
```

---

You're ready to test! Start with Terminal 1 (backend), then Terminal 2 (MQTT monitor), then Terminal 3 (test publisher).

Ready to proceed?
