/** Legend for MQTT status colors (dashboard + nav). */
export const MQTT_COLOR_GUIDE = [
  { swatch: '#22c55e', name: 'Green', text: 'Healthy: broker connected and telemetry received.' },
  { swatch: '#f59e0b', name: 'Amber', text: 'Warning: broker disconnected, or connected but no telemetry yet.' },
  { swatch: '#ef4444', name: 'Red', text: 'Error: MQTT client missing or ingest loop not running.' },
  { swatch: '#64748b', name: 'Gray', text: 'Inactive: simulation mode — MQTT ingest is not used.' },
]

/**
 * @param {object | null} mqttHealth - JSON from GET /health/mqtt
 * @returns {object | null}
 */
export function getMqttBadge(mqttHealth) {
  if (!mqttHealth) return null
  const mode = mqttHealth.mode
  const mqtt = mqttHealth.mqtt || {}
  if (mode === 'simulation') {
    return {
      color: '#64748b',
      label: 'MQTT: inactive (simulation mode)',
      details: 'Backend is using built-in simulator; MQTT ingest is not active.',
      thisColorMeans: 'Gray means MQTT is not used — the backend is driving readings from the built-in simulator.',
    }
  }
  if (!mqtt.mqtt_available) {
    return {
      color: '#ef4444',
      label: 'MQTT: client unavailable',
      details: 'Install backend dependencies to enable MQTT ingest.',
      thisColorMeans: 'Red means the MQTT client library is missing — install `paho-mqtt` in the backend environment.',
    }
  }
  if (!mqtt.running) {
    return {
      color: '#ef4444',
      label: 'MQTT: ingest not running',
      details: 'Hardware ingest mode is enabled but MQTT loop is not running.',
      thisColorMeans: 'Red means the ingest loop did not start — check backend logs and hardware mode configuration.',
    }
  }
  if (!mqtt.connected) {
    return {
      color: '#f59e0b',
      label: 'MQTT: broker disconnected',
      details: `Cannot connect to broker at ${mqtt.broker_host}:${mqtt.broker_port}.`,
      thisColorMeans: 'Amber means the broker is unreachable — start Mosquitto or fix host/port/firewall.',
    }
  }
  if (!mqtt.last_message_at) {
    return {
      color: '#f59e0b',
      label: 'MQTT: connected, no telemetry yet',
      details: 'Broker connected; waiting for sensor messages from Pi/emulator.',
      thisColorMeans: 'Amber means the broker accepted the connection but no sensor messages have arrived yet.',
    }
  }
  return {
    color: '#22c55e',
    label: 'MQTT: healthy',
    details: `Last message at ${new Date(mqtt.last_message_at).toLocaleTimeString()}.`,
    thisColorMeans: 'Green means the broker is connected and telemetry has been received.',
  }
}
