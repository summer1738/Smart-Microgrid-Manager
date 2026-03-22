import { useState, useEffect, useMemo } from 'react'
import { MultiLineChart } from '../components/Charts'

export default function Forecast({ api }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${api}/forecast?horizon_hours=24`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false))
  }, [api])

  const lineData = useMemo(() => {
    const series = data?.series
    if (!series?.timestamps?.length) return null
    const labels = series.timestamps.map((t) =>
      new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    )
    return {
      labels,
      gen: series.generation_kw || [],
      cons: series.consumption_kw || [],
    }
  }, [data])

  if (loading) return <p>Loading…</p>
  if (!data) return null

  const series = data.series
  const hasSeries = series && series.timestamps && series.timestamps.length > 0
  const maxGen = hasSeries ? Math.max(...series.generation_kw, 0.001) : 1
  const maxCons = hasSeries ? Math.max(...series.consumption_kw, 0.001) : 1
  const scale = (v, m) => (m > 0 ? (v / m) * 100 : 0)

  return (
    <div>
      <h1>Forecast</h1>
      <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
        Generated at: {data.generated_at ? new Date(data.generated_at).toLocaleString() : '–'} · Horizon: {data.horizon_hours} h
      </p>
      {data.message && <p style={{ background: '#1e293b', padding: '0.5rem 0.75rem', borderRadius: 6 }}>{data.message}</p>}

      {lineData && lineData.gen.length > 0 && (
        <section style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Forecast curves (kW)</h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: '1rem',
              alignItems: 'start',
            }}
          >
            <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
              <MultiLineChart
                series={[{ name: 'PV generation', color: '#22c55e', values: lineData.gen }]}
                labels={lineData.labels}
                height={220}
                title="PV generation (kW)"
              />
            </div>
            <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
              <MultiLineChart
                series={[{ name: 'Demand', color: '#f59e0b', values: lineData.cons }]}
                labels={lineData.labels}
                height={220}
                title="Demand (kW)"
              />
            </div>
          </div>
        </section>
      )}

      {hasSeries && (
        <div style={{ marginTop: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Hourly bars (kW)</h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1rem',
            }}
          >
            <div style={{ background: '#1e293b', padding: '0.75rem', borderRadius: 8 }}>
              <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: 6 }}>PV generation</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 160, overflowX: 'auto' }}>
                {series.timestamps.map((_, i) => (
                  <div
                    key={`pv-${i}`}
                    style={{
                      flex: '1 0 8px',
                      minWidth: 6,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <div
                      style={{
                        height: `${scale(series.generation_kw[i], maxGen)}%`,
                        minHeight: series.generation_kw[i] > 0 ? 4 : 0,
                        background: '#22c55e',
                        borderRadius: 2,
                      }}
                      title={`PV: ${series.generation_kw[i].toFixed(2)} kW`}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div style={{ background: '#1e293b', padding: '0.75rem', borderRadius: 8 }}>
              <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: 6 }}>Demand</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 160, overflowX: 'auto' }}>
                {series.timestamps.map((_, i) => (
                  <div
                    key={`dem-${i}`}
                    style={{
                      flex: '1 0 8px',
                      minWidth: 6,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <div
                      style={{
                        height: `${scale(series.consumption_kw[i], maxCons)}%`,
                        minHeight: series.consumption_kw[i] > 0 ? 4 : 0,
                        background: '#f59e0b',
                        borderRadius: 2,
                      }}
                      title={`Demand: ${series.consumption_kw[i].toFixed(2)} kW`}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
