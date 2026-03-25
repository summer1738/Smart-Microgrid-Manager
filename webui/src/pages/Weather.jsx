import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { MultiLineChart } from '../components/Charts'

function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function Weather({ api }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${api}/forecast/weather-insights?forecast_days=16&history_days=30`)
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText)
        return r.json()
      })
      .then((j) => {
        if (!cancelled) setData(j)
      })
      .catch((e) => {
        if (!cancelled) setErr(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  const forecastChart = useMemo(() => {
    const rows = data?.daily_weather || []
    if (!rows.length) return null
    return {
      labels: rows.map((r) => shortDate(r.date)),
      values: rows.map((r) => r.expected_pv_kwh ?? 0),
    }
  }, [data])

  const historyChart = useMemo(() => {
    const rows = data?.historical_daily_pv_kwh || []
    if (!rows.length) return null
    return {
      labels: rows.map((r) => shortDate(r.date)),
      values: rows.map((r) => r.actual_pv_kwh ?? 0),
    }
  }, [data])

  if (loading) return <p>Loading weather & PV insights…</p>
  if (err) return <p style={{ color: '#f87171' }}>Error: {err}</p>
  if (!data) return null

  const loc = data.location
  const comp = data.comparison

  return (
    <div>
      <h1>Weather &amp; PV outlook</h1>
      <p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: 720 }}>
        Open-Meteo hourly forecast (up to 16 days) for the <strong>system location</strong>{' '}
        <strong>
          {loc?.latitude?.toFixed(2)}, {loc?.longitude?.toFixed(2)}
        </strong>
        , compared with <strong>actual PV energy</strong> integrated from your database (recent history). Change the
        system location and PV nameplate in <Link to="/settings">Settings</Link>.
      </p>
      {data.summary_message && (
        <p style={{ background: '#1e293b', padding: '0.5rem 0.75rem', borderRadius: 6, marginTop: '0.75rem' }}>
          {data.summary_message}
        </p>
      )}
      {data.message && !data.forecast_available && (
        <p style={{ color: '#fbbf24', marginTop: '0.5rem' }}>{data.message}</p>
      )}

      {comp && (
        <section
          style={{
            marginTop: '1.5rem',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1rem',
          }}
        >
          <StatCard title="Next 14 days (forecast PV)" value={`${comp.next_14d_forecast_pv_kwh ?? '–'} kWh`} />
          <StatCard title="Last 14 days (actual PV)" value={`${comp.last_14d_actual_pv_kwh ?? '–'} kWh`} />
          <StatCard
            title="Forecast / actual ratio"
            value={comp.ratio_forecast_over_actual != null ? `${comp.ratio_forecast_over_actual}` : '–'}
            sub=">1 means next two weeks sunnier than the last two weeks (PV-wise)"
          />
        </section>
      )}

      {forecastChart && (
        <section style={{ marginTop: '2rem', background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
          <h2 style={{ fontSize: '1rem', marginBottom: 8 }}>Expected PV energy by day (from weather)</h2>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 0 }}>
            Hourly shortwave × array capacity (see backend weather settings).
          </p>
          <MultiLineChart
            series={[{ name: 'kWh/day', color: '#22c55e', values: forecastChart.values }]}
            labels={forecastChart.labels}
            height={200}
            title="kWh/day"
          />
        </section>
      )}

      {historyChart && (
        <section style={{ marginTop: '1.5rem', background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
          <h2 style={{ fontSize: '1rem', marginBottom: 8 }}>Past PV energy (database)</h2>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 0 }}>
            Trapezoidal integration of <code>pv_readings.power_kw</code> per day — your simulator or hardware trend.
          </p>
          <MultiLineChart
            series={[{ name: 'Actual kWh/day', color: '#38bdf8', values: historyChart.values }]}
            labels={historyChart.labels}
            height={200}
            title="kWh/day"
          />
        </section>
      )}

      {data.daily_weather?.length > 0 && (
        <section style={{ marginTop: '2rem' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Daily weather summary (forecast)</h2>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
                  <th style={{ padding: '0.5rem' }}>Date</th>
                  <th style={{ padding: '0.5rem' }}>Avg cloud %</th>
                  <th style={{ padding: '0.5rem' }}>Max SW (W/m²)</th>
                  <th style={{ padding: '0.5rem' }}>Conditions</th>
                  <th style={{ padding: '0.5rem', textAlign: 'right' }}>Expected PV (kWh)</th>
                </tr>
              </thead>
              <tbody>
                {data.daily_weather.map((row) => (
                  <tr key={row.date} style={{ borderBottom: '1px solid #1e293b' }}>
                    <td style={{ padding: '0.5rem' }}>{row.date}</td>
                    <td style={{ padding: '0.5rem' }}>{row.avg_cloud_cover_pct ?? '–'}</td>
                    <td style={{ padding: '0.5rem' }}>{row.max_shortwave_wm2 ?? '–'}</td>
                    <td style={{ padding: '0.5rem', color: '#cbd5e1' }}>{row.dominant_weather_label}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>{row.expected_pv_kwh}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!forecastChart && !historyChart && (
        <p style={{ marginTop: '1.5rem', color: '#94a3b8' }}>No forecast or history data yet. Run the backend simulator to accumulate PV readings.</p>
      )}
    </div>
  )
}

function StatCard({ title, value, sub }) {
  return (
    <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
      <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{title}</div>
      <div style={{ fontSize: '1.35rem', fontWeight: 600, marginTop: 6 }}>{value}</div>
      {sub && <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 6 }}>{sub}</div>}
    </div>
  )
}
