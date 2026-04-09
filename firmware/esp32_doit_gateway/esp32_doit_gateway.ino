/**
 * ESP32 DOIT DevKit V1 — MQTT gateway for Smart Microgrid Manager.
 *
 * Wiring (matches circuits/README): DHT11 on GPIO4, light DO on GPIO21,
 * LEDs on 25/26, buzzer drivers on 27/14. No physical switches.
 *
 * Arduino libraries: PubSubClient, DHT sensor library (Adafruit DHT Unified optional — use classic DHT.h).
 *
 * Create four appliances in the web UI with these external_id values (or change the #defines below):
 *   proto_led_a, proto_led_b, proto_buzz_a, proto_buzz_b
 *
 * Run backend with MICROGRID_USE_HARDWARE_SIMULATION=false and Mosquitto on MQTT_HOST.
 */

#include <WiFi.h>
#include <math.h>
#include <string.h>

#define MQTT_MAX_PACKET_SIZE 512
#include <PubSubClient.h>
#include <DHT.h>

#include "secrets.h"

#ifndef MQTT_TOPIC_PREFIX
#define MQTT_TOPIC_PREFIX "microgrid"
#endif

#ifndef LIGHT_SENSOR_ENABLED
#define LIGHT_SENSOR_ENABLED 1
#endif

// --- Pins (DOIT silkscreen D# = GPIO#) ---
static const int PIN_DHT = 4;
static const int PIN_LIGHT_DO = 21;
static const int PIN_LED_A = 25;
static const int PIN_LED_B = 26;
static const int PIN_BUZZ_A = 27;
static const int PIN_BUZZ_B = 14;

// --- Appliance external_ids (must exist in DB; see firmware/README.md) ---
#define EXT_LED_A "proto_led_a"
#define EXT_LED_B "proto_led_b"
#define EXT_BUZZ_A "proto_buzz_a"
#define EXT_BUZZ_B "proto_buzz_b"

// Approximate draw when "on" (kW) for telemetry
static const float KW_LED_A = 0.005f;
static const float KW_LED_B = 0.005f;
static const float KW_BUZZ_A = 0.012f;
static const float KW_BUZZ_B = 0.012f;

static const unsigned long TELEMETRY_MS = 5000;

DHT dht(PIN_DHT, DHT11);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

char topicBuf[96];
char jsonBuf[512];

struct LoadPin {
  const char* ext_id;
  int pin;
  float kw_on;
  bool on;
};

LoadPin loads[] = {
    {EXT_LED_A, PIN_LED_A, KW_LED_A, false},
    {EXT_LED_B, PIN_LED_B, KW_LED_B, false},
    {EXT_BUZZ_A, PIN_BUZZ_A, KW_BUZZ_A, false},
    {EXT_BUZZ_B, PIN_BUZZ_B, KW_BUZZ_B, false},
};

static const int NUM_LOADS = sizeof(loads) / sizeof(loads[0]);

void buildPrefix(char* out, size_t n) {
  snprintf(out, n, "%s", MQTT_TOPIC_PREFIX);
}

void publishRelayAck(const char* ext_id, bool is_on);

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (length >= sizeof(jsonBuf)) {
    length = sizeof(jsonBuf) - 1;
  }
  memcpy(jsonBuf, payload, length);
  jsonBuf[length] = '\0';

  // Expect topic: <prefix>/cmd/relay/<external_id>
  char prefix[48];
  buildPrefix(prefix, sizeof(prefix));
  char relayBase[80];
  snprintf(relayBase, sizeof(relayBase), "%s/cmd/relay/", prefix);
  if (strncmp(topic, relayBase, strlen(relayBase)) != 0) {
    return;
  }
  const char* ext = topic + strlen(relayBase);
  bool is_on =
      (strstr(jsonBuf, "\"is_on\":true") != nullptr) || (strstr(jsonBuf, "\"is_on\": true") != nullptr);

  for (int i = 0; i < NUM_LOADS; i++) {
    if (strcmp(ext, loads[i].ext_id) == 0) {
      loads[i].on = is_on;
      digitalWrite(loads[i].pin, is_on ? HIGH : LOW);
      publishRelayAck(ext, is_on);
      return;
    }
  }
}

void publishRelayAck(const char* ext_id, bool is_on) {
  buildPrefix(topicBuf, sizeof(topicBuf));
  char ackTopic[120];
  snprintf(ackTopic, sizeof(ackTopic), "%s/ack/relay/%s", topicBuf, ext_id);
  snprintf(
      jsonBuf,
      sizeof(jsonBuf),
      "{\"appliance_id\":\"%s\",\"applied_state\":\"%s\",\"timestamp\":\"\"}",
      ext_id,
      is_on ? "on" : "off");
  mqtt.publish(ackTopic, jsonBuf, false);
}

void publishLoad(const LoadPin& L) {
  snprintf(topicBuf, sizeof(topicBuf), "%s/sensors/load/%s", MQTT_TOPIC_PREFIX, L.ext_id);
  float p = L.on ? L.kw_on : 0.0f;
  snprintf(
      jsonBuf,
      sizeof(jsonBuf),
      "{\"appliance_id\":\"%s\",\"power_kw\":%.5f,\"state\":\"%s\",\"timestamp\":\"\"}",
      L.ext_id,
      p,
      L.on ? "on" : "off");
  mqtt.publish(topicBuf, jsonBuf, false);
}

void publishEnvironment(float t, float h, int light) {
  char envTopic[80];
  snprintf(envTopic, sizeof(envTopic), "%s/sensors/environment", MQTT_TOPIC_PREFIX);
  bool haveTh = !isnan(h) && !isnan(t) && t > -40.0f && t < 85.0f && h >= 0.0f && h <= 100.0f;
#if LIGHT_SENSOR_ENABLED
  const bool haveLight = true;
#else
  const bool haveLight = false;
#endif
  int rssi = WiFi.RSSI();
  uint32_t heap = ESP.getFreeHeap();
  uint32_t up = millis();
  // Pins match setupPins() / circuits README — UI shows this as the live board map.
  if (haveTh && haveLight) {
    snprintf(
        jsonBuf,
        sizeof(jsonBuf),
        "{\"temperature_c\":%.2f,\"humidity_percent\":%.2f,\"light_digital\":%d,"
        "\"dht_ok\":true,\"light_ok\":true,\"wifi_rssi_dbm\":%d,\"free_heap_bytes\":%u,\"uptime_ms\":%u,"
        "\"pins\":{\"dht\":%d,\"light_do\":%d,\"led_a\":%d,\"led_b\":%d,\"buzz_a\":%d,\"buzz_b\":%d},\"timestamp\":\"\"}",
        t,
        h,
        light ? 1 : 0,
        rssi,
        heap,
        up,
        PIN_DHT,
        PIN_LIGHT_DO,
        PIN_LED_A,
        PIN_LED_B,
        PIN_BUZZ_A,
        PIN_BUZZ_B);
  } else if (haveTh && !haveLight) {
    snprintf(
        jsonBuf,
        sizeof(jsonBuf),
        "{\"temperature_c\":%.2f,\"humidity_percent\":%.2f,"
        "\"dht_ok\":true,\"light_ok\":false,\"wifi_rssi_dbm\":%d,\"free_heap_bytes\":%u,\"uptime_ms\":%u,"
        "\"pins\":{\"dht\":%d,\"light_do\":%d,\"led_a\":%d,\"led_b\":%d,\"buzz_a\":%d,\"buzz_b\":%d},\"timestamp\":\"\"}",
        t,
        h,
        rssi,
        heap,
        up,
        PIN_DHT,
        PIN_LIGHT_DO,
        PIN_LED_A,
        PIN_LED_B,
        PIN_BUZZ_A,
        PIN_BUZZ_B);
  } else if (!haveTh && haveLight) {
    snprintf(
        jsonBuf,
        sizeof(jsonBuf),
        "{\"light_digital\":%d,\"dht_ok\":false,\"light_ok\":true,\"wifi_rssi_dbm\":%d,\"free_heap_bytes\":%u,\"uptime_ms\":%u,"
        "\"pins\":{\"dht\":%d,\"light_do\":%d,\"led_a\":%d,\"led_b\":%d,\"buzz_a\":%d,\"buzz_b\":%d},\"timestamp\":\"\"}",
        light ? 1 : 0,
        rssi,
        heap,
        up,
        PIN_DHT,
        PIN_LIGHT_DO,
        PIN_LED_A,
        PIN_LED_B,
        PIN_BUZZ_A,
        PIN_BUZZ_B);
  } else {
    snprintf(
        jsonBuf,
        sizeof(jsonBuf),
        "{\"dht_ok\":false,\"light_ok\":false,\"wifi_rssi_dbm\":%d,\"free_heap_bytes\":%u,\"uptime_ms\":%u,"
        "\"pins\":{\"dht\":%d,\"light_do\":%d,\"led_a\":%d,\"led_b\":%d,\"buzz_a\":%d,\"buzz_b\":%d},\"timestamp\":\"\"}",
        rssi,
        heap,
        up,
        PIN_DHT,
        PIN_LIGHT_DO,
        PIN_LED_A,
        PIN_LED_B,
        PIN_BUZZ_A,
        PIN_BUZZ_B);
  }
  mqtt.publish(envTopic, jsonBuf, false);
}

void publishPvBattery() {
  buildPrefix(topicBuf, sizeof(topicBuf));
  // Simple demo wave so dashboard charts move (replace with real MPPT/charger later).
  float t = millis() / 15000.0f;
  float pv_kw = 0.25f + 0.15f * sinf(t);
  float soc = 72.0f + 8.0f * sinf(t * 0.7f);

  snprintf(jsonBuf, sizeof(jsonBuf),
           "{\"power_kw\":%.4f,\"voltage\":48.0,\"current_a\":%.3f,\"timestamp\":\"\"}",
           pv_kw, pv_kw * 1000.0f / 48.0f);
  char pvTopic[80];
  snprintf(pvTopic, sizeof(pvTopic), "%s/sensors/pv", MQTT_TOPIC_PREFIX);
  mqtt.publish(pvTopic, jsonBuf, false);

  snprintf(jsonBuf, sizeof(jsonBuf),
           "{\"soc_percent\":%.2f,\"voltage\":12.8,\"current_a\":%.3f,\"timestamp\":\"\"}",
           soc, (soc - 70.0f) * 0.02f);
  char batTopic[80];
  snprintf(batTopic, sizeof(batTopic), "%s/sensors/battery", MQTT_TOPIC_PREFIX);
  mqtt.publish(batTopic, jsonBuf, false);
}

void setupPins() {
  pinMode(PIN_LIGHT_DO, INPUT);
  pinMode(PIN_LED_A, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_BUZZ_A, OUTPUT);
  pinMode(PIN_BUZZ_B, OUTPUT);
  digitalWrite(PIN_LED_A, LOW);
  digitalWrite(PIN_LED_B, LOW);
  digitalWrite(PIN_BUZZ_A, LOW);
  digitalWrite(PIN_BUZZ_B, LOW);
}

void setupWifiMqtt() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
}

bool mqttReconnect() {
  if (mqtt.connected()) {
    return true;
  }
  Serial.print("MQTT...");
  char clientId[40];
  uint8_t mac[6];
  WiFi.macAddress(mac);
  snprintf(
      clientId,
      sizeof(clientId),
      "esp32-mg-%02x%02x%02x%02x%02x%02x",
      mac[0],
      mac[1],
      mac[2],
      mac[3],
      mac[4],
      mac[5]);
  if (!mqtt.connect(clientId)) {
    Serial.println(" fail");
    return false;
  }
  Serial.println(" ok");

  char relayBase[80];
  snprintf(relayBase, sizeof(relayBase), "%s/cmd/relay/", MQTT_TOPIC_PREFIX);
  for (int i = 0; i < NUM_LOADS; i++) {
    snprintf(topicBuf, sizeof(topicBuf), "%s%s", relayBase, loads[i].ext_id);
    mqtt.subscribe(topicBuf, 1);
    Serial.print("Sub ");
    Serial.println(topicBuf);
  }
  return true;
}

unsigned long lastTelem = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  setupPins();
  dht.begin();
  setupWifiMqtt();
}

void loop() {
  if (!mqttReconnect()) {
    delay(2000);
    return;
  }
  mqtt.loop();

  if (millis() - lastTelem >= TELEMETRY_MS) {
    lastTelem = millis();
    float h = dht.readHumidity();
    float t = dht.readTemperature();
#if LIGHT_SENSOR_ENABLED
    int light = digitalRead(PIN_LIGHT_DO);
#else
    int light = 0;
#endif
    publishPvBattery();
    for (int i = 0; i < NUM_LOADS; i++) {
      publishLoad(loads[i]);
    }
    publishEnvironment(t, h, light);
#if LIGHT_SENSOR_ENABLED
    Serial.printf("DHT T=%.1f H=%.1f  lightDO=%d\n", t, h, light);
#else
    Serial.printf("DHT T=%.1f H=%.1f  (light sensor disabled)\n", t, h);
#endif
  }
}
