import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../utils/api'

function ToggleSwitch({ checked, onChange, disabled = false }) {
  return (
    <label
      style={{
        position: 'relative',
        display: 'inline-block',
        width: 44,
        height: 24,
        opacity: disabled ? 0.65 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        flexShrink: 0,
      }}
    >
      <input
        type="checkbox"
        checked={!!checked}
        disabled={disabled}
        onChange={(e) => onChange(!!e.target.checked)}
        style={{ display: 'none' }}
      />
      <span
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: checked ? '#22c55e' : '#334155',
          transition: 'all 0.2s ease',
          borderRadius: 999,
          border: '1px solid #334155',
        }}
      />
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: 3,
          width: 18,
          height: 18,
          background: '#0f172a',
          borderRadius: '50%',
          transform: `translateX(${checked ? 20 : 0}px)`,
          transition: 'all 0.2s ease',
          boxShadow: '0 2px 10px rgba(0,0,0,0.35)',
        }}
      />
    </label>
  )
}

export default function Training({ api }) {
  const [status, setStatus] = useState(null)
  const [statusErr, setStatusErr] = useState(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [trainBusy, setTrainBusy] = useState(false)
  const [trainResult, setTrainResult] = useState(null)
  const [autoSaving, setAutoSaving] = useState(false)
  const [activeJob, setActiveJob] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [jobPolling, setJobPolling] = useState(false)

  const loadStatus = useCallback(() => {
    setStatusErr(null)
    return apiFetch(`${api}/forecast/training-status`)
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText)
        return r.json()
      })
      .then((d) => {
        setStatus(d)
        if (d?.last_train) {
          setTrainResult({
            ok: !!d.last_train.ok,
            message: d.last_train.message,
            output: d.last_train.output,
          })
        }
      })
      .catch((e) => setStatusErr(e.message))
      .finally(() => setLoadingStatus(false))
  }, [api])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  const runTraining = async () => {
    setTrainBusy(true)
    setTrainResult(null)
    setActiveJob(null)
    setJobId(null)
    setJobPolling(false)
    try {
      const r = await apiFetch(`${api}/forecast/monitor/train-now-async`, { method: 'POST' })
      const j = await r.json()
      if (!r.ok || !j.job_id) throw new Error(j?.message || 'Failed to start training job')
      setActiveJob(j)
      setJobId(j.job_id)
      setJobPolling(true)
    } catch (e) {
      setTrainResult({ ok: false, message: String(e.message || e), output: '' })
      setStatusErr(String(e.message || e))
      setTrainBusy(false)
      setJobPolling(false)
      setActiveJob(null)
      setJobId(null)
    } finally {
      // trainBusy is cleared by the poller when the job finishes.
    }
  }

  useEffect(() => {
    if (!jobPolling || !jobId) return
    let cancelled = false
    const id = setInterval(async () => {
      try {
        const r = await apiFetch(`${api}/forecast/monitor/train-now-progress?job_id=${jobId}`)
        const j = await r.json()
        if (cancelled) return
        setActiveJob(j)
        if (j.state === 'done' || j.state === 'failed') {
          setJobPolling(false)
          setTrainBusy(false)
          setTrainResult({
            ok: j.state === 'done',
            message: j.message || (j.state === 'done' ? 'Success' : 'Failed'),
            output: j.log_tail || '',
          })
          await loadStatus()
        }
      } catch (e) {
        // best-effort polling; UI keeps whatever last job state we have
      }
    }, 2000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [api, jobId, jobPolling, loadStatus])

  const setAutoTrain = async (enabled) => {
    setAutoSaving(true)
    setStatusErr(null)
    try {
      const r = await apiFetch(`${api}/system/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_train_enabled: enabled }),
      })
      if (!r.ok) throw new Error(await r.text())
      await loadStatus()
    } catch (e) {
      setStatusErr(e.message || 'Failed to save')
    } finally {
      setAutoSaving(false)
    }
  }

  const ready =
    status?.torch_available &&
    status?.enough_samples &&
    !loadingStatus

  return (
    <div>
      <p style={{ marginBottom: '1rem' }}>
        <Link to="/">Dashboard</Link>
        {' · '}
        <Link to="/model-monitor">Model monitor</Link>
      </p>
      <h1>LSTM training</h1>
      {/*<p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: 720 }}>
        All training runs on the server from this page: export readings → build datasets → train both models. No terminal
        commands needed after PyTorch is installed in the backend venv (one-time <code>pip install … torch</code>).
      </p>*/}

      {statusErr && <p style={{ color: '#f87171', marginTop: '0.75rem' }}>{statusErr}</p>}

      {loadingStatus && !status && <p style={{ color: '#94a3b8' }}>Loading status…</p>}

      {status && (
        <section
          style={{
            marginTop: '1.25rem',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1rem',
          }}
        >
          <StatusPill
            ok={status.torch_available}
            label="PyTorch in backend"
            detail={status.torch_available ? 'OK' : 'Install CPU torch in venv'}
          />
          <StatusPill
            ok={status.enough_samples}
            label="Database samples"
            detail={`${status.battery_readings_count} / ${status.min_samples_required} battery_readings`}
          />
          <StatusPill
            ok={status.auto_train_enabled}
            label="Scheduled auto-train"
            detail={status.auto_train_enabled ? 'On' : 'Off'}
          />
        </section>
      )}

      {status && (
        <section style={{ marginTop: '1.25rem', background: '#1e293b', padding: '1rem 1.25rem', borderRadius: 8, maxWidth: 640 }}>
          <h2 style={{ fontSize: '1rem', marginTop: 0 }}>Scheduled training</h2>
          <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: 0 }}>
            Every <strong>{status.auto_train_interval_minutes}</strong> minutes (env), using the last{' '}
            <strong>{status.auto_train_history_hours}</strong> hours of data.
          </p>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: autoSaving ? 'wait' : 'pointer' }}>
            <ToggleSwitch
              checked={!!status.auto_train_enabled}
              disabled={autoSaving}
              onChange={(val) => setAutoTrain(val)}
            />
            <span>Enable automatic retraining</span>
          </label>
        </section>
      )}

      <section style={{ marginTop: '1.5rem', background: '#0f172a', padding: '1.25rem', borderRadius: 8, border: '1px solid #334155', maxWidth: 720 }}>
        <h2 style={{ fontSize: '1rem', marginTop: 0 }}>Run full pipeline now</h2>
        <ol style={{ color: '#94a3b8', fontSize: '0.9rem', paddingLeft: '1.25rem', marginBottom: '1rem' }}>
          {(status?.pipeline_steps || []).map((s, i) => (
            <li key={i} style={{ marginBottom: 4 }}>
              {s}
            </li>
          ))}
        </ol>
        <button
          type="button"
          disabled={trainBusy || !ready || (activeJob && activeJob.state === 'running')}
          onClick={runTraining}
          style={{
            padding: '0.65rem 1.25rem',
            background: trainBusy || !ready ? '#334155' : '#0ea5e9',
            border: 'none',
            borderRadius: 8,
            color: trainBusy || !ready ? '#94a3b8' : '#0b1220',
            fontWeight: 700,
            cursor: trainBusy || !ready ? 'not-allowed' : 'pointer',
          }}
        >
          {trainBusy ? 'Training… (may take several minutes)' : 'Start training'}
        </button>

        {activeJob && (activeJob.state === 'running' || activeJob.state === 'queued') && (
          <div style={{ marginTop: 14 }}>
            <h3 style={{ fontSize: '0.95rem', marginTop: 0, marginBottom: 8 }}>Training progress</h3>
            <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: 8 }}>
              Step {activeJob.current_step + 1} / 5: <strong style={{ color: '#e2e8f0' }}>{activeJob.current_label || '…'}</strong>
            </div>
            <div style={{ height: 10, background: '#1e293b', borderRadius: 999, overflow: 'hidden', border: '1px solid #334155' }}>
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, activeJob.progress || 0))}%`,
                  height: '100%',
                  background: '#0ea5e9',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <div style={{ marginTop: 12, background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '0.75rem' }}>
              <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: 8 }}>Live log tail</div>
              <pre
                style={{
                  margin: 0,
                  maxHeight: 220,
                  overflow: 'auto',
                  fontSize: '0.75rem',
                  color: '#cbd5e1',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {activeJob.log_tail || ''}
              </pre>
            </div>
          </div>
        )}

        {!ready && status && (
          <p style={{ color: '#fbbf24', fontSize: '0.85rem', marginTop: '0.75rem', marginBottom: 0 }}>
            {!status.torch_available && 'Install PyTorch in the backend venv. '}
            {!status.enough_samples && 'Let the simulator run longer until sample count is met. '}
          </p>
        )}
        <button
          type="button"
          onClick={() => {
            setLoadingStatus(true)
            loadStatus()
          }}
          style={{
            marginLeft: 12,
            padding: '0.65rem 1rem',
            background: '#334155',
            border: 'none',
            borderRadius: 8,
            color: '#e2e8f0',
            cursor: 'pointer',
          }}
        >
          Refresh status
        </button>
      </section>

      {trainResult && (
        <section style={{ marginTop: '1.25rem' }}>
          <h2 style={{ fontSize: '1rem' }}>Last run</h2>
          <p style={{ color: trainResult.ok ? '#86efac' : '#f87171', marginBottom: '0.5rem' }}>
            {trainResult.ok ? 'Success' : 'Failed'}: {trainResult.message}
          </p>
          {trainResult.output ? (
            <pre
              style={{
                background: '#0f172a',
                border: '1px solid #334155',
                borderRadius: 8,
                padding: '1rem',
                fontSize: '0.75rem',
                overflow: 'auto',
                maxHeight: 360,
                color: '#cbd5e1',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {trainResult.output}
            </pre>
          ) : null}
        </section>
      )}
    </div>
  )
}

function StatusPill({ ok, label, detail }) {
  return (
    <div
      style={{
        background: '#1e293b',
        borderRadius: 8,
        padding: '0.75rem 1rem',
        border: `1px solid ${ok ? '#166534' : '#7f1d1d'}`,
      }}
    >
      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{label}</div>
      <div style={{ fontSize: '1rem', fontWeight: 600, color: ok ? '#4ade80' : '#f87171', marginTop: 4 }}>
        {ok ? 'Ready' : 'Blocked'}
      </div>
      <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: 6 }}>{detail}</div>
    </div>
  )
}
