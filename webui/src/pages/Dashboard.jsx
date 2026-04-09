import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { MultiLineChart, DonutChart, HorizontalBarChart } from '../components/Charts'
import { MqttStatusTooltip } from '../components/MqttStatusTooltip'
import { useAppSettings } from '../context/AppSettingsContext'
import { getMqttBadge } from '../utils/mqttStatus'
import SensorPipelineAlert from '../components/SensorPipelineAlert'

function downsample(points, max = 120) {
  if (!points?.length || points.length <= max) return points
  const step = Math.ceil(points.length / max)
  const out = []
  for (let i = 0; i < points.length; i += step) out.push(points[i])
  if (out[out.length - 1] !== points[points.length - 1]) out.push(points[points.length - 1])
  return out
}

export default function Dashboard({ api }) {
  const { settings } = useAppSettings()
  const showColorHover = settings.showHoverColorInterpretations
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState(null)
  const [mqttHealth, setMqttHealth] = useState(null)
  const [mqttBadgeHover, setMqttBadgeHover] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchHistory = () => {
    fetch(`${api}/status/history?hours=24`)
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => setHistory({ points: [], ambient_points: [] }))
  }

  useEffect(() => {
    let cancelled = false
    async function fetchStatus() {
      try {
        const r = await fetch(`${api}/status`)
        if (!r.ok) throw new Error(r.statusText)
        const data = await r.json()
        if (!cancelled) setStatus(data)
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    async function fetchMqttHealth() {
      try {
        const r = await fetch(`${api}/health/mqtt`)
        if (!r.ok) throw new Error(r.statusText)
        const data = await r.json()
        if (!cancelled) setMqttHealth(data)
      } catch {
        if (!cancelled) setMqttHealth(null)
      }
    }
    fetchStatus()
    fetchHistory()
    fetchMqttHealth()
    const live = setInterval(() => {
      fetchStatus()
      fetchMqttHealth()
    }, 5000)
    const historyEvery = setInterval(() => {
      fetchHistory()
    }, 30000)
    return () => {
      cancelled = true
      clearInterval(live)
      clearInterval(historyEvery)
    }
  }, [api])

  const chartData = useMemo(() => {
    const pts = downsample(history?.points || [], 100)
    if (!pts.length) return null
    return {
      soc: pts.map((p) => p.soc_percent ?? 0),
      pv: pts.map((p) => p.power_kw ?? 0),
      load: pts.map((p) => p.total_load_kw ?? 0),
      exportable: pts.map((p) => p.available_export_kw ?? 0),
      labels: pts.map((p) => (p.timestamp ? new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')),
    }
  }, [history])

  const ambientChartData = useMemo(() => {
    const pts = downsample(history?.ambient_points || [], 100)
    if (!pts.length) return null
    return {
      temp: pts.map((p) => (p.temperature_c != null ? Number(p.temperature_c) : 0)),
      hum: pts.map((p) => (p.humidity_percent != null ? Number(p.humidity_percent) : 0)),
      light: pts.map((p) => (p.light_digital === true ? 100 : 0)),
      labels: pts.map((p) => (p.timestamp ? new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')),
    }
  }, [history])

  if (loading) return <p>Loading status…</p>
  if (error) return <p style={{ color: '#f87171' }}>Error: {error}</p>
  if (!status) return null

  const {
    pv,
    battery,
    loads,
    total_load_kw,
    available_export_kw,
    battery_is_charging,
    battery_status_label,
    battery_status_level,
    manual_override_detected,
    manual_override_messages,
    simulated,
    ambient_temperature_c,
    ambient_humidity_percent,
    ambient_light_digital,
    ambient_sensors_updated_at,
  } = status
  const ts = status.timestamp ? new Date(status.timestamp).toLocaleString() : '–'
  const loadBars = loads
    .map((l) => {
      const on = l.state === 'on'
      const color = l.unexpected_override ? '#ef4444' : on ? '#22c55e' : '#64748b'
      return {
        label: l.name,
        value: l.power_kw,
        color,
        hoverTitle: showColorHover
          ? `${l.name}: ${l.power_kw.toFixed(3)} kW. Bar fill — ${
              l.unexpected_override
                ? 'red: unexpected manual override detected (load appears ON outside the planned schedule).'
                : 
              on
                ? 'green: appliance ON (drawing power).'
                : 'slate gray: appliance OFF or shedded (no intentional draw).'
            }`
          : undefined,
      }
    })
    .sort((a, b) => b.value - a.value)
  const mqttBadge = getMqttBadge(mqttHealth)
  const batteryStatusColor =
    battery_status_level === 'success' ? '#22c55e' : battery_status_level === 'warning' ? '#f59e0b' : '#94a3b8'

  const hasAmbientReadings =
    ambient_temperature_c != null || ambient_humidity_percent != null || ambient_light_digital != null
  const ambientValueLine = hasAmbientReadings
    ? [
        ambient_temperature_c != null ? `${Number(ambient_temperature_c).toFixed(1)} °C` : null,
        ambient_humidity_percent != null ? `${Number(ambient_humidity_percent).toFixed(0)} % RH` : null,
        ambient_light_digital != null ? (ambient_light_digital ? 'Light: bright' : 'Light: dark') : null,
      ]
        .filter(Boolean)
        .join(' · ') || '—'
    : simulated
      ? '—'
      : 'Waiting for readings…'
  const ambientSub = hasAmbientReadings ? (
    ambient_sensors_updated_at ? (
      `Updated ${new Date(ambient_sensors_updated_at).toLocaleString()}`
    ) : (
      'From MQTT …/sensors/environment'
    )
  ) : simulated ? (
    'Not connected in simulation mode.'
  ) : (
    <span style={{ color: '#64748b' }}>
      <Link to="/hardware" style={{ color: '#38bdf8' }}>
        Hardware
      </Link>{' '}
      has GPIO + MQTT timing. Topic <code style={{ fontSize: '0.75rem' }}>microgrid/sensors/environment</code>.
    </span>
  )

  return (
    <div>
      <h1>Dashboard</h1>
      <SensorPipelineAlert pipeline={mqttHealth?.sensor_pipeline} />
      {mqttBadge && (
        <div
          style={{ position: 'relative', display: 'inline-block', marginBottom: '0.75rem' }}
          onMouseEnter={() => showColorHover && setMqttBadgeHover(true)}
          onMouseLeave={() => setMqttBadgeHover(false)}
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
              cursor: showColorHover ? 'help' : 'default',
            }}
            title={showColorHover ? undefined : mqttBadge.details}
          >
            <span
              title={showColorHover ? `Status dot color: ${mqttBadge.thisColorMeans}` : undefined}
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: mqttBadge.color,
                display: 'inline-block',
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>{mqttBadge.label}</span>
          </p>
          {showColorHover && mqttBadgeHover && <MqttStatusTooltip mqttBadge={mqttBadge} />}
        </div>
      )}
      {simulated && (
        <p style={{ background: '#1e293b', padding: '0.5rem 0.75rem', borderRadius: 6 }}>
          Running in <strong>simulation mode</strong>. Background loop updates readings; charts use last 24h history.
        </p>
      )}
      {manual_override_detected && (
        <div style={{ background: '#3f0d12', border: '1px solid #ef4444', padding: '0.7rem 0.85rem', borderRadius: 8, marginTop: '0.75rem' }}>
          <div style={{ color: '#fecaca', fontWeight: 700, marginBottom: 4 }}>Unplanned appliance use detected</div>
          <div style={{ color: '#fecaca', fontSize: '0.9rem' }}>
            {manual_override_messages?.length ? manual_override_messages.join(' ') : 'A load appears to be running outside the planned schedule.'}
          </div>
        </div>
      )}
      <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>Last updated: {ts}</p>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginTop: '1.5rem', alignItems: 'start' }}>
        <Card title="Ambient (ESP32) — live" value={ambientValueLine} sub={ambientSub} />
        <Card title="PV generation" value={`${pv.power_kw.toFixed(2)} kW`} sub={`${pv.voltage} V, ${pv.current_a.toFixed(1)} A`} />
        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, display: 'flex', justifyContent: 'center' }}>
          <DonutChart value={battery.soc_percent} label="Battery SOC" color="#0ea5e9" />
        </div>
        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, border: `1px solid ${batteryStatusColor}` }}>
          <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Battery status</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: 6, color: batteryStatusColor }}>
            {battery_is_charging ? 'Charging' : 'Not charging'}
          </div>
          <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: 6 }}>{battery_status_label}</div>
        </div>
        <Card title="Total load" value={`${total_load_kw.toFixed(2)} kW`} sub={`${loads.length} circuits`} />
        <Card
          title="Available to export"
          value={`${(available_export_kw ?? 0).toFixed(2)} kW`}
          sub="Only counts when the battery is full and PV still exceeds the applied IEBA load"
        />
      </section>

      {chartData && (
        <section style={{ marginTop: '2rem', background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
          <h2 style={{ fontSize: '1rem', marginBottom: 4 }}>Last 24 hours – trends</h2>
          <MultiLineChart
            title="Battery SOC (%)"
            series={[{ name: 'SOC %', color: '#0ea5e9', values: chartData.soc }]}
            labels={chartData.labels}
            height={160}
          />
          <MultiLineChart
            title="PV (kW) vs total load (kW) vs exportable surplus (kW)"
            series={[
              { name: 'PV kW', color: '#22c55e', values: chartData.pv },
              { name: 'Load kW', color: '#f59e0b', values: chartData.load },
              { name: 'Exportable kW', color: '#a855f7', values: chartData.exportable },
            ]}
            labels={chartData.labels}
            height={180}
          />
        </section>
      )}

      {ambientChartData && (
        <section style={{ marginTop: '1.5rem', background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
          <h2 style={{ fontSize: '1rem', marginBottom: 4 }}>Ambient (ESP32) — last 24h</h2>
          <p style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: 8 }}>
            Temperature (°C), humidity (%), light sensor (0 = dark, 100 = bright on this chart).
          </p>
          <MultiLineChart
            title="DHT11 + digital light"
            series={[
              { name: 'Temp °C', color: '#f97316', values: ambientChartData.temp },
              { name: 'RH %', color: '#38bdf8', values: ambientChartData.hum },
              { name: 'Light', color: '#eab308', values: ambientChartData.light },
            ]}
            labels={ambientChartData.labels}
            height={180}
          />
        </section>
      )}

      {history?.points?.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem' }}>SOC snapshot (bars)</h2>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 72, marginTop: 8 }}>
            {history.points.slice(-72).map((p, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  height: `${p.soc_percent ?? 0}%`,
                  minHeight: 2,
                  background: '#0ea5e9',
                  borderRadius: 2,
                  cursor: showColorHover ? 'help' : 'default',
                }}
                title={
                  p.timestamp
                    ? showColorHover
                      ? `${new Date(p.timestamp).toLocaleString()} — SOC ${p.soc_percent ?? 0}%. Cyan bar height = battery state of charge (history); color is the chart series, not MQTT status.`
                      : new Date(p.timestamp).toLocaleString() + ' – ' + (p.soc_percent ?? 0) + '%'
                    : ''
                }
              />
            ))}
          </div>
        </section>
      )}

      {loadBars.length > 0 && (
        <section style={{ marginTop: '2rem', background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
          <HorizontalBarChart items={loadBars} title="Current load by appliance (kW)" unit=" kW" />
        </section>
      )}

      <h2 style={{ marginTop: '2rem' }}>Loads</h2>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #334155' }}>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>Appliance</th>
            <th style={{ textAlign: 'right', padding: '0.5rem' }}>Power (kW)</th>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>State</th>
          </tr>
        </thead>
        <tbody>
          {loads.map((l) => (
            <tr key={l.appliance_id} style={{ borderBottom: '1px solid #334155' }}>
              <td style={{ padding: '0.5rem' }}>{l.name}</td>
              <td style={{ textAlign: 'right', padding: '0.5rem' }}>{l.power_kw.toFixed(3)}</td>
              <td style={{ padding: '0.5rem', color: l.unexpected_override ? '#f87171' : undefined }}>
                {l.state}{l.unexpected_override ? ' (unexpected override)' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Card({ title, value, sub }) {
  return (
    <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
      <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>{title}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 600, marginTop: 4 }}>{value}</div>
      {sub != null && sub !== '' && <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

