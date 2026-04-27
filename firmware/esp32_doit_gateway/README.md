# ESP32 Microgrid Gateway Firmware

Production-ready firmware for ESP32 DOIT DevKit with MQTT integration to Smart Microgrid Manager.

## Features

✅ **MQTT Integration** — Publishes sensor data, subscribes to relay commands  
✅ **Web Dashboard** — Local monitoring + API endpoints  
✅ **Relay Control** — Remote on/off control via backend or web UI  
✅ **Error Handling** — WiFi/MQTT reconnection, sensor validation  
✅ **ISO Timestamps** — NTP sync for accurate timestamps  
✅ **Modular Code** — Clean logging, well-documented functions  
✅ **Multi-Load Support** — Handles multiple appliances with relay control  

## Hardware Requirements

- ESP32 DOIT DevKit (or compatible)
- DHT11 Temperature/Humidity Sensor
- Light sensor (photodiode or LDR)
- 2x Relay modules (for load control)
- 6x LEDs (battery level, load status indicators)
- Buzzer for critical alerts
- USB cable for programming
- 5V power supply

## Pin Configuration

```
GPIO 4    - DHT11 data pin
GPIO 21   - Light sensor (digital input)
GPIO 32   - Buzzer (active HIGH)
GPIO 13   - LED Battery High (>70%)
GPIO 12   - LED Battery Medium (40-70%)
GPIO 14   - LED Battery Low (<40%)
GPIO 27   - LED Load 1 Status
GPIO 26   - LED Load 2 Status
GPIO 25   - Relay 1 Control (Load 01)
GPIO 33   - Relay 2 Control (Load 02)
```

## Installation

### 1. Arduino IDE Setup

```bash
# Add ESP32 board to Arduino IDE:
# Preferences → Additional Board Manager URLs:
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

# Board Manager → Search "esp32" → Install by Espressif Systems
```

### 2. Install Required Libraries

In Arduino IDE, go to **Sketch → Include Library → Manage Libraries**:

- Search & install: **PubSubClient** (by Nick O'Leary) — MQTT client
- Search & install: **ArduinoJson** (by Benoit Blanchon) — JSON serialization
- Search & install: **DHT sensor library** (by Adafruit) — DHT11 support

Or via command line:
```bash
# Using Arduino CLI
arduino-cli lib install PubSubClient
arduino-cli lib install ArduinoJson
arduino-cli lib install "DHT sensor library"
```

### 3. Configure for Your Network

Edit `esp32_gateway.ino`:

```cpp
const char* SSID     = "YOUR_SSID";      // Your WiFi SSID
const char* PASSWORD = "YOUR_PASSWORD";  // Your WiFi password
const char* MQTT_BROKER = "192.168.1.100";  // Your MQTT broker IP
```

**MQTT Broker Options:**
- **Local Mosquitto**: `mosquitto install` on your PC/Pi, then use its IP
- **Backend PC**: Install Mosquitto on same machine as backend
- **Docker**: Run MQTT container locally

### 4. Upload to ESP32

1. Connect ESP32 via USB
2. In Arduino IDE:
   - **Tools → Board → ESP32 → ESP32 Dev Module**
   - **Tools → Port → /dev/ttyUSB0** (or your USB port)
   - **Sketch → Upload**
3. Monitor serial output:
   - **Tools → Serial Monitor** (115200 baud)

### 5. Set Up Mosquitto MQTT Broker (Linux/Mac)

```bash
# Install
sudo apt install mosquitto mosquitto-clients  # Linux
brew install mosquitto  # Mac

# Start service
sudo systemctl start mosquitto
mosquitto -c /etc/mosquitto/mosquitto.conf

# Test connection (from another terminal)
mosquitto_sub -h localhost -t "microgrid/#" -v
```

## Operation

### Local Web Dashboard

Once ESP32 is running, visit:
```
http://<ESP32_IP>:80
```

Replace `<ESP32_IP>` with the IP shown in Serial Monitor (e.g., `http://192.168.1.50`).

**Dashboard shows:**
- Battery SOC, Temperature, PV Generation
- WiFi/MQTT connection status
- Live relay toggle buttons
- Load status indicators

### MQTT Topics

#### Sensor Publishing (ESP32 → Backend)

**PV Readings**
```
Topic: microgrid/sensors/pv
Payload: {
  "timestamp": "2026-04-21T10:30:45Z",
  "power_kw": 0.15,
  "voltage": 40.0,
  "current_a": 3.75
}
```

**Battery Readings**
```
Topic: microgrid/sensors/battery
Payload: {
  "timestamp": "2026-04-21T10:30:45Z",
  "soc_percent": 85.0,
  "voltage": 48.0,
  "current_a": 2.5
}
```

**Load Readings**
```
Topic: microgrid/sensors/load/load_01
Payload: {
  "timestamp": "2026-04-21T10:30:45Z",
  "power_kw": 0.015,
  "state": "on"
}
```

#### Relay Commands (Backend → ESP32)

**Command Topic**
```
Topic: microgrid/cmd/relay/load_01
Payload: {"state": true}  // or false
```

**Acknowledgment Topic**
```
Topic: microgrid/ack/relay/load_01
Payload: {"state": true, "timestamp": "2026-04-21T10:30:45Z"}
```

## Testing MQTT

### From command line (if Mosquitto installed):

```bash
# Monitor all microgrid topics
mosquitto_sub -h 192.168.1.100 -t "microgrid/#" -v

# Send relay command
mosquitto_pub -h 192.168.1.100 -t "microgrid/cmd/relay/load_01" -m '{"state":true}'

# Monitor acknowledgments
mosquitto_sub -h 192.168.1.100 -t "microgrid/ack/relay/load_01" -v
```

## Backend Integration

### 1. Start Backend in Hardware Mode

```bash
cd /home/lester/Documents/smart-microgrid-manager
source .venv/bin/activate
cp backend/.env.example backend/.env

# Edit backend/.env:
# MICROGRID_USE_HARDWARE_SIMULATION=false  (hardware mode, not simulator)
# MICROGRID_MQTT_HOST=192.168.1.100       (your MQTT broker)
# MICROGRID_MQTT_PORT=1883
# MICROGRID_MQTT_TOPIC_PREFIX=microgrid
```

### 2. Start Backend

```bash
cd backend
PYTHONPATH=.. uvicorn app.main:app --reload --port 8001
```

### 3. Verify Data Ingestion

Check backend API:
```bash
curl http://localhost:8001/status
curl http://localhost:8001/status/history?hours=1
```

Should see PV, battery, and load readings from your ESP32.

## Troubleshooting

### ESP32 Won't Connect to WiFi

**Serial Output Shows "WIFI: Failed to connect"**
- Verify SSID and password in code
- Check WiFi signal strength (ensure ESP32 is in range)
- Restart router
- Try WPA2-PSK (avoid WPA3 if possible, less compatible)

### MQTT Connection Fails

**Serial Output Shows "MQTT: Failed (code: -4)"**
- Verify MQTT broker IP in code
- Ensure Mosquitto is running: `sudo systemctl status mosquitto`
- Check firewall: `sudo ufw allow 1883`
- Test connectivity: `nc -zv 192.168.1.100 1883`

### No Data in Backend

**Backend not receiving sensor data**
- Check MQTT topics match: `microgrid/sensors/pv`, etc.
- Monitor with: `mosquitto_sub -h 192.168.1.100 -t "microgrid/#" -v`
- Verify backend `.env`: `MICROGRID_USE_HARDWARE_SIMULATION=false`
- Check backend logs: Look for MQTT ingest messages

### DHT11 Readings Stuck

**Temperature shows "--" or doesn't update**
- DHT11 has 1-2 second minimum read interval (code respects this)
- Check wiring: GPIO 4 → DHT data pin
- Try different GPIO if pin is problematic
- Add 10kΩ pull-up resistor on data pin if intermittent

### Relay Not Responding to Commands

**Backend sends command but relay doesn't toggle**
- Check relay wiring: GPIO 25/33 to relay IN pins
- Verify relay power supply (separate from ESP32)
- Monitor serial: Should log "RELAY: load_01 -> ON/OFF"
- Check backend sends correct topic: `microgrid/cmd/relay/load_XX`

## Performance Tuning

### Sensor Publish Interval

Change in code (default 10s):
```cpp
const unsigned long PUBLISH_INTERVAL = 10000;  // milliseconds
```

### DHT Read Interval

Change in code (default 2s, don't go below ~1.5s):
```cpp
if (now - lastSensorRead < 2000) return;
```

### MQTT Keep-Alive

In `connectMqtt()`, adjust:
```cpp
if (mqttClient.connect("ESP32-Gateway", user, pass)) { // Add credentials if needed
```

## Firmware Updates

To push a new firmware version:

1. Edit `esp32_gateway.ino`
2. **Sketch → Verify/Compile** to check for errors
3. Connect ESP32 via USB
4. **Sketch → Upload**
5. Monitor serial output for startup messages

No need to restart backend; it will auto-reconnect when gateway reboots.

## Advanced: Implementing Real Sensors

Current firmware simulates readings. To use real sensors:

### Real PV Readings (ADC)

Replace in `readSensors()`:
```cpp
// Read ADC pin (e.g., GPIO 35 for voltage divider)
int rawAdc = analogRead(35);  // 0-4095
float adcVoltage = (rawAdc / 4095.0) * 3.3;  // Scale to 0-3.3V
// Map to your actual PV voltage range (e.g., 0-60V)
pvVoltage = adcVoltage * (60.0 / 3.3);
pvPower = pvVoltage * pvCurrent;
```

### Real Battery Current (INA219)

Install library: **Adafruit INA219**

```cpp
#include <Adafruit_INA219.h>
Adafruit_INA219 ina219;

void setup() {
  ina219.begin();
}

void readBatteryFromINA219() {
  batteryCurrent = ina219.getCurrent_mA() / 1000.0;  // Convert to A
  batteryVoltage = ina219.getBusVoltage_V();
}
```

## Support

For issues:
1. Check serial monitor (115200 baud)
2. Review troubleshooting section above
3. Test MQTT connectivity independently
4. Verify backend logs for ingest errors
