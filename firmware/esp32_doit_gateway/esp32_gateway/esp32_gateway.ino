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
#define DHT_PIN         4
#define DHT_TYPE        DHT11
#define LIGHT_SENSOR    21
#define BUZZER_PIN      32
#define LED_BAT_HIGH    13
#define LED_BAT_MED     12
#define LED_BAT_LOW     14
#define LED_LOAD_1      27
#define LED_LOAD_2      26
#define RELAY_LOAD_1    25  // Control relay for Load 1
#define RELAY_LOAD_2    33  // Control relay for Load 2
// Keep these aligned with backend appliances.external_id.
static const char* EXT_LOAD_1 = "proto_led_a";
static const char* EXT_LOAD_2 = "proto_led_b";

// ===== Sensor & Device Variables =====
float batterySOC = 100.0;
float batteryVoltage = 48.0;
float batteryCurrent = 0.0;
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
  StaticJsonDocument<256> doc;
  doc["timestamp"] = getIsoTimestamp();
  doc["soc_percent"] = batterySOC;
  doc["voltage"] = batteryVoltage;
  doc["current_a"] = batteryCurrent;
  
  String topic = String(MQTT_PREFIX) + "/sensors/battery";
  String json;
  serializeJson(doc, json);
  
  if (mqttClient.publish(topic.c_str(), json.c_str())) {
    logf("BATT", "Published: %.1f%%", batterySOC);
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
  
  // Update LED indicators
  digitalWrite(LED_BAT_HIGH, batterySOC > 70 ? HIGH : LOW);
  digitalWrite(LED_BAT_MED, (batterySOC > 40 && batterySOC <= 70) ? HIGH : LOW);
  digitalWrite(LED_BAT_LOW, batterySOC < 40 ? HIGH : LOW);
  
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
<html>
<head>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Microgrid Gateway</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f0f0f0; margin: 0; padding: 20px; }
    .container { max-width: 900px; margin: auto; }
    h1 { color: #333; text-align: center; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
    .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .label { color: #666; font-size: 0.9em; }
    .value { font-size: 2em; font-weight: bold; color: #27ae60; margin: 10px 0; }
    .status { padding: 5px 10px; border-radius: 5px; display: inline-block; font-size: 0.9em; }
    .status.ok { background: #27ae60; color: white; }
    .status.warn { background: #f39c12; color: white; }
    .status.error { background: #e74c3c; color: white; }
    button { padding: 10px 20px; margin: 5px; font-size: 1em; border: none; border-radius: 5px; cursor: pointer; }
    .btn-on { background: #27ae60; color: white; }
    .btn-off { background: #e74c3c; color: white; }
  </style>
  <script>
    setInterval(function() {
      fetch('/api/status').then(r => r.json()).then(d => {
        document.getElementById('batt').textContent = d.batt.toFixed(1) + '%';
        document.getElementById('temp').textContent = d.temp.toFixed(1) + '°C';
        document.getElementById('pv').textContent = d.pv.toFixed(0) + 'W';
        document.getElementById('load').textContent = d.load.toFixed(0) + 'W';
        document.getElementById('sun').textContent = d.sun ? 'YES' : 'NO';
        document.getElementById('mqtt').textContent = d.mqtt ? 'Connected' : 'Disconnected';
        document.getElementById('mqtt').className = 'status ' + (d.mqtt ? 'ok' : 'error');
        document.getElementById('wifi').textContent = d.wifi ? 'Connected' : 'Disconnected';
        document.getElementById('wifi').className = 'status ' + (d.wifi ? 'ok' : 'error');
      });
    }, 2000);
    
    function toggleRelay(relay) {
      fetch('/api/relay/' + relay, {method: 'POST'}).then(r => r.json()).then(d => {
        console.log(d.message);
      });
    }
  </script>
</head>
<body>
  <div class='container'>
    <h1>🔋 Microgrid Gateway Monitor</h1>
    
    <div class='grid'>
      <div class='card'>
        <div class='label'>Battery SOC</div>
        <div class='value' id='batt'>--</div>
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
        <div class='label'>Solar Status</div>
        <div id='sun'>--</div>
      </div>
      
      <div class='card'>
        <div class='label'>Load Power</div>
        <div class='value' id='load'>--</div>
      </div>
      
      <div class='card'>
        <div class='label'>Relay 1 (proto_led_a)</div>
        <button class='btn-on' onclick='toggleRelay("1")'>Toggle</button>
      </div>
      
      <div class='card'>
        <div class='label'>Relay 2 (proto_led_b)</div>
        <button class='btn-on' onclick='toggleRelay("2")'>Toggle</button>
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
  doc["batt"] = batterySOC;
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
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_BAT_HIGH, OUTPUT);
  pinMode(LED_BAT_MED, OUTPUT);
  pinMode(LED_BAT_LOW, OUTPUT);
  pinMode(LED_LOAD_1, OUTPUT);
  pinMode(LED_LOAD_2, OUTPUT);
  pinMode(RELAY_LOAD_1, OUTPUT);
  pinMode(RELAY_LOAD_2, OUTPUT);
  
  // Initialize relays to ON
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
  
  // Publish data
  publishSensorData();
  
  delay(50);  // Small delay to prevent watchdog reset
}
