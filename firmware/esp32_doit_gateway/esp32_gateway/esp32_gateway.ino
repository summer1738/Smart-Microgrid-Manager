#include <DHT.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <WebServer.h>
#include <time.h>
#include "../secrets.h"

// ===== MQTT Configuration (from secrets.h) =====
const char* MQTT_BROKER = MQTT_HOST;
const int   MQTT_PORT_CFG = MQTT_PORT;
const char* MQTT_PREFIX = MQTT_TOPIC_PREFIX;

// ===== Pin Definitions =====
// ===============================
// LED & BUZZER PINS
// ===============================
#define WIFI_LED          2
#define LIGHT_LED         15
#define STATUS_LED        26
#define CHARGING_LED      27
#define FAULT_LED         14
#define BUZZER_PIN        13

// ===============================
// BATTERY MONITORING
// ===============================
#define BATTERY_PIN       34

// Voltage divider resistors
const float R1 = 100000.0;
const float R2 = 100000.0;

// ADC reference
const float ADC_REFERENCE = 3.3;
const int ADC_RESOLUTION = 4095;

#define DHT_PIN         4
#define DHT_TYPE        DHT11
#define LIGHT_SENSOR    21
#define LED_LOAD_1      27
#define LED_LOAD_2      26
#define RELAY_LOAD_1    25  // Control relay for Load 1
#define RELAY_LOAD_2    33  // Control relay for Load 2
// Keep these aligned with backend appliances.external_id.
static const char* EXT_LOAD_1 = "proto_led_a";
static const char* EXT_LOAD_2 = "proto_led_b";

// ===== Sensor & Device Variables =====
// Battery and system state
float batteryVoltage = 0.0;
float batteryPercentage = 0.0;
bool chargingState = false;
bool lowBattery = false;
bool criticalBattery = false;
float batterySOC = 100.0; // legacy, for compatibility
float batteryCurrent = 0.0;
// Lighting load state
bool lightState = false;
// ===============================
// Battery Reading Function
// ===============================
void readBattery()
{
  int rawADC = analogRead(BATTERY_PIN);
  float adcVoltage = ((float)rawADC / ADC_RESOLUTION) * ADC_REFERENCE;
  // Voltage divider formula
  batteryVoltage = adcVoltage * ((R1 + R2) / R2);
  // Battery percentage estimation (map 3.0V-4.2V to 0-100%)
  batteryPercentage = map(batteryVoltage * 100, 300, 420, 0, 100);
  if (batteryPercentage > 100)
    batteryPercentage = 100;
  if (batteryPercentage < 0)
    batteryPercentage = 0;
  // Battery state checks
  lowBattery = batteryPercentage < 25;
  criticalBattery = batteryPercentage < 10;
  // Charging state simulation
  chargingState = batteryVoltage > 4.0;
}

// ===============================
// Device Status Handler
// ===============================
void handleSystemStatus()
{
  // WiFi Indicator
  if (WiFi.status() == WL_CONNECTED)
  {
    digitalWrite(WIFI_LED, HIGH);
  }
  else
  {
    digitalWrite(WIFI_LED, millis() % 500 < 250);
  }
  // Charging Indicator
  digitalWrite(CHARGING_LED, chargingState);
  // Healthy System
  if (!lowBattery && WiFi.status() == WL_CONNECTED)
  {
    digitalWrite(STATUS_LED, HIGH);
  }
  else
  {
    digitalWrite(STATUS_LED, LOW);
  }
  // Warning/Fault LED
  if (lowBattery)
  {
    digitalWrite(FAULT_LED, millis() % 400 < 200);
  }
  else
  {
    digitalWrite(FAULT_LED, LOW);
  }
  // Buzzer Alerts
  if (criticalBattery)
  {
    tone(BUZZER_PIN, 1000);
  }
  else if (lowBattery)
  {
    if (millis() % 2000 < 300)
    {
      tone(BUZZER_PIN, 800);
    }
    else
    {
      noTone(BUZZER_PIN);
    }
  }
  else
  {
    noTone(BUZZER_PIN);
  }
}

// ===============================
// Lighting Load Control
// ===============================
void controlLighting(bool state)
{
  lightState = state;
  digitalWrite(LIGHT_LED, state);
}
float currentTemp = 0.0;
float currentHum = 0.0;
bool isSunny = false;
float pvPower = 0.0;
float pvVoltage = 0.0;
float pvCurrent = 0.0;
float loadPower = 15.0;

bool relay1State = true;
bool relay2State = true;
unsigned long lastSensorRead = 0;
unsigned long lastMqttPublish = 0;
unsigned long lastUsbPublish = 0;

// ===== Objects =====
DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
WebServer webServer(80);

// ===== Logging Helper =====
void log(const char* tag, const char* msg) {
  Serial.printf("[%lu] [%s] %s\n", millis(), tag, msg);
}

void logf(const char* tag, const char* fmt, ...) {
  char buffer[256];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buffer, sizeof(buffer), fmt, args);
  va_end(args);
  log(tag, buffer);
}

// ===== Wi-Fi Connection =====
void connectWiFi() {
  log("WIFI", "Connecting to WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    logf("WIFI", "Connected! IP: %s", WiFi.localIP().toString().c_str());
  } else {
    log("WIFI", "Failed to connect");
  }
}

// ===== MQTT Callbacks =====
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  char payloadStr[256];
  if (length >= sizeof(payloadStr)) length = sizeof(payloadStr) - 1;
  memcpy(payloadStr, payload, length);
  payloadStr[length] = '\0';
  
  logf("MQTT", "Received on %s: %s", topic, payloadStr);
  
  // Parse relay commands: microgrid/cmd/relay/{appliance_id}
  String topicStr = String(topic);
  String cmdPrefix = String(MQTT_PREFIX) + "/cmd/relay/";
  
  if (topicStr.startsWith(cmdPrefix)) {
    String applianceId = topicStr.substring(cmdPrefix.length());
    
    // Parse JSON payload
    StaticJsonDocument<128> doc;
    DeserializationError error = deserializeJson(doc, payloadStr);
    
    if (!error) {
      // Backend command payload uses "is_on" (preferred). Keep "state" fallback
      // for compatibility with older payloads.
      bool state = doc["is_on"] | doc["state"] | true;
      int relayPin = -1;
      
      if (applianceId == EXT_LOAD_1) relayPin = RELAY_LOAD_1;
      else if (applianceId == EXT_LOAD_2) relayPin = RELAY_LOAD_2;
      
      if (relayPin != -1) {
        digitalWrite(relayPin, state ? HIGH : LOW);
        logf("RELAY", "%s -> %s", applianceId.c_str(), state ? "ON" : "OFF");
        
        // Publish acknowledgment
        publishRelayAck(applianceId, state);
      }
    } else {
      logf("MQTT", "JSON parse error: %s", error.c_str());
    }
  }
}

void onMqttConnected() {
  log("MQTT", "Connected to broker");
  
  // Subscribe to relay commands
  String sub1 = String(MQTT_PREFIX) + "/cmd/relay/" + EXT_LOAD_1;
  String sub2 = String(MQTT_PREFIX) + "/cmd/relay/" + EXT_LOAD_2;
  
  mqttClient.subscribe(sub1.c_str());
  mqttClient.subscribe(sub2.c_str());
  
  logf("MQTT", "Subscribed to: %s, %s", sub1.c_str(), sub2.c_str());
}

void onMqttDisconnected() {
  log("MQTT", "Disconnected from broker");
}

// ===== MQTT Connection =====
void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED) {
    log("MQTT", "WiFi not connected, skipping MQTT");
    return;
  }
  
  if (mqttClient.connected()) return;
  
  logf("MQTT", "Connecting to %s:%d", MQTT_BROKER, MQTT_PORT_CFG);
  
  if (mqttClient.connect("ESP32-Gateway")) {
    onMqttConnected();
  } else {
    logf("MQTT", "Failed (code: %d)", mqttClient.state());
  }
}

// ===== Publish Helpers =====
void publishPv() {
  StaticJsonDocument<256> doc;
  doc["timestamp"] = getIsoTimestamp();
  doc["power_kw"] = pvPower / 1000.0;
  doc["voltage"] = pvVoltage;
  doc["current_a"] = pvCurrent;
  
  String topic = String(MQTT_PREFIX) + "/sensors/pv";
  String json;
  serializeJson(doc, json);
  
  if (mqttClient.publish(topic.c_str(), json.c_str())) {
    logf("PV", "Published: %.2f kW", pvPower / 1000.0);
  } else {
    log("PV", "Publish failed");
  }
}

void publishBattery() {
  StaticJsonDocument<256> batteryDoc;
  batteryDoc["voltage"] = batteryVoltage;
  batteryDoc["soc_percent"] = batteryPercentage;
  batteryDoc["charging"] = chargingState;
  batteryDoc["low_battery"] = lowBattery;
  String topic = String(MQTT_PREFIX) + "/sensors/battery";
  String json;
  serializeJson(batteryDoc, json);
  if (mqttClient.publish(topic.c_str(), json.c_str())) {
    logf("BATT", "Published: %.1f%%", batteryPercentage);
  } else {
    log("BATT", "Publish failed");
  }
}

void publishLoad(const char* applianceId, float powerKw, const char* state) {
  StaticJsonDocument<256> doc;
  doc["timestamp"] = getIsoTimestamp();
  doc["power_kw"] = powerKw;
  doc["state"] = state;
  
  String topic = String(MQTT_PREFIX) + "/sensors/load/" + applianceId;
  String json;
  serializeJson(doc, json);
  
  if (mqttClient.publish(topic.c_str(), json.c_str())) {
    logf("LOAD", "%s: %.2f kW (%s)", applianceId, powerKw, state);
  } else {
    log("LOAD", "Publish failed");
  }
}

void publishRelayAck(const String& applianceId, bool state) {
  StaticJsonDocument<128> doc;
  doc["state"] = state;
  doc["timestamp"] = getIsoTimestamp();
  
  String topic = String(MQTT_PREFIX) + "/ack/relay/" + applianceId;
  String json;
  serializeJson(doc, json);
  
  mqttClient.publish(topic.c_str(), json.c_str());
}

// ===== USB (Serial) Fallback Telemetry =====
void publishUsbTelemetry(const char* reason) {
  unsigned long now = millis();
  if (now - lastUsbPublish < 10000) return;  // every 10 seconds
  lastUsbPublish = now;

  StaticJsonDocument<384> doc;
  doc["timestamp"] = getIsoTimestamp();
  doc["source"] = "usb_fallback";
  doc["reason"] = reason;
  doc["wifi_connected"] = (WiFi.status() == WL_CONNECTED);
  doc["mqtt_connected"] = mqttClient.connected();
  doc["temp_c"] = currentTemp;
  doc["humidity_percent"] = currentHum;
  doc["battery_soc_percent"] = batterySOC;
  doc["pv_power_w"] = pvPower;
  doc["load_power_w"] = loadPower;
  doc["relay1"] = relay1State;
  doc["relay2"] = relay2State;

  String json;
  serializeJson(doc, json);
  Serial.print("[USB] ");
  Serial.println(json);
}

// ===== Sensor Reading =====
void readSensors() {
  unsigned long now = millis();
  
  // DHT reads every 2 seconds (DHT11 has 1-2s min interval)
  if (now - lastSensorRead < 2000) return;
  lastSensorRead = now;
  
  // Read DHT11
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  if (!isnan(temp)) currentTemp = temp;
  if (!isnan(hum)) currentHum = hum;
  
  // Read light sensor (active LOW = sunny)
  isSunny = (digitalRead(LIGHT_SENSOR) == LOW);
  
  // Simulate PV generation (replace with ADC reading for real implementation)
  pvPower = isSunny ? 150.0 : 0.0;  // Watts
  pvVoltage = isSunny ? 40.0 : 0.0;
  pvCurrent = isSunny ? (pvPower / pvVoltage) : 0.0;
  
  // Simulate battery dynamics
  float chargeRate = (pvPower - loadPower) * 0.001;  // kWh per interval
  batterySOC += chargeRate;
  batterySOC = constrain(batterySOC, 0.0, 100.0);
  
  // Battery current (simplified)
  batteryCurrent = (pvPower - loadPower) / batteryVoltage;
  
  // Battery status LEDs are now handled in handleSystemStatus()
  
  // Critical alert
  if (batterySOC < 20) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  }
  
  // Load LEDs
  digitalWrite(LED_LOAD_1, relay1State ? HIGH : LOW);
  digitalWrite(LED_LOAD_2, relay2State ? HIGH : LOW);
}

// ===== Publish Sensor Data =====
void publishSensorData() {
  unsigned long now = millis();
  if (now - lastMqttPublish < 10000) return;  // Publish every 10 seconds
  lastMqttPublish = now;
  
  if (WiFi.status() != WL_CONNECTED) {
    publishUsbTelemetry("wifi_disconnected");
    return;
  }
  if (!mqttClient.connected()) {
    publishUsbTelemetry("mqtt_disconnected");
    return;
  }
  
  publishPv();
  publishBattery();
  publishLoad(EXT_LOAD_1, (relay1State ? 15.0 : 0.0) / 1000.0, relay1State ? "on" : "off");
  publishLoad(EXT_LOAD_2, (relay2State ? 10.0 : 0.0) / 1000.0, relay2State ? "on" : "off");

  // Publish DHT11 temp/humidity
  StaticJsonDocument<128> dhtDoc;
  dhtDoc["timestamp"] = getIsoTimestamp();
  dhtDoc["temp_c"] = currentTemp;
  dhtDoc["humidity_percent"] = currentHum;
  String dhtTopic = String(MQTT_PREFIX) + "/sensors/temp_humidity";
  String dhtJson;
  serializeJson(dhtDoc, dhtJson);
  mqttClient.publish(dhtTopic.c_str(), dhtJson.c_str());

  // Publish light sensor
  StaticJsonDocument<96> lightDoc;
  lightDoc["timestamp"] = getIsoTimestamp();
  lightDoc["is_sunny"] = isSunny;
  String lightTopic = String(MQTT_PREFIX) + "/sensors/light";
  String lightJson;
  serializeJson(lightDoc, lightJson);
  mqttClient.publish(lightTopic.c_str(), lightJson.c_str());
}

// ===== ISO Timestamp =====
String getIsoTimestamp() {
  time_t now = time(nullptr);
  struct tm* timeinfo = gmtime(&now);
  char buffer[30];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", timeinfo);
  return String(buffer);
}

// ===== Web Dashboard =====
String getHtmlDashboard() {
  String html = R"rawliteral(
<!DOCTYPE html>
<html lang='en'>
<head>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Microgrid Gateway</title>
  <style>
    body {
      font-family: 'Inter', Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 24px 12px;
    }
    h1 {
      color: #38bdf8;
      text-align: center;
      font-size: 2.2rem;
      margin-bottom: 1.5rem;
      letter-spacing: -1px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 18px;
      margin-bottom: 2rem;
    }
    .card {
      background: #1e293b;
      padding: 1.2rem 1.1rem 1.1rem 1.1rem;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      min-height: 120px;
    }
    .label {
      color: #94a3b8;
      font-size: 0.98em;
      margin-bottom: 0.2em;
    }
    .value {
      font-size: 2.1em;
      font-weight: 700;
      color: #0ea5e9;
      margin: 0.2em 0 0.1em 0;
    }
    .status {
      padding: 5px 12px;
      border-radius: 999px;
      display: inline-block;
      font-size: 0.98em;
      margin-top: 0.5em;
      font-weight: 500;
      border: 1px solid #334155;
    }
    .status.ok { background: #22c55e; color: #fff; border-color: #22c55e; }
    .status.warn { background: #f59e0b; color: #fff; border-color: #f59e0b; }
    .status.error { background: #ef4444; color: #fff; border-color: #ef4444; }
    .donut {
      width: 80px; height: 80px; display: block; margin: 0.5em auto 0.2em auto;
    }
    .pvbar {
      width: 100%; height: 16px; background: #334155; border-radius: 8px; margin: 0.5em 0 0.2em 0; overflow: hidden;
    }
    .pvbar-inner {
      height: 100%; background: #22c55e; transition: width 0.5s; }
    .pvbar-label { font-size: 0.9em; color: #38bdf8; margin-top: 0.2em; }
    .relay-btn {
      padding: 10px 20px;
      margin: 5px 0 0 0;
      font-size: 1em;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      background: #0ea5e9;
      color: #fff;
      font-weight: 600;
      transition: background 0.2s;
    }
    .relay-btn:hover { background: #38bdf8; }
    @media (max-width: 600px) {
      .container { padding: 8px 2px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
  <script>
    function setDonut(val) {
      var c = document.getElementById('donut');
      if (!c) return;
      var pct = Math.max(0, Math.min(100, val));
      var r = 36, cLen = 2 * Math.PI * r;
      var offset = cLen * (1 - pct / 100);
      c.querySelector('.donut-ring').setAttribute('stroke-dasharray', cLen);
      c.querySelector('.donut-segment').setAttribute('stroke-dasharray', cLen);
      c.querySelector('.donut-segment').setAttribute('stroke-dashoffset', offset);
      document.getElementById('batt').textContent = pct.toFixed(1) + '%';
    }
    function updateUI(d) {
      setDonut(d.batt);
      document.getElementById('temp').textContent = d.temp.toFixed(1) + '°C';
      document.getElementById('pv').textContent = d.pv.toFixed(0) + 'W';
      document.getElementById('pvbar-inner').style.width = Math.min(100, d.pv / 200 * 100) + '%';
      document.getElementById('load').textContent = d.load.toFixed(0) + 'W';
      document.getElementById('sun').textContent = d.sun ? 'YES' : 'NO';
      document.getElementById('mqtt').textContent = d.mqtt ? 'Connected' : 'Disconnected';
      document.getElementById('mqtt').className = 'status ' + (d.mqtt ? 'ok' : 'error');
      document.getElementById('wifi').textContent = d.wifi ? 'Connected' : 'Disconnected';
      document.getElementById('wifi').className = 'status ' + (d.wifi ? 'ok' : 'error');
    }
    setInterval(function() {
      fetch('/api/status').then(r => r.json()).then(updateUI);
    }, 2000);
    function toggleRelay(relay) {
      fetch('/api/relay/' + relay, {method: 'POST'}).then(r => r.json()).then(d => {
        // Optionally show feedback
      });
    }
    window.onload = function() {
      fetch('/api/status').then(r => r.json()).then(updateUI);
    }
  </script>
</head>
<body>
  <div class='container'>
    <h1> Microgrid Gateway</h1>
    <div class='grid'>
      <div class='card' style='align-items:center;'>
        <div class='label'>Battery SOC</div>
        <svg id='donut' class='donut' viewBox='0 0 80 80'>
          <circle class='donut-ring' cx='40' cy='40' r='36' fill='transparent' stroke='#334155' stroke-width='8'/>
          <circle class='donut-segment' cx='40' cy='40' r='36' fill='transparent' stroke='#0ea5e9' stroke-width='8' stroke-linecap='round' stroke-dasharray='226' stroke-dashoffset='0'/>
          <text x='40' y='46' text-anchor='middle' font-size='1.2em' fill='#e2e8f0' font-family='Inter,Arial,sans-serif'>
            <tspan id='batt'>--</tspan>
          </text>
        </svg>
        <div id='mqtt' class='status error'>Disconnected</div>
        <div id='wifi' class='status error'>Disconnected</div>
      </div>
      <div class='card'>
        <div class='label'>Temperature</div>
        <div class='value' id='temp'>--</div>
      </div>
      <div class='card'>
        <div class='label'>PV Generation</div>
        <div class='value' id='pv'>--</div>
        <div class='pvbar'><div id='pvbar-inner' class='pvbar-inner' style='width:0%'></div></div>
        <div class='pvbar-label'>Solar Status: <span id='sun'>--</span></div>
      </div>
      <div class='card'>
        <div class='label'>Load Power</div>
        <div class='value' id='load'>--</div>
      </div>
      <div class='card'>
        <div class='label'>Relay 1 (proto_led_a)</div>
        <button class='relay-btn' onclick='toggleRelay("1")'>Toggle</button>
      </div>
      <div class='card'>
        <div class='label'>Relay 2 (proto_led_b)</div>
        <button class='relay-btn' onclick='toggleRelay("2")'>Toggle</button>
      </div>
    </div>
  </div>
</body>
</html>
  )rawliteral";
  return html;
}

// ===== Web Server Handlers =====
void handleRoot() {
  webServer.send(200, "text/html", getHtmlDashboard());
}

void handleStatus() {
  StaticJsonDocument<256> doc;
  doc["battery_voltage"] = batteryVoltage;
  doc["battery_percent"] = batteryPercentage;
  doc["charging"] = chargingState;
  doc["low_battery"] = lowBattery;
  doc["batt"] = batteryPercentage;
  doc["temp"] = currentTemp;
  doc["pv"] = pvPower;
  doc["load"] = loadPower;
  doc["sun"] = isSunny;
  doc["mqtt"] = mqttClient.connected();
  doc["wifi"] = WiFi.status() == WL_CONNECTED;
  String json;
  serializeJson(doc, json);
  webServer.send(200, "application/json", json.c_str());
}

void handleRelayToggle() {
  String relay = webServer.pathArg(0);
  
  if (relay == "1") {
    relay1State = !relay1State;
    digitalWrite(RELAY_LOAD_1, relay1State ? HIGH : LOW);
  } else if (relay == "2") {
    relay2State = !relay2State;
    digitalWrite(RELAY_LOAD_2, relay2State ? HIGH : LOW);
  }
  
  StaticJsonDocument<128> doc;
  doc["relay"] = relay;
  doc["state"] = (relay == "1") ? relay1State : relay2State;
  doc["message"] = "Relay toggled";
  
  String json;
  serializeJson(doc, json);
  webServer.send(200, "application/json", json.c_str());
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  log("BOOT", "Starting ESP32 Microgrid Gateway");
  
  // Pin setup
  pinMode(LIGHT_SENSOR, INPUT);
  pinMode(WIFI_LED, OUTPUT);
  pinMode(LIGHT_LED, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);
  pinMode(CHARGING_LED, OUTPUT);
  pinMode(FAULT_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(BATTERY_PIN, INPUT);
  pinMode(RELAY_LOAD_1, OUTPUT);
  pinMode(RELAY_LOAD_2, OUTPUT);

  // Initial states
  digitalWrite(WIFI_LED, LOW);
  digitalWrite(LIGHT_LED, LOW);
  digitalWrite(STATUS_LED, LOW);
  digitalWrite(CHARGING_LED, LOW);
  digitalWrite(FAULT_LED, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_LOAD_1, HIGH);
  digitalWrite(RELAY_LOAD_2, HIGH);
  
  // DHT setup
  dht.begin();
  delay(500);
  
  // WiFi
  connectWiFi();
  
  // Time sync (required for ISO timestamps)
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  log("TIME", "Syncing time from NTP...");
  time_t now = time(nullptr);
  while (now < 24 * 3600) {
    delay(500);
    Serial.print(".");
    now = time(nullptr);
  }
  Serial.println();
  logf("TIME", "Time synced: %s", ctime(&now));
  
  // MQTT setup
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT_CFG);
  mqttClient.setCallback(onMqttMessage);
  
  // Web server
  webServer.on("/", handleRoot);
  webServer.on("/api/status", handleStatus);
  webServer.on("/api/relay/1", handleRelayToggle);
  webServer.on("/api/relay/2", handleRelayToggle);
  webServer.begin();
  
  logf("BOOT", "Setup complete. Web: http://%s", WiFi.localIP().toString().c_str());
}

// ===== Main Loop =====
void loop() {
  // Handle web requests
  webServer.handleClient();

  // WiFi reconnection
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // MQTT connection & loop
  if (!mqttClient.connected()) {
    connectMqtt();
  }
  mqttClient.loop();

  // Read sensors
  readSensors();
  readBattery();
  handleSystemStatus();

  // Publish data
  publishSensorData();

  delay(100);  // Small delay to prevent watchdog reset
}
