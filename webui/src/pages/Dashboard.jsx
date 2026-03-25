import { useState, useEffect, useMemo } from 'react'
import { MultiLineChart, DonutChart, HorizontalBarChart } from '../components/Charts'
import { MqttStatusTooltip } from '../components/MqttStatusTooltip'
import { useAppSettings } from '../context/AppSettingsContext'
import { getMqttBadge } from '../utils/mqttStatus'

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
      .catch(() => setHistory({ points: [] }))
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
    const interval = setInterval(() => {
      fetchStatus()
      fetchHistory()
      fetchMqttHealth()
    }, 10000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [api])

  const chartData = useMemo(() => {
    const pts = downsample(history?.points || [], 100)
    if (!pts.length) return null
    return {
      soc: pts.map((p) => p.soc_percent ?? 0),
      pv: pts.map((p) => p.power_kw ?? 0),
      load: pts.map((p) => p.total_load_kw ?? 0),
      labels: pts.map((p) => (p.timestamp ? new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')),
    }
  }, [history])

  if (loading) return <p>Loading status…</p>
  if (error) return <p style={{ color: '#f87171' }}>Error: {error}</p>
  if (!status) return null

  const { pv, battery, loads, total_load_kw, simulated } = status
  const ts = status.timestamp ? new Date(status.timestamp).toLocaleString() : '–'
  const loadBars = loads
    .map((l) => {
      const on = l.state === 'on'
      const color = on ? '#22c55e' : '#64748b'
      return {
        label: l.name,
        value: l.power_kw,
        color,
        hoverTitle: showColorHover
          ? `${l.name}: ${l.power_kw.toFixed(3)} kW. Bar fill — ${
              on
                ? 'green: appliance ON (drawing power).'
                : 'slate gray: appliance OFF or shedded (no intentional draw).'
            }`
          : undefined,
      }
    })
    .sort((a, b) => b.value - a.value)
  const mqttBadge = getMqttBadge(mqttHealth)

  return (
    <div>
      <h1>Dashboard</h1>
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
      <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>Last updated: {ts}</p>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem', marginTop: '1.5rem', alignItems: 'start' }}>
        <Card title="PV generation" value={`${pv.power_kw.toFixed(2)} kW`} sub={`${pv.voltage} V, ${pv.current_a.toFixed(1)} A`} />
        <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, display: 'flex', justifyContent: 'center' }}>
          <DonutChart value={battery.soc_percent} label="Battery SOC" color="#0ea5e9" />
        </div>
        <Card title="Total load" value={`${total_load_kw.toFixed(2)} kW`} sub={`${loads.length} circuits`} />
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
            title="PV (kW) vs total load (kW)"
            series={[
              { name: 'PV kW', color: '#22c55e', values: chartData.pv },
              { name: 'Load kW', color: '#f59e0b', values: chartData.load },
            ]}
            labels={chartData.labels}
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
              <td style={{ padding: '0.5rem' }}>{l.state}</td>
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
      {sub && <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

