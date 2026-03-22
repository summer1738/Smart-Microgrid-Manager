import { useState, useEffect, useMemo } from 'react'
import { HorizontalBarChart } from '../components/Charts'

export default function Appliances({ api }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({ name: '', priority: 2, rated_watts: 100 })
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', priority: 2, rated_watts: 100 })

  const fetchList = async () => {
    try {
      const r = await fetch(`${api}/appliances`)
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
      const r = await fetch(`${api}/appliances`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        throw new Error(err.detail || r.statusText)
      }
      setForm({ name: '', priority: 2, rated_watts: 100 })
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
    setEditForm({ name: a.name, priority: a.priority, rated_watts: a.rated_watts })
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  const saveEdit = async (id) => {
    try {
      const r = await fetch(`${api}/appliances/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
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

  const deleteAppliance = async (id) => {
    if (!window.confirm('Delete this appliance?')) return
    try {
      const r = await fetch(`${api}/appliances/${id}`, { method: 'DELETE' })
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
        <button type="submit" disabled={saving} style={{ padding: '0.5rem 1rem', borderRadius: 6, background: '#0ea5e9', color: '#0f172a', border: 'none', fontWeight: 600 }}>
          {saving ? 'Adding…' : 'Add appliance'}
        </button>
      </form>

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
