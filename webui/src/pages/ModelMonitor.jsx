import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { MultiLineChart } from '../components/Charts'

function Badge({ ok, label }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '0.35rem 0.65rem',
        borderRadius: 6,
        fontSize: '0.85rem',
        background: ok ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
        color: ok ? '#4ade80' : '#f87171',
        border: `1px solid ${ok ? '#166534' : '#991b1b'}`,
      }}
    >
      <span style={{ fontSize: '1rem' }}>{ok ? '●' : '○'}</span>
      {label}
    </span>
  )
}

export default function ModelMonitor({ api }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastFetch, setLastFetch] = useState(null)
  const load = useCallback(() => {
    setErr(null)
    fetch(`${api}/forecast/monitor?horizon_hours=24&compare=true`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
        return r.json()
      })
      .then(setData)
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => {
        setLoading(false)
        setLastFetch(new Date())
      })
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [autoRefresh, load])

  const pvCompare = useMemo(() => {
    const m = data?.model_series
    const s = data?.simulated_series
    if (!s?.timestamps?.length) return null
    const labels = s.timestamps.map((t) =>
      new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    )
    const series = [
      { name: 'Simulated PV', color: '#64748b', values: s.generation_kw || [] },
    ]
    if (m?.generation_kw?.length === s.generation_kw.length) {
      series.unshift({ name: 'LSTM PV', color: '#22c55e', values: m.generation_kw })
    }
    return { labels, series }
  }, [data])

  const loadCompare = useMemo(() => {
    const m = data?.model_series
    const s = data?.simulated_series
    if (!s?.timestamps?.length) return null
    const labels = s.timestamps.map((t) =>
      new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    )
    const series = [
      { name: 'Simulated demand', color: '#78716c', values: s.consumption_kw || [] },
    ]
    if (m?.consumption_kw?.length === s.consumption_kw.length) {
      series.unshift({ name: 'LSTM demand', color: '#f59e0b', values: m.consumption_kw })
    }
    return { labels, series }
  }, [data])

  if (loading && !data) return <p>Loading model monitor…</p>

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Model monitor</h1>
        <button
          type="button"
          onClick={() => {
            setLoading(true)
            load()
          }}
          style={{
            padding: '0.4rem 0.85rem',
            background: '#334155',
            border: 'none',
            borderRadius: 6,
            color: '#e2e8f0',
            cursor: 'pointer',
          }}
        >
          Refresh
        </button>
        <Link
          to="/training"
          style={{
            padding: '0.4rem 0.85rem',
            background: '#0ea5e9',
            borderRadius: 6,
            color: '#0b1220',
            fontWeight: 600,
            textDecoration: 'none',
            display: 'inline-block',
          }}
        >
          Training
        </Link>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.9rem', color: '#94a3b8' }}>
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
          Auto-refresh (15s)
        </label>
        {lastFetch && (
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Updated {lastFetch.toLocaleTimeString()}</span>
        )}
      </div>

      <p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: 720 }}>
        Tracks PyTorch, checkpoint files, and whether the <strong>Forecast</strong> API uses LSTMs. <strong>IEBA</strong>{' '}
        (<code>/schedule/run</code>) uses the same <strong>hybrid</strong> forecast as <strong>/forecast</strong> when
        checkpoints exist (Open-Meteo PV when enabled in settings; consumption from the load LSTM).
      </p>

      {err && (
        <p style={{ color: '#f87171', background: '#450a0a', padding: '0.75rem', borderRadius: 8 }}>{err}</p>
      )}
      {data && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '1rem' }}>
            <Badge ok={data.torch_available} label="PyTorch" />
            <Badge ok={data.gen_file_exists} label="gen_lstm.pt on disk" />
            <Badge ok={data.load_file_exists} label="load_lstm.pt on disk" />
            <Badge ok={data.models_load_ok} label="Checkpoints load" />
            <Badge ok={data.lstm_forecast_active} label="LSTM drives /forecast" />
          </div>

          <div
            style={{
              marginTop: '1.25rem',
              padding: '1rem',
              background: '#1e293b',
              borderRadius: 8,
              fontSize: '0.9rem',
            }}
          >
            <div style={{ marginBottom: 8 }}>
              <strong>Inference</strong> (24h rollout):{' '}
              <code style={{ color: '#38bdf8' }}>{data.inference_ms != null ? `${data.inference_ms} ms` : '–'}</code>
            </div>
            <div style={{ marginBottom: 8 }}>
              <strong>Seed</strong>: {data.seed_source}
              {data.seed_source === 'database' ? (
                <span style={{ color: '#94a3b8' }}> — LSTM window from MySQL (PV, SOC, load; ambient as-of).</span>
              ) : (
                <span style={{ color: '#94a3b8' }}>
                  {' '}
                  — synthetic constants (no battery rows in range yet, or DB unavailable during inference).
                </span>
              )}
            </div>
            <div style={{ color: '#cbd5e1' }}>{data.forecast_message}</div>
          </div>

          <div
            style={{
              marginTop: '1.25rem',
              padding: '1rem',
              background: '#0f172a',
              borderRadius: 8,
              border: '1px solid #334155',
            }}
          >
            <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>Model performance</h2>
            <p style={{ color: '#64748b', fontSize: '0.8rem', marginBottom: '0.75rem', maxWidth: 720 }}>
              <strong>sMAPE</strong> (symmetric MAPE) is shown for PV because classic MAPE blows up when power is near zero
              (e.g. night). <strong>MAPE (masked)</strong> uses only hours where |actual| ≥ 0.02 kW.
            </p>
            <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', fontSize: '0.9rem' }}>
              <div>
                <h3 style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: 6 }}>Validation (from training)</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <th style={{ textAlign: 'left', padding: '4px 8px 4px 0', color: '#64748b' }}>Metric</th>
                      <th style={{ textAlign: 'right', padding: '4px 0', color: '#64748b' }}>PV (gen)</th>
                      <th style={{ textAlign: 'right', padding: '4px 0', color: '#64748b' }}>Load</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <td style={{ padding: '6px 8px 6px 0' }}>sMAPE %</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.gen?.validation_smape != null ? `${Number(data.gen.validation_smape).toFixed(2)}%` : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.load?.validation_smape != null ? `${Number(data.load.validation_smape).toFixed(2)}%` : '–'}
                      </td>
                    </tr>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <td style={{ padding: '6px 8px 6px 0' }}>MAPE % (masked)</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.gen?.validation_mape_masked != null
                          ? `${Number(data.gen.validation_mape_masked).toFixed(2)}%`
                          : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.load?.validation_mape_masked != null
                          ? `${Number(data.load.validation_mape_masked).toFixed(2)}%`
                          : '–'}
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: '6px 8px 6px 0' }}>MAE (kW)</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.gen?.validation_mae != null ? Number(data.gen.validation_mae).toFixed(4) : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.load?.validation_mae != null ? Number(data.load.validation_mae).toFixed(4) : '–'}
                      </td>
                    </tr>
                  </tbody>
                </table>
                {!(data.gen?.validation_smape != null || data.load?.validation_smape != null) &&
                  (data.gen?.validation_mape_legacy != null || data.load?.validation_mape_legacy != null) && (
                  <p style={{ color: '#fdba74', fontSize: '0.8rem', marginTop: 6 }}>
                    Old checkpoint format (classic MAPE). <strong>Retrain</strong> with current <code>lstm_train.py</code>{' '}
                    for sMAPE + masked MAPE.
                  </p>
                )}
                {!(data.gen?.validation_smape != null || data.load?.validation_smape != null) &&
                  !(data.gen?.validation_mape_legacy != null || data.load?.validation_mape_legacy != null) && (
                  <p style={{ color: '#64748b', fontSize: '0.8rem', marginTop: 6 }}>
                    Re-train with current <code>lstm_train.py</code> to store validation metrics in checkpoints.
                  </p>
                )}
              </div>
              <div>
                <h3 style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: 6 }}>
                  Live (vs last {data.live_metrics_hours ?? 24}h actuals)
                </h3>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <th style={{ textAlign: 'left', padding: '4px 8px 4px 0', color: '#64748b' }}>Metric</th>
                      <th style={{ textAlign: 'right', padding: '4px 0', color: '#64748b' }}>PV (gen)</th>
                      <th style={{ textAlign: 'right', padding: '4px 0', color: '#64748b' }}>Load</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <td style={{ padding: '6px 8px 6px 0' }}>sMAPE %</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_smape_gen != null ? `${Number(data.live_smape_gen).toFixed(2)}%` : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_smape_load != null ? `${Number(data.live_smape_load).toFixed(2)}%` : '–'}
                      </td>
                    </tr>
                    <tr style={{ borderBottom: '1px solid #334155' }}>
                      <td style={{ padding: '6px 8px 6px 0' }}>MAPE % (masked)</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_mape_masked_gen != null ? `${Number(data.live_mape_masked_gen).toFixed(2)}%` : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_mape_masked_load != null ? `${Number(data.live_mape_masked_load).toFixed(2)}%` : '–'}
                      </td>
                    </tr>
                    <tr>
                      <td style={{ padding: '6px 8px 6px 0' }}>MAE (kW)</td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_mae_gen != null ? Number(data.live_mae_gen).toFixed(4) : '–'}
                      </td>
                      <td style={{ textAlign: 'right', padding: '6px 0' }}>
                        {data.live_mae_load != null ? Number(data.live_mae_load).toFixed(4) : '–'}
                      </td>
                    </tr>
                  </tbody>
                </table>
                {data.lstm_forecast_active &&
                  data.live_smape_gen == null &&
                  data.live_smape_load == null &&
                  data.live_mae_gen == null &&
                  data.live_mae_load == null && (
                  <p style={{ color: '#64748b', fontSize: '0.8rem', marginTop: 6 }}>
                    Need overlapping hourly history in DB to compute live metrics.
                  </p>
                )}
              </div>
            </div>
          </div>

          {data.errors?.length > 0 && (
            <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#422006', borderRadius: 8 }}>
              <strong style={{ color: '#fdba74' }}>Issues</strong>
              <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem', color: '#fed7aa' }}>
                {data.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ marginTop: '1.5rem', display: 'grid', gap: '1.25rem', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            <div style={{ background: '#0f172a', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
              <h2 style={{ fontSize: '0.95rem', marginTop: 0 }}>Generation model</h2>
              <code style={{ fontSize: '0.75rem', wordBreak: 'break-all', color: '#94a3b8' }}>{data.gen_path}</code>
              {data.gen ? (
                <dl style={{ fontSize: '0.85rem', marginTop: 12, marginBottom: 0 }}>
                  <dt style={{ color: '#64748b' }}>seq_len / hidden / feat_dim</dt>
                  <dd style={{ margin: '0 0 8px' }}>
                    {data.gen.seq_len} / {data.gen.hidden} / {data.gen.feat_dim}
                  </dd>
                  {(data.gen.validation_smape != null ||
                    data.gen.validation_mape_masked != null ||
                    data.gen.validation_mae != null) && (
                    <>
                      <dt style={{ color: '#64748b' }}>Validation</dt>
                      <dd style={{ margin: '0 0 8px' }}>
                        sMAPE {data.gen.validation_smape != null ? `${Number(data.gen.validation_smape).toFixed(2)}%` : '–'}
                        {data.gen.validation_mape_masked != null && (
                          <> · MAPE(mask) {Number(data.gen.validation_mape_masked).toFixed(2)}%</>
                        )}
                        {' · '}
                        MAE {data.gen.validation_mae != null ? Number(data.gen.validation_mae).toFixed(4) : '–'} kW
                      </dd>
                    </>
                  )}
                  {data.gen.validation_mape_legacy != null && data.gen.validation_smape == null && (
                    <dd style={{ margin: '0 0 8px', color: '#fdba74', fontSize: '0.8rem' }}>
                      Legacy MAPE {Number(data.gen.validation_mape_legacy).toFixed(0)}% — retrain for sMAPE
                    </dd>
                  )}
                  <dt style={{ color: '#64748b' }}>Features</dt>
                  <dd style={{ margin: 0 }}>{data.gen.feature_names.join(', ')}</dd>
                </dl>
              ) : (
                <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Not loaded</p>
              )}
            </div>
            <div style={{ background: '#0f172a', padding: '1rem', borderRadius: 8, border: '1px solid #334155' }}>
              <h2 style={{ fontSize: '0.95rem', marginTop: 0 }}>Load model</h2>
              <code style={{ fontSize: '0.75rem', wordBreak: 'break-all', color: '#94a3b8' }}>{data.load_path}</code>
              {data.load ? (
                <dl style={{ fontSize: '0.85rem', marginTop: 12, marginBottom: 0 }}>
                  <dt style={{ color: '#64748b' }}>seq_len / hidden / feat_dim</dt>
                  <dd style={{ margin: '0 0 8px' }}>
                    {data.load.seq_len} / {data.load.hidden} / {data.load.feat_dim}
                  </dd>
                  {(data.load.validation_smape != null ||
                    data.load.validation_mape_masked != null ||
                    data.load.validation_mae != null) && (
                    <>
                      <dt style={{ color: '#64748b' }}>Validation</dt>
                      <dd style={{ margin: '0 0 8px' }}>
                        sMAPE {data.load.validation_smape != null ? `${Number(data.load.validation_smape).toFixed(2)}%` : '–'}
                        {data.load.validation_mape_masked != null && (
                          <> · MAPE(mask) {Number(data.load.validation_mape_masked).toFixed(2)}%</>
                        )}
                        {' · '}
                        MAE {data.load.validation_mae != null ? Number(data.load.validation_mae).toFixed(4) : '–'} kW
                      </dd>
                    </>
                  )}
                  {data.load.validation_mape_legacy != null && data.load.validation_smape == null && (
                    <dd style={{ margin: '0 0 8px', color: '#fdba74', fontSize: '0.8rem' }}>
                      Legacy MAPE {Number(data.load.validation_mape_legacy).toFixed(0)}% — retrain for sMAPE
                    </dd>
                  )}
                  <dt style={{ color: '#64748b' }}>Features</dt>
                  <dd style={{ margin: 0 }}>{data.load.feature_names.join(', ')}</dd>
                </dl>
              ) : (
                <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Not loaded</p>
              )}
            </div>
          </div>

          <section style={{ marginTop: '2rem' }}>
            <h2 style={{ fontSize: '1.05rem' }}>LSTM vs simulated (24h)</h2>
            {!data.lstm_forecast_active && (
              <p style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
                Train and place both checkpoints under <code>ai/models/</code> to see the green/orange LSTM curves
                alongside the simulated baseline.
              </p>
            )}
            {(pvCompare || loadCompare) && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                  gap: '1rem',
                  marginTop: 12,
                  alignItems: 'start',
                }}
              >
                {pvCompare && (
                  <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
                    <MultiLineChart series={pvCompare.series} labels={pvCompare.labels} height={200} title="PV (kW)" />
                  </div>
                )}
                {loadCompare && (
                  <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
                    <MultiLineChart
                      series={loadCompare.series}
                      labels={loadCompare.labels}
                      height={200}
                      title="Demand (kW)"
                    />
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
