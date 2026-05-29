import { useEffect, useMemo, useState } from 'react'
import { getMqttBadge } from '../utils/mqttStatus'
import { apiFetch } from '../utils/api'

function FreshnessBadge({ freshness }) {
  const palette =
    freshness === 'fresh'
      ? { bg: 'rgba(34, 197, 94, 0.15)', border: '#166534', text: '#bbf7d0' }
      : freshness === 'stale'
        ? { bg: 'rgba(245, 158, 11, 0.15)', border: '#92400e', text: '#fde68a' }
        : { bg: 'rgba(100, 116, 139, 0.15)', border: '#475569', text: '#cbd5e1' }
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '0.2rem 0.45rem',
        borderRadius: 999,
        fontSize: '0.74rem',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        background: palette.bg,
        color: palette.text,
        border: `1px solid ${palette.border}`,
      }}
    >
      {freshness}
    </span>
  )
}

function fmtTs(ts) {
  return ts ? new Date(ts).toLocaleString() : '–'
}

function fmtAge(seconds) {
  if (seconds == null) return '–'
  if (seconds < 60) return `${seconds}s ago`
  const mins = Math.floor(seconds / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  const rem = mins % 60
  return rem ? `${hrs}h ${rem}m ago` : `${hrs}h ago`
}

function SensorCard({ title, sensor, rows }) {
  return (
    <section style={{ background: '#1e293b', padding: '1rem', borderRadius: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '1rem' }}>{title}</h2>
        <FreshnessBadge freshness={sensor?.freshness || 'missing'} />
      </div>
      <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
        {rows.map((row) => (
          <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: '0.9rem' }}>
            <span style={{ color: '#94a3b8' }}>{row.label}</span>
            <span style={{ color: '#e2e8f0', textAlign: 'right' }}>{row.value}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Sensors({ api }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await apiFetch(`${api}/status/sensors`)
        if (!r.ok) throw new Error(r.statusText)
        const payload = await r.json()
        if (!cancelled) {
          setData(payload)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(String(e.message || e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 10000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [api])

  const mqttBadge = useMemo(() => getMqttBadge(data ? { mode: data.mode, mqtt: data.mqtt } : null), [data])

  if (loading && !data) return <p>Loading sensor monitor…</p>

  return (
    <div>
      <h1>Sensors</h1>
      <p style={{ color: '#94a3b8', fontSize: '0.92rem', maxWidth: 820 }}>
        Monitor raw sensor telemetry coming into the backend. This page shows the latest PV, battery, temp/humidity, light, and per-load sensor
        values along with freshness so you can tell whether the web UI is looking at live data, stale readings, or no sensor data yet.
      </p>

      {error && <p style={{ color: '#f87171' }}>Error: {error}</p>}

      {data && (
        <>
          <div
            style={{
              marginTop: '1rem',
              padding: '0.9rem 1rem',
              borderRadius: 10,
              background: '#0f172a',
              border: '1px solid #334155',
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
              <span style={{ color: '#cbd5e1' }}>
                <strong>Mode:</strong> {data.mode}
              </span>
              <span style={{ color: '#cbd5e1' }}>
                <strong>Freshness window:</strong> {data.freshness_threshold_seconds}s
              </span>
              <span style={{ color: '#cbd5e1' }}>
                <strong>Updated:</strong> {fmtTs(data.generated_at)}
              </span>
            </div>
            {mqttBadge && (
              <div style={{ marginTop: 10, color: '#cbd5e1', fontSize: '0.9rem' }}>
                <strong>MQTT:</strong> <span style={{ color: mqttBadge.color }}>{mqttBadge.label}</span>
                <span style={{ color: '#94a3b8' }}> · {mqttBadge.details}</span>
              </div>
            )}
          </div>

          <div
            style={{
              marginTop: '1.5rem',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1rem',
            }}
          >
            <SensorCard
              title="PV sensor"
              sensor={data.pv}
              rows={[
                { label: 'Power', value: data.pv?.power_kw != null ? `${data.pv.power_kw.toFixed(3)} kW` : '–' },
                { label: 'Voltage', value: data.pv?.voltage != null ? `${data.pv.voltage} V` : '–' },
                { label: 'Current', value: data.pv?.current_a != null ? `${data.pv.current_a.toFixed(2)} A` : '–' },
                { label: 'Timestamp', value: fmtTs(data.pv?.timestamp) },
                { label: 'Age', value: fmtAge(data.pv?.age_seconds) },
              ]}
            />
            <SensorCard
              title="Battery sensor"
              sensor={data.battery}
              rows={[
                { label: 'SOC', value: data.battery?.soc_percent != null ? `${data.battery.soc_percent.toFixed(1)}%` : '–' },
                { label: 'Voltage', value: data.battery?.voltage != null ? `${data.battery.voltage} V` : '–' },
                { label: 'Current', value: data.battery?.current_a != null ? `${data.battery.current_a.toFixed(2)} A` : '–' },
                { label: 'Timestamp', value: fmtTs(data.battery?.timestamp) },
                { label: 'Age', value: fmtAge(data.battery?.age_seconds) },
              ]}
            />
            <SensorCard
              title="Temp/Humidity sensor"
              sensor={data.temp_humidity}
              rows={[
                { label: 'Temperature', value: data.temp_humidity?.temp_c != null ? `${data.temp_humidity.temp_c.toFixed(1)} °C` : '–' },
                { label: 'Humidity', value: data.temp_humidity?.humidity_percent != null ? `${data.temp_humidity.humidity_percent.toFixed(1)} %` : '–' },
                { label: 'Timestamp', value: fmtTs(data.temp_humidity?.timestamp) },
                { label: 'Age', value: fmtAge(data.temp_humidity?.age_seconds) },
              ]}
            />
            <SensorCard
              title="Light sensor"
              sensor={data.light}
              rows={[
                { label: 'Is sunny', value: data.light?.is_sunny != null ? (data.light.is_sunny ? 'Yes' : 'No') : '–' },
                { label: 'Timestamp', value: fmtTs(data.light?.timestamp) },
                { label: 'Age', value: fmtAge(data.light?.age_seconds) },
              ]}
            />
          </div>

          <section style={{ marginTop: '1.75rem' }}>
            <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Load sensors</h2>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
                    <th style={{ padding: '0.55rem' }}>Appliance</th>
                    <th style={{ padding: '0.55rem' }}>Freshness</th>
                    <th style={{ padding: '0.55rem', textAlign: 'right' }}>Power</th>
                    <th style={{ padding: '0.55rem' }}>Sensor state</th>
                    <th style={{ padding: '0.55rem' }}>Expected</th>
                    <th style={{ padding: '0.55rem' }}>Control</th>
                    <th style={{ padding: '0.55rem' }}>Timestamp</th>
                    <th style={{ padding: '0.55rem' }}>Age</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.loads || []).map((load) => (
                    <tr key={load.appliance_id} style={{ borderBottom: '1px solid #1e293b' }}>
                      <td style={{ padding: '0.55rem' }}>
                        <div>{load.name}</div>
                        <div style={{ color: '#64748b', fontSize: '0.76rem' }}>{load.appliance_id}</div>
                      </td>
                      <td style={{ padding: '0.55rem' }}>
                        <FreshnessBadge freshness={load.freshness} />
                      </td>
                      <td style={{ padding: '0.55rem', textAlign: 'right' }}>{(load.power_kw || 0).toFixed(3)} kW</td>
                      <td style={{ padding: '0.55rem', color: load.state === 'stale' ? '#fde68a' : '#e2e8f0' }}>{load.state}</td>
                      <td style={{ padding: '0.55rem', color: load.expected_on ? '#4ade80' : '#cbd5e1' }}>{load.expected_on ? 'ON' : 'OFF'}</td>
                      <td style={{ padding: '0.55rem', color: load.manual_override_active ? '#fbbf24' : '#94a3b8' }}>
                        {load.manual_override_active ? 'Manual override' : 'IEBA'}
                      </td>
                      <td style={{ padding: '0.55rem' }}>{fmtTs(load.timestamp)}</td>
                      <td style={{ padding: '0.55rem' }}>{fmtAge(load.age_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
