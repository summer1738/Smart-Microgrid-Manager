import { useState, useEffect, useMemo } from 'react'
import { ScheduleHeatmap, buildScheduleMatrix } from '../components/Charts'
import { apiFetch } from '../utils/api'

export default function Schedule({ api }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  const fetchSchedule = () => {
    apiFetch(`${api}/schedule`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchSchedule()
  }, [api])

  const heatmap = useMemo(() => {
    const slots = data?.slots || []
    const { matrix, names, hours } = buildScheduleMatrix(slots)
    const hourLabels = hours.map((h) => `${h}h`)
    return { matrix, names, hourLabels }
  }, [data?.slots])

  const runIeba = () => {
    setRunning(true)
    apiFetch(`${api}/schedule/run`, { method: 'POST' })
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ slots: [], message: 'Run failed.' }))
      .finally(() => setRunning(false))
  }

  const applyNow = () => {
    apiFetch(`${api}/schedule/apply`, { method: 'POST' })
      .then((r) => r.json())
      .then((res) => alert(`Applied: ${res.slots_applied} slots, ${res.appliances_updated} appliances updated.`))
      .catch(() => alert('Apply failed.'))
  }

  if (loading && !data) return <p>Loading…</p>

  return (
    <div>
      <h1>IEBA Schedule</h1>
      <p style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={runIeba}
          disabled={running}
          style={{ padding: '0.5rem 1rem', borderRadius: 6, background: '#0ea5e9', color: '#0f172a', border: 'none', fontWeight: 600 }}
        >
          {running ? 'Running IEBA…' : 'Run IEBA (optimize 24h schedule)'}
        </button>
        <button
          type="button"
          onClick={applyNow}
          style={{ padding: '0.5rem 1rem', borderRadius: 6, background: '#334155', color: '#e2e8f0', border: 'none', fontWeight: 600 }}
        >
          Apply schedule now
        </button>
      </p>
      <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginTop: 4 }}>
        Green blocks = load scheduled <strong>on</strong> for that hour. Table below lists every slot.
      </p>
      {data?.message && (
        <p style={{ background: '#1e293b', padding: '1rem', borderRadius: 8, marginTop: '1rem' }}>
          {data.message}
        </p>
      )}
      {heatmap.matrix.length > 0 && (
        <ScheduleHeatmap matrix={heatmap.matrix} applianceNames={heatmap.names} hourLabels={heatmap.hourLabels} />
      )}
      {data?.slots && data.slots.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1.5rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #334155' }}>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Appliance</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>Start</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>End</th>
              <th style={{ textAlign: 'left', padding: '0.5rem' }}>State</th>
            </tr>
          </thead>
          <tbody>
            {data.slots.map((s, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #334155' }}>
                <td style={{ padding: '0.5rem' }}>{s.appliance_name}</td>
                <td style={{ padding: '0.5rem' }}>{new Date(s.start_ts).toLocaleString()}</td>
                <td style={{ padding: '0.5rem' }}>{new Date(s.end_ts).toLocaleString()}</td>
                <td style={{ padding: '0.5rem' }}>
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: s.planned_state === 'on' ? '#14532d' : '#334155',
                      color: s.planned_state === 'on' ? '#86efac' : '#94a3b8',
                    }}
                  >
                    {s.planned_state}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
