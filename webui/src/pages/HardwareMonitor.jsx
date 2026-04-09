import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getMqttBadge } from '../utils/mqttStatus'
import { MqttStatusTooltip } from '../components/MqttStatusTooltip'
import { useAppSettings } from '../context/AppSettingsContext'
import SensorPipelineAlert from '../components/SensorPipelineAlert'

/** Default GPIO map — matches `firmware/esp32_doit_gateway` and `circuits/README.md` (DOIT silkscreen D# = GPIO#). */
const DEFAULT_ESP32_PINS = {
  dht: 4,
  light_do: 21,
  led_a: 25,
  led_b: 26,
  buzz_a: 27,
  buzz_b: 14,
}

const PIN_META = [
  { key: 'dht', label: 'DHT11', detail: 'Temperature & humidity (1-wire)' },
  { key: 'light_do', label: 'Light sensor', detail: 'Digital output (bright vs dark)' },
  { key: 'led_a', label: 'LED A', detail: 'Load proto_led_a' },
  { key: 'led_b', label: 'LED B', detail: 'Load proto_led_b' },
  { key: 'buzz_a', label: 'Buzzer A', detail: 'Load proto_buzz_a' },
  { key: 'buzz_b', label: 'Buzzer B', detail: 'Load proto_buzz_b' },
]

const EXT_ID_TO_PIN_KEY = {
  proto_led_a: 'led_a',
  proto_led_b: 'led_b',
  proto_buzz_a: 'buzz_a',
  proto_buzz_b: 'buzz_b',
}

function ageStyle(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return { color: '#64748b', label: '—' }
  if (seconds < 45) return { color: '#4ade80', label: `${Math.round(seconds)}s` }
  if (seconds < 300) return { color: '#fbbf24', label: `${Math.round(seconds / 60)}m` }
  return { color: '#f87171', label: `${Math.round(seconds / 60)}m` }
}

function secondsSince(iso) {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, (Date.now() - t) / 1000)
}

function formatUptimeMs(ms) {
  if (ms == null || Number.isNaN(ms)) return '—'
  const s = Math.floor(ms / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}

function rssiLabel(dbm) {
  if (dbm == null || Number.isNaN(dbm)) return { text: '—', color: '#64748b' }
  if (dbm >= -60) return { text: `${dbm} dBm (strong)`, color: '#4ade80' }
  if (dbm >= -75) return { text: `${dbm} dBm (ok)`, color: '#a3e635' }
  if (dbm >= -85) return { text: `${dbm} dBm (weak)`, color: '#fbbf24' }
  return { text: `${dbm} dBm (poor)`, color: '#f87171' }
}

function Section({ title, children, subtitle }) {
  return (
    <section style={{ marginBottom: '1.75rem' }}>
      <h2 style={{ fontSize: '1.05rem', marginBottom: subtitle ? 4 : '0.75rem', color: '#e2e8f0' }}>{title}</h2>
      {subtitle && (
        <p style={{ fontSize: '0.85rem', color: '#64748b', marginTop: 0, marginBottom: '0.75rem', maxWidth: 820 }}>
          {subtitle}
        </p>
      )}
      {children}
    </section>
  )
}

function tableShell(children) {
  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #334155' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>{children}</table>
    </div>
  )
}

function HealthCard({ label, value, sub, valueColor }) {
  return (
    <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
      <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: '1.15rem', color: valueColor || '#f1f5f9', fontWeight: 600 }}>{value}</div>
      {sub && <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 6 }}>{sub}</div>}
    </div>
  )
}

export default function HardwareMonitor({ api }) {
  const { settings } = useAppSettings()
  const showHover = settings.showHoverColorInterpretations
  const [mqttHealth, setMqttHealth] = useState(null)
  const [status, setStatus] = useState(null)
  const [appliances, setAppliances] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mqttHover, setMqttHover] = useState(false)
  const [showMqttDetails, setShowMqttDetails] = useState(false)

  const refresh = async () => {
    try {
      const [rM, rS, rA] = await Promise.all([
        fetch(`${api}/health/mqtt`),
        fetch(`${api}/status`),
        fetch(`${api}/appliances`),
      ])
      if (!rM.ok) throw new Error(rM.statusText)
      if (!rS.ok) throw new Error(rS.statusText)
      if (!rA.ok) throw new Error(rA.statusText)
      const m = await rM.json()
      const s = await rS.json()
      const a = await rA.json()
      setMqttHealth(m)
      setStatus(s)
      setAppliances(Array.isArray(a) ? a : [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    refresh()
    const id = setInterval(() => {
      if (!cancelled) refresh()
    }, 8000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [api])

  const mqtt = mqttHealth?.mqtt || {}
  const exampleTopics = mqttHealth?.example_topics || {}
  const simulated = status?.simulated
  const eg = status?.esp32_gateway
  const mergedPins = useMemo(() => ({ ...DEFAULT_ESP32_PINS, ...(eg?.pins || {}) }), [eg?.pins])

  const lastEsp32PacketIso = eg?.updated_at || status?.ambient_sensors_updated_at
  const packetAgeSec = secondsSince(lastEsp32PacketIso)
  const packetAge = ageStyle(packetAgeSec)

  const loadRows = useMemo(() => {
    const loads = status?.loads || []
    const lastLoadAt = (mqttHealth?.mqtt || {}).last_load_at || {}
    return appliances.map((app) => {
      const live = loads.find((l) => l.appliance_id === app.external_id)
      const lastIso = lastLoadAt[app.external_id]
      const sec = secondsSince(lastIso)
      const ag = ageStyle(sec)
      const pinKey = EXT_ID_TO_PIN_KEY[app.external_id]
      const gpio = pinKey != null ? mergedPins[pinKey] : null
      return {
        key: app.id,
        name: app.name,
        externalId: app.external_id,
        gpio,
        pinKey,
        state: live?.state ?? '—',
        powerKw: live != null ? live.power_kw : null,
        unexpected: live?.unexpected_override,
        ageLabel: sec == null ? 'Never' : ag.label,
        ageColor: sec == null ? '#64748b' : ag.color,
      }
    })
  }, [appliances, status, mqttHealth, mergedPins])

  const telemetryRows = useMemo(() => {
    const m = mqttHealth?.mqtt || {}
    const ex = mqttHealth?.example_topics || {}
    const rows = [
      { key: 'pv', label: 'PV', topic: ex.pv, iso: m.last_pv_at },
      { key: 'bat', label: 'Battery', topic: ex.battery, iso: m.last_battery_at },
      { key: 'env', label: 'Environment (sensors)', topic: ex.environment, iso: m.last_environment_at },
      { key: 'any', label: 'Any MQTT frame', topic: '(all subscribed)', iso: m.last_message_at },
      { key: 'ack', label: 'Relay ACK', topic: ex.relay_ack?.replace('{external_id}', '…'), iso: m.last_relay_ack_at },
    ]
    return rows.map((r) => {
      const sec = secondsSince(r.iso)
      const ag = ageStyle(sec)
      return {
        ...r,
        ageLabel: r.iso ? ag.label : 'Never',
        ageColor: r.iso ? ag.color : '#64748b',
        timeLocal: r.iso ? new Date(r.iso).toLocaleString() : '—',
      }
    })
  }, [mqttHealth])

  const mqttBadge = getMqttBadge(mqttHealth)
  const wifi = rssiLabel(eg?.wifi_rssi_dbm)

  if (loading && !status) return <p style={{ color: '#94a3b8' }}>Loading hardware status…</p>
  if (error) return <p style={{ color: '#f87171' }}>Error: {error}</p>

  const dhtOk = eg?.dht_ok
  const lightOk = eg?.light_ok
  const hasEsp32Telemetry = Boolean(eg && (eg.wifi_rssi_dbm != null || eg.uptime_ms != null || eg.pins))

  return (
    <div>
      <h1 style={{ marginBottom: 8 }}>Hardware monitor</h1>
      <p style={{ color: '#94a3b8', fontSize: '0.92rem', maxWidth: 860, marginBottom: '1.25rem' }}>
        <strong>ESP32</strong> gateway: on-board <strong>sensors</strong> (DHT11, digital light), <strong>GPIO</strong> map, and{' '}
        <strong>device health</strong> (Wi‑Fi, heap, uptime) as reported in the environment MQTT payload. Below that: PV/battery
        demo telemetry, actuators, and MQTT link checks.
      </p>

      <SensorPipelineAlert pipeline={mqttHealth?.sensor_pipeline} title="Why live sensor data may be missing" />

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
        <span
          style={{
            display: 'inline-block',
            padding: '0.35rem 0.75rem',
            borderRadius: 999,
            fontSize: '0.85rem',
            background: simulated ? '#1e3a5f' : '#14532d',
            color: simulated ? '#93c5fd' : '#bbf7d0',
            border: `1px solid ${simulated ? '#3b82f6' : '#22c55e'}`,
          }}
        >
          Backend: {simulated ? 'simulation' : 'hardware ingest'}
        </span>
        {mqttBadge && (
          <div
            style={{ position: 'relative', display: 'inline-block' }}
            onMouseEnter={() => showHover && setMqttHover(true)}
            onMouseLeave={() => showHover && setMqttHover(false)}
          >
            <p
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                background: '#1e293b',
                padding: '0.45rem 0.75rem',
                borderRadius: 999,
                border: `1px solid ${mqttBadge.color}`,
                margin: 0,
                cursor: showHover ? 'help' : 'default',
              }}
              title={showHover ? undefined : mqttBadge.details}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: mqttBadge.color,
                  display: 'inline-block',
                }}
              />
              <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>{mqttBadge.label}</span>
            </p>
            {showHover && mqttHover && <MqttStatusTooltip mqttBadge={mqttBadge} />}
          </div>
        )}
        <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
          Polls every 8s ·{' '}
          <button type="button" onClick={() => refresh()} style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', padding: 0 }}>
            Refresh now
          </button>
        </span>
      </div>

      {simulated && (
        <div
          style={{
            background: '#1e293b',
            border: '1px solid #475569',
            padding: '0.75rem 1rem',
            borderRadius: 8,
            marginBottom: '1.25rem',
            fontSize: '0.9rem',
            color: '#cbd5e1',
          }}
        >
          <strong>Simulation mode</strong> — the backend is not ingesting MQTT, so live ESP32 fields below stay empty. Flash the
          DOIT gateway firmware, run Mosquitto, set <code style={{ color: '#a5b4fc' }}>MICROGRID_USE_HARDWARE_SIMULATION=false</code>
          , and restart the API. The <strong>GPIO reference</strong> still shows the intended prototype wiring.
        </div>
      )}

      {/* —— ESP32 board —— */}
      <Section
        title="ESP32 gateway — sensors & GPIO"
        subtitle="Values come from `…/sensors/environment` (JSON from `esp32_doit_gateway.ino`). Pin numbers are reported by the firmware; the table matches the DOIT DevKit silkscreen (D# = GPIO#)."
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <HealthCard
            label="Wi‑Fi signal (ESP32)"
            value={eg?.wifi_rssi_dbm != null ? `${eg.wifi_rssi_dbm} dBm` : '—'}
            sub={wifi.text}
            valueColor={wifi.color}
          />
          <HealthCard
            label="Free heap"
            value={eg?.free_heap_bytes != null ? `${eg.free_heap_bytes.toLocaleString()} B` : '—'}
            sub="ESP.getFreeHeap()"
          />
          <HealthCard label="Uptime" value={formatUptimeMs(eg?.uptime_ms)} sub="Since last reboot" />
          <HealthCard
            label="Last sensor packet"
            value={lastEsp32PacketIso ? packetAge.label : '—'}
            sub={lastEsp32PacketIso ? new Date(lastEsp32PacketIso).toLocaleString() : 'No environment message yet'}
            valueColor={lastEsp32PacketIso ? packetAge.color : '#64748b'}
          />
        </div>

        {!hasEsp32Telemetry && !simulated && (
          <p style={{ color: '#fbbf24', fontSize: '0.88rem', marginBottom: '1rem' }}>
            Waiting for environment telemetry — check ESP32 Wi‑Fi, broker address, and topic prefix.
          </p>
        )}

        <h3 style={{ fontSize: '0.95rem', color: '#94a3b8', marginBottom: '0.5rem' }}>GPIO assignments</h3>
        {tableShell(
          <tbody>
            <tr style={{ background: '#0f172a' }}>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Function</th>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Silkscreen</th>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Notes</th>
            </tr>
            {PIN_META.map(({ key, label, detail }) => {
              const n = mergedPins[key]
              return (
                <tr key={key} style={{ borderTop: '1px solid #334155' }}>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>
                    <strong>{label}</strong>
                    <div style={{ fontSize: '0.78rem', color: '#64748b' }}>{detail}</div>
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'ui-monospace, monospace', color: '#7dd3fc' }}>
                    {n != null ? `D${n} (GPIO ${n})` : '—'}
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#94a3b8', fontSize: '0.82rem' }}>
                    {key === 'dht' && '3-pin module; 10 kΩ pull-up on data if needed'}
                    {key === 'light_do' && 'Digital comparator output (bright / dark)'}
                    {(key === 'led_a' || key === 'led_b') && '~220 Ω in series with LED'}
                    {(key === 'buzz_a' || key === 'buzz_b') && 'NPN + base resistor per circuits README'}
                  </td>
                </tr>
              )
            })}
          </tbody>,
        )}

        <h3 style={{ fontSize: '0.95rem', color: '#94a3b8', marginTop: '1.25rem', marginBottom: '0.5rem' }}>Sensor readings</h3>
        {tableShell(
          <tbody>
            <tr style={{ background: '#0f172a' }}>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Sensor</th>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Value</th>
              <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Health</th>
            </tr>
            <tr style={{ borderTop: '1px solid #334155' }}>
              <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>
                <strong>DHT11</strong>
                <div style={{ fontSize: '0.78rem', color: '#64748b' }}>GPIO {mergedPins.dht ?? '—'}</div>
              </td>
              <td style={{ padding: '0.55rem 0.75rem', color: '#cbd5e1' }}>
                {status?.ambient_temperature_c != null ? `${Number(status.ambient_temperature_c).toFixed(1)} °C` : '—'} ·{' '}
                {status?.ambient_humidity_percent != null ? `${Number(status.ambient_humidity_percent).toFixed(0)} % RH` : '—'}
              </td>
              <td style={{ padding: '0.55rem 0.75rem' }}>
                {dhtOk === true && <span style={{ color: '#4ade80' }}>OK</span>}
                {dhtOk === false && <span style={{ color: '#f87171' }}>Read failed</span>}
                {dhtOk == null && <span style={{ color: '#64748b' }}>—</span>}
              </td>
            </tr>
            <tr style={{ borderTop: '1px solid #334155' }}>
              <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>
                <strong>Light (DO)</strong>
                <div style={{ fontSize: '0.78rem', color: '#64748b' }}>GPIO {mergedPins.light_do ?? '—'}</div>
              </td>
              <td style={{ padding: '0.55rem 0.75rem', color: '#cbd5e1' }}>
                {lightOk === false && <span style={{ color: '#94a3b8' }}>Not connected</span>}
                {lightOk !== false && status?.ambient_light_digital === true && 'Bright'}
                {lightOk !== false && status?.ambient_light_digital === false && 'Dark'}
                {lightOk !== false && status?.ambient_light_digital == null && '—'}
              </td>
              <td style={{ padding: '0.55rem 0.75rem' }}>
                {lightOk === true && <span style={{ color: '#4ade80' }}>OK</span>}
                {lightOk === false && <span style={{ color: '#f87171' }}>Disabled</span>}
                {lightOk == null && <span style={{ color: '#64748b' }}>Digital</span>}
              </td>
            </tr>
          </tbody>,
        )}
      </Section>

      <Section
        title="Electrical telemetry (gateway demo)"
        subtitle="PV and battery streams are published by the stock sketch as demo waveforms until you connect real MPPT/BMS. Values mirror `/status`."
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}>
          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>PV</div>
            <div style={{ fontSize: '1.25rem', color: '#f1f5f9' }}>{status?.pv ? `${status.pv.power_kw.toFixed(2)} kW` : '—'}</div>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 4 }}>
              {status?.pv ? `${status.pv.voltage} V · ${status.pv.current_a?.toFixed?.(1) ?? '—'} A` : ''}
            </div>
          </div>
          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>Battery SOC</div>
            <div style={{ fontSize: '1.25rem', color: '#f1f5f9' }}>{status?.battery ? `${status.battery.soc_percent.toFixed(0)} %` : '—'}</div>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 4 }}>
              {status?.battery ? `${status.battery.voltage} V` : ''}
            </div>
          </div>
          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>Total load</div>
            <div style={{ fontSize: '1.25rem', color: '#f1f5f9' }}>
              {status?.total_load_kw != null ? `${Number(status.total_load_kw).toFixed(2)} kW` : '—'}
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="Actuators (loads)"
        subtitle="Each row is a registered appliance. GPIO is the ESP32 pin driving that load (from the environment JSON). Compare state to your schedule on the Schedule page."
      >
        {loadRows.length === 0 ? (
          <p style={{ color: '#64748b' }}>
            No appliances.{' '}
            <Link to="/appliances" style={{ color: '#38bdf8' }}>
              Register proto_led_a / proto_led_b / proto_buzz_a / proto_buzz_b
            </Link>{' '}
            to match the stock firmware.
          </p>
        ) : (
          tableShell(
            <tbody>
              <tr style={{ background: '#0f172a' }}>
                <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Appliance</th>
                <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>external_id</th>
                <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>GPIO</th>
                <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>State</th>
                <th style={{ textAlign: 'right', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>kW</th>
                <th style={{ textAlign: 'right', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Last load MQTT</th>
              </tr>
              {loadRows.map((r) => (
                <tr key={r.key} style={{ borderTop: '1px solid #334155' }}>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>{r.name}</td>
                  <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'ui-monospace, monospace', fontSize: '0.82rem', color: '#a5b4fc' }}>
                    {r.externalId}
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'ui-monospace, monospace', color: '#7dd3fc' }}>
                    {r.gpio != null ? `D${r.gpio}` : '—'}
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem' }}>
                    <span style={{ color: r.state === 'on' ? '#4ade80' : '#94a3b8' }}>{r.state}</span>
                    {r.unexpected && <span style={{ marginLeft: 8, color: '#f87171', fontSize: '0.75rem' }}>override?</span>}
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem', textAlign: 'right', color: '#cbd5e1' }}>
                    {r.powerKw != null ? r.powerKw.toFixed(3) : '—'}
                  </td>
                  <td style={{ padding: '0.55rem 0.75rem', textAlign: 'right', color: r.ageColor, fontWeight: 600 }}>{r.ageLabel}</td>
                </tr>
              ))}
            </tbody>,
          )
        )}
      </Section>

      <div style={{ marginBottom: '1.75rem' }}>
        <button
          type="button"
          onClick={() => setShowMqttDetails((v) => !v)}
          style={{
            background: '#1e293b',
            border: '1px solid #475569',
            color: '#e2e8f0',
            padding: '0.5rem 0.85rem',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: '0.9rem',
          }}
        >
          {showMqttDetails ? '▼ Hide' : '▶ Show'} broker, topics & stream ages
        </button>
        {showMqttDetails && (
          <div style={{ marginTop: '1rem' }}>
            <Section title="MQTT broker" subtitle={`Prefix ${mqttHealth?.topic_prefix ?? '—'} · ${mqtt.broker_host ?? '—'}:${mqtt.broker_port ?? '—'}`}>
              {tableShell(
                <tbody>
                  <tr style={{ background: '#0f172a' }}>
                    <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8', width: '28%' }}>Role</th>
                    <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Topic</th>
                  </tr>
                  {[
                    ['PV', exampleTopics.pv],
                    ['Battery', exampleTopics.battery],
                    ['Environment (sensors)', exampleTopics.environment],
                    ['Load', exampleTopics.load],
                    ['Relay command', exampleTopics.relay_command],
                    ['Relay ACK', exampleTopics.relay_ack],
                  ].map(([role, topic]) => (
                    <tr key={role} style={{ borderTop: '1px solid #334155' }}>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>{role}</td>
                      <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'ui-monospace, monospace', fontSize: '0.82rem', color: '#7dd3fc' }}>
                        {topic || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>,
              )}
            </Section>
            <Section title="Stream freshness" subtitle="Last time each class of message was seen by the backend broker client.">
              {tableShell(
                <tbody>
                  <tr style={{ background: '#0f172a' }}>
                    <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Stream</th>
                    <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Topic</th>
                    <th style={{ textAlign: 'left', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Last (local)</th>
                    <th style={{ textAlign: 'right', padding: '0.6rem 0.75rem', color: '#94a3b8' }}>Age</th>
                  </tr>
                  {telemetryRows.map((r) => (
                    <tr key={r.key} style={{ borderTop: '1px solid #334155' }}>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#e2e8f0' }}>{r.label}</td>
                      <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'ui-monospace, monospace', fontSize: '0.78rem', color: '#94a3b8' }}>
                        {r.topic || '—'}
                      </td>
                      <td style={{ padding: '0.55rem 0.75rem', color: '#cbd5e1', fontSize: '0.85rem' }}>{r.timeLocal}</td>
                      <td style={{ padding: '0.55rem 0.75rem', textAlign: 'right', color: r.ageColor, fontWeight: 600 }}>{r.ageLabel}</td>
                    </tr>
                  ))}
                </tbody>,
              )}
            </Section>
          </div>
        )}
      </div>

      <Section title="Maintenance & bring-up">
        <ul style={{ margin: 0, paddingLeft: '1.25rem', color: '#cbd5e1', lineHeight: 1.7, fontSize: '0.92rem' }}>
          <li>
            <strong>Serial</strong>: open the ESP32 serial monitor at <strong>115200</strong> baud for Wi‑Fi IP and DHT/light debug
            lines.
          </li>
          <li>
            <strong>DHT11</strong>: data on <code style={{ color: '#a5b4fc' }}>D4</code>; add a 10 kΩ pull-up to 3.3 V if the module has none.
          </li>
          <li>
            <strong>Light module</strong>: wire <code style={{ color: '#a5b4fc' }}>DO</code> to <code style={{ color: '#a5b4fc' }}>D21</code> (digital input).
          </li>
          <li>
            <strong>Broker</strong>: <code style={{ color: '#a5b4fc' }}>MICROGRID_MQTT_HOST</code> must match the network IP Mosquitto listens on.
          </li>
          <li>
            <strong>Appliances</strong>:{' '}
            <Link to="/appliances" style={{ color: '#38bdf8' }}>
              external_id
            </Link>{' '}
            must match topic segments and firmware <code style={{ color: '#a5b4fc' }}>#define</code>s.
          </li>
        </ul>
      </Section>
    </div>
  )
}
