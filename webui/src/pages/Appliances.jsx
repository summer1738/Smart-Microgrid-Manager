import { useState, useEffect, useMemo } from 'react'
import { HorizontalBarChart } from '../components/Charts'
import { apiFetch } from '../utils/api'

function ToggleSwitch({ checked, onChange, label }) {
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 10, cursor: 'pointer', userSelect: 'none' }}>
      <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>{label}</span>
      <span
        onClick={() => onChange(!checked)}
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') onChange(!checked)
        }}
        style={{
          width: 44,
          height: 24,
          borderRadius: 999,
          background: checked ? '#22c55e' : '#334155',
          border: '1px solid #475569',
          position: 'relative',
          transition: 'background 150ms ease',
        }}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: 999,
            background: '#0f172a',
            position: 'absolute',
            top: 2,
            left: checked ? 22 : 2,
            transition: 'left 150ms ease',
            border: '1px solid #0b1220',
          }}
        />
      </span>
    </label>
  )
}

function prefSummary(schedule_prefs) {
  if (!schedule_prefs) return 'Run as long as possible'
  try {
    const p = JSON.parse(schedule_prefs)
    if (p?.mode !== 'preferred_times') return 'Run as long as possible'
    const w = Array.isArray(p.windows) ? p.windows : []
    const windows = w.map((x) => `${x.start}-${x.end}`).join(', ')
    return `${p.hard ? 'Hard' : 'Soft'} windows: ${windows || '(none)'}`
  } catch {
    return 'Run as long as possible'
  }
}

function usageModeLabel(mode) {
  return mode === 'on_demand' ? 'On-demand' : 'Scheduled'
}

function decisionTone(decision) {
  if (decision === 'approved_now') return { border: '#22c55e', bg: '#052e16', text: '#bbf7d0', title: 'Approved now' }
  if (decision === 'deferred') return { border: '#f59e0b', bg: '#3f2a05', text: '#fde68a', title: 'Deferred' }
  if (decision === 'rejected') return { border: '#ef4444', bg: '#3f0d12', text: '#fecaca', title: 'Rejected' }
  return { border: '#475569', bg: '#0f172a', text: '#cbd5e1', title: 'Decision' }
}

const QUICK_RUN_MINUTES = [15, 30, 60]

export default function Appliances({ api }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    name: '',
    priority: 2,
    rated_watts: 100,
    usage_mode: 'scheduled',
    default_run_minutes: 30,
    run_mode: 'max_possible', // max_possible | preferred_times
    hard: false,
    windows: [{ start: '07:00', end: '09:00' }],
  })
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({
    name: '',
    priority: 2,
    rated_watts: 100,
    usage_mode: 'scheduled',
    default_run_minutes: 30,
    run_mode: 'max_possible',
    hard: false,
    windows: [{ start: '07:00', end: '09:00' }],
  })
  const [runRequestBusyId, setRunRequestBusyId] = useState(null)
  const [runRequestResult, setRunRequestResult] = useState(null)

  const fetchList = async () => {
    try {
      const r = await apiFetch(`${api}/appliances`)
      if (!r.ok) throw new Error(r.statusText)
      const data = await r.json()
      setList(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchList()
  }, [api])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const schedule_prefs =
        form.run_mode === 'preferred_times'
          ? JSON.stringify({ mode: 'preferred_times', hard: !!form.hard, windows: form.windows })
          : JSON.stringify({ mode: 'max_possible' })
      const r = await apiFetch(`${api}/appliances`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          priority: form.priority,
          rated_watts: form.rated_watts,
          usage_mode: form.usage_mode,
          default_run_minutes: form.default_run_minutes,
          schedule_prefs,
        }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || r.statusText)
      }
      setForm({
        name: '',
        priority: 2,
        rated_watts: 100,
        usage_mode: 'scheduled',
        default_run_minutes: 30,
        run_mode: 'max_possible',
        hard: false,
        windows: [{ start: '07:00', end: '09:00' }],
      })
      await fetchList()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const priorityLabel = (p) => (p === 1 ? 'Critical' : p === 2 ? 'Essential' : 'Non-essential')

  const startEdit = (a) => {
    setEditingId(a.id)
    let pref = { mode: 'max_possible', hard: false, windows: [{ start: '07:00', end: '09:00' }] }
    try {
      if (a.schedule_prefs) pref = JSON.parse(a.schedule_prefs)
    } catch {}
    setEditForm({
      name: a.name,
      priority: a.priority,
      rated_watts: a.rated_watts,
      usage_mode: a.usage_mode || 'scheduled',
      default_run_minutes: a.default_run_minutes || 30,
      run_mode: pref.mode === 'preferred_times' ? 'preferred_times' : 'max_possible',
      hard: !!pref.hard,
      windows: Array.isArray(pref.windows) && pref.windows.length ? pref.windows : [{ start: '07:00', end: '09:00' }],
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  const saveEdit = async (id) => {
    try {
      const schedule_prefs =
        editForm.run_mode === 'preferred_times'
          ? JSON.stringify({ mode: 'preferred_times', hard: !!editForm.hard, windows: editForm.windows })
          : JSON.stringify({ mode: 'max_possible' })
      const r = await apiFetch(`${api}/appliances/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editForm.name,
          priority: editForm.priority,
          rated_watts: editForm.rated_watts,
          usage_mode: editForm.usage_mode,
          default_run_minutes: editForm.default_run_minutes,
          schedule_prefs,
        }),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || r.statusText)
      }
      setEditingId(null)
      await fetchList()
    } catch (e) {
      setError(e.message)
    }
  }

  const requestRunNow = async (appliance, durationMinutes = null) => {
    setRunRequestBusyId(appliance.id)
    setRunRequestResult(null)
    try {
      const requestedMinutes = durationMinutes || appliance.default_run_minutes || 30
      const r = await apiFetch(`${api}/appliances/${appliance.id}/request-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_minutes: requestedMinutes }),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.detail || r.statusText)
      setRunRequestResult(data)
      await fetchList()
    } catch (e) {
      setRunRequestResult({
        appliance_name: appliance.name,
        decision: 'rejected',
        message: e.message,
      })
    } finally {
      setRunRequestBusyId(null)
    }
  }

  const deleteAppliance = async (id) => {
    if (!window.confirm('Delete this appliance?')) return
    try {
      const r = await apiFetch(`${api}/appliances/${id}`, { method: 'DELETE' })
      if (!r.ok && r.status !== 204) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || r.statusText)
      }
      await fetchList()
    } catch (e) {
      setError(e.message)
    }
  }

  const charts = useMemo(() => {
    if (!list.length) return { byPriority: [], topRated: [] }
    const p1 = list.filter((a) => a.priority === 1).reduce((s, a) => s + a.rated_watts, 0)
    const p2 = list.filter((a) => a.priority === 2).reduce((s, a) => s + a.rated_watts, 0)
    const p3 = list.filter((a) => a.priority === 3).reduce((s, a) => s + a.rated_watts, 0)
    const byPriority = [
      { label: 'Priority 1 – Critical', value: p1, color: '#ef4444' },
      { label: 'Priority 2 – Essential', value: p2, color: '#f59e0b' },
      { label: 'Priority 3 – Non-essential', value: p3, color: '#64748b' },
    ]
    const topRated = [...list]
      .sort((a, b) => b.rated_watts - a.rated_watts)
      .slice(0, 12)
      .map((a) => ({ label: a.name, value: a.rated_watts, color: '#0ea5e9' }))
    return { byPriority, topRated }
  }, [list])

  if (loading) return <p>Loading appliances…</p>

  return (
    <div>
      <h1>Appliances (UCLPI)</h1>
      {error && <p style={{ color: '#f87171' }}>{error}</p>}

      <form onSubmit={handleSubmit} style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
        <input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          required
          style={{ padding: '0.5rem', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0' }}
        />
        <select
          value={form.priority}
          onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
          style={{ padding: '0.5rem', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0' }}
        >
          <option value={1}>Priority 1 – Critical</option>
          <option value={2}>Priority 2 – Essential</option>
          <option value={3}>Priority 3 – Non-essential</option>
        </select>
        <input
          type="number"
          placeholder="Rated (W)"
          value={form.rated_watts}
          onChange={(e) => setForm((f) => ({ ...f, rated_watts: Number(e.target.value) || 0 }))}
          min={1}
          style={{ width: 100, padding: '0.5rem', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0' }}
        />
        <select
          value={form.usage_mode}
          onChange={(e) => setForm((f) => ({ ...f, usage_mode: e.target.value }))}
          style={{ padding: '0.5rem', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0' }}
        >
          <option value="scheduled">Scheduled</option>
          <option value="on_demand">On-demand</option>
        </select>
        <input
          type="number"
          placeholder="Default run (min)"
          value={form.default_run_minutes}
          onChange={(e) => setForm((f) => ({ ...f, default_run_minutes: Number(e.target.value) || 30 }))}
          min={5}
          style={{ width: 140, padding: '0.5rem', borderRadius: 6, border: '1px solid #475569', background: '#1e293b', color: '#e2e8f0' }}
        />
        <button type="submit" disabled={saving} style={{ padding: '0.5rem 1rem', borderRadius: 6, background: '#0ea5e9', color: '#0f172a', border: 'none', fontWeight: 600 }}>
          {saving ? 'Adding…' : 'Add appliance'}
        </button>
      </form>
      {runRequestResult && (
        <div
          style={{
            marginTop: 10,
            padding: '0.8rem 1rem',
            borderRadius: 8,
            border: `1px solid ${decisionTone(runRequestResult.decision).border}`,
            background: decisionTone(runRequestResult.decision).bg,
            color: decisionTone(runRequestResult.decision).text,
            maxWidth: 920,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            {decisionTone(runRequestResult.decision).title}: {runRequestResult.appliance_name}
          </div>
          <div style={{ fontSize: '0.9rem' }}>{runRequestResult.message}</div>
          {runRequestResult.recommended_start_ts && (
            <div style={{ marginTop: 6, fontSize: '0.85rem', color: '#f8fafc' }}>
              Recommended start: {new Date(runRequestResult.recommended_start_ts).toLocaleString()}
            </div>
          )}
          {runRequestResult.scheduled_start_ts && runRequestResult.scheduled_end_ts && (
            <div style={{ marginTop: 6, fontSize: '0.85rem', color: '#f8fafc' }}>
              Scheduled: {new Date(runRequestResult.scheduled_start_ts).toLocaleString()} to{' '}
              {new Date(runRequestResult.scheduled_end_ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          )}
        </div>
      )}

      <div style={{ marginTop: 12, background: '#1e293b', padding: '0.75rem 1rem', borderRadius: 8, maxWidth: 920 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
          <div style={{ fontSize: '0.85rem', color: '#94a3b8', minWidth: 140 }}>Run preference</div>
          <select
            value={form.run_mode}
            onChange={(e) => setForm((f) => ({ ...f, run_mode: e.target.value }))}
            style={{ padding: '0.45rem', borderRadius: 6, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
          >
            <option value="max_possible">Run as long as possible</option>
            <option value="preferred_times">Preferred times</option>
          </select>
          {form.run_mode === 'preferred_times' && (
            <>
              <ToggleSwitch checked={form.hard} onChange={(v) => setForm((f) => ({ ...f, hard: v }))} label="Only run in preferred windows (hard)" />
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, windows: [...f.windows, { start: '17:00', end: '21:00' }] }))}
                style={{ padding: '0.35rem 0.6rem', borderRadius: 6, background: '#334155', border: 'none', color: '#e2e8f0' }}
              >
                + Window
              </button>
            </>
          )}
        </div>
        {form.run_mode === 'preferred_times' && (
          <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            {form.windows.map((w, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type="time"
                  value={w.start}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      windows: f.windows.map((x, idx) => (idx === i ? { ...x, start: e.target.value } : x)),
                    }))
                  }
                  style={{ padding: '0.35rem', borderRadius: 6, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                />
                <span style={{ color: '#64748b' }}>to</span>
                <input
                  type="time"
                  value={w.end}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      windows: f.windows.map((x, idx) => (idx === i ? { ...x, end: e.target.value } : x)),
                    }))
                  }
                  style={{ padding: '0.35rem', borderRadius: 6, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                />
                {form.windows.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, windows: f.windows.filter((_, idx) => idx !== i) }))}
                    style={{ padding: '0.25rem 0.45rem', borderRadius: 6, background: '#7f1d1d', border: 'none', color: '#fecaca' }}
                    title="Remove window"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <p style={{ marginTop: 10, marginBottom: 0, color: '#64748b', fontSize: '0.8rem' }}>
          IEBA will prioritize running appliances inside preferred windows (soft), or forbid running outside them (hard).
        </p>
      </div>

      {list.length > 0 && (
        <section style={{ marginTop: '1.5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
            <HorizontalBarChart items={charts.byPriority} title="Total rated power by priority (W)" unit=" W" />
          </div>
          {charts.topRated.length > 0 && (
            <div style={{ background: '#1e293b', padding: '1rem', borderRadius: 8 }}>
              <HorizontalBarChart items={charts.topRated} title="Top appliances by rated power (W)" unit=" W" />
            </div>
          )}
        </section>
      )}

      <h2 style={{ marginTop: '2rem' }}>Registered appliances</h2>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #334155' }}>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>ID</th>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>Name</th>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>Priority</th>
            <th style={{ textAlign: 'right', padding: '0.5rem' }}>Rated (W)</th>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>Mode</th>
            <th style={{ textAlign: 'left', padding: '0.5rem' }}>Run preference</th>
            <th style={{ textAlign: 'right', padding: '0.5rem' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {list.map((a) => (
            <tr key={a.id} style={{ borderBottom: '1px solid #334155' }}>
              <td style={{ padding: '0.5rem' }}>{a.external_id}</td>
              <td style={{ padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <input
                    value={editForm.name}
                    onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                    style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                  />
                ) : (
                  a.name
                )}
              </td>
              {/* Preferences shown in edit row only for brevity */}
              <td style={{ padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <select
                    value={editForm.priority}
                    onChange={(e) => setEditForm((f) => ({ ...f, priority: Number(e.target.value) }))}
                    style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                  >
                    <option value={1}>Priority 1 – Critical</option>
                    <option value={2}>Priority 2 – Essential</option>
                    <option value={3}>Priority 3 – Non-essential</option>
                  </select>
                ) : (
                  priorityLabel(a.priority)
                )}
              </td>
              <td style={{ textAlign: 'right', padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <input
                    type="number"
                    value={editForm.rated_watts}
                    onChange={(e) => setEditForm((f) => ({ ...f, rated_watts: Number(e.target.value) || 0 }))}
                    style={{ width: 90, padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                  />
                ) : (
                  a.rated_watts
                )}
              </td>
              <td style={{ padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <select
                      value={editForm.usage_mode}
                      onChange={(e) => setEditForm((f) => ({ ...f, usage_mode: e.target.value }))}
                      style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                    >
                      <option value="scheduled">Scheduled</option>
                      <option value="on_demand">On-demand</option>
                    </select>
                    <input
                      type="number"
                      value={editForm.default_run_minutes}
                      min={5}
                      onChange={(e) => setEditForm((f) => ({ ...f, default_run_minutes: Number(e.target.value) || 30 }))}
                      style={{ width: 120, padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                    />
                  </div>
                ) : (
                  <span style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>
                    {usageModeLabel(a.usage_mode)}{a.usage_mode === 'on_demand' ? ` (${a.default_run_minutes || 30} min)` : ''}
                  </span>
                )}
              </td>
              <td style={{ padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
                    <select
                      value={editForm.run_mode}
                      onChange={(e) => setEditForm((f) => ({ ...f, run_mode: e.target.value }))}
                      style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                    >
                      <option value="max_possible">Run as long as possible</option>
                      <option value="preferred_times">Preferred times</option>
                    </select>
                    {editForm.usage_mode === 'scheduled' && editForm.run_mode === 'preferred_times' && (
                      <>
                        <ToggleSwitch checked={editForm.hard} onChange={(v) => setEditForm((f) => ({ ...f, hard: v }))} label="Hard (only within windows)" />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {editForm.windows.map((w, i) => (
                            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                              <input
                                type="time"
                                value={w.start}
                                onChange={(e) =>
                                  setEditForm((f) => ({
                                    ...f,
                                    windows: f.windows.map((x, idx) => (idx === i ? { ...x, start: e.target.value } : x)),
                                  }))
                                }
                                style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                              />
                              <span style={{ color: '#64748b' }}>to</span>
                              <input
                                type="time"
                                value={w.end}
                                onChange={(e) =>
                                  setEditForm((f) => ({
                                    ...f,
                                    windows: f.windows.map((x, idx) => (idx === i ? { ...x, end: e.target.value } : x)),
                                  }))
                                }
                                style={{ padding: '0.25rem', borderRadius: 4, border: '1px solid #475569', background: '#0f172a', color: '#e2e8f0' }}
                              />
                              {editForm.windows.length > 1 && (
                                <button
                                  type="button"
                                  onClick={() => setEditForm((f) => ({ ...f, windows: f.windows.filter((_, idx) => idx !== i) }))}
                                  style={{ padding: '0.2rem 0.4rem', borderRadius: 6, background: '#7f1d1d', border: 'none', color: '#fecaca' }}
                                  title="Remove window"
                                >
                                  ×
                                </button>
                              )}
                            </div>
                          ))}
                          <button
                            type="button"
                            onClick={() => setEditForm((f) => ({ ...f, windows: [...f.windows, { start: '17:00', end: '21:00' }] }))}
                            style={{ padding: '0.25rem 0.5rem', borderRadius: 6, background: '#334155', border: 'none', color: '#e2e8f0' }}
                          >
                            + Window
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <span style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>
                    {a.usage_mode === 'on_demand' ? 'Manual request when needed' : prefSummary(a.schedule_prefs)}
                  </span>
                )}
              </td>
              <td style={{ textAlign: 'right', padding: '0.5rem' }}>
                {editingId === a.id ? (
                  <>
                    <button
                      type="button"
                      onClick={() => saveEdit(a.id)}
                      style={{ marginRight: 6, padding: '0.25rem 0.5rem', borderRadius: 4, background: '#22c55e', color: '#0f172a', border: 'none', fontSize: '0.8rem' }}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={cancelEdit}
                      style={{ padding: '0.25rem 0.5rem', borderRadius: 4, background: '#334155', color: '#e2e8f0', border: 'none', fontSize: '0.8rem' }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    {a.usage_mode === 'on_demand' && (
                      <>
                        {QUICK_RUN_MINUTES.map((mins) => (
                          <button
                            key={mins}
                            type="button"
                            onClick={() => requestRunNow(a, mins)}
                            disabled={runRequestBusyId === a.id}
                            style={{
                              marginRight: 6,
                              marginBottom: 4,
                              padding: '0.25rem 0.5rem',
                              borderRadius: 4,
                              background: mins === (a.default_run_minutes || 30) ? '#9333ea' : '#a855f7',
                              color: '#f8fafc',
                              border: 'none',
                              fontSize: '0.8rem',
                            }}
                          >
                            {runRequestBusyId === a.id ? 'Checking…' : `${mins}m`}
                          </button>
                        ))}
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => startEdit(a)}
                      style={{ marginRight: 6, padding: '0.25rem 0.5rem', borderRadius: 4, background: '#0ea5e9', color: '#0f172a', border: 'none', fontSize: '0.8rem' }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteAppliance(a.id)}
                      style={{ padding: '0.25rem 0.5rem', borderRadius: 4, background: '#ef4444', color: '#0f172a', border: 'none', fontSize: '0.8rem' }}
                    >
                      Delete
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.length === 0 && <p style={{ color: '#94a3b8' }}>No appliances yet. Add one above or rely on simulator defaults.</p>}
    </div>
  )
}
