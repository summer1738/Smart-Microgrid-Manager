import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const ROLE_HELP = {
  viewer: 'Dashboard, weather, and forecast — read-focused.',
  operator: 'Adds appliances, schedule, and hardware monitoring.',
  admin: 'Full access including settings, training, and model tools.',
}

export default function Login({ api }) {
  const { user, setUser, ready } = useAuth()
  const [users, setUsers] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const r = await fetch(`${api}/users`)
        if (!r.ok) throw new Error(r.statusText)
        const list = await r.json()
        if (!cancelled && Array.isArray(list)) {
          setUsers(list)
          if (list.length && !selectedId) {
            setSelectedId(String(list[0].id))
          }
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Could not load users')
      }
    }
    if (ready && !user) load()
    return () => {
      cancelled = true
    }
  }, [api, ready, user, selectedId])

  if (ready && user) {
    return <Navigate to="/" replace />
  }

  const onSubmit = (e) => {
    e.preventDefault()
    const id = Number(selectedId)
    const u = users.find((x) => x.id === id)
    if (!u) return
    setUser(u)
    navigate('/', { replace: true })
  }

  return (
    <div style={{ maxWidth: 420, margin: '3rem auto', padding: '0 1rem' }}>
      <h1 style={{ fontSize: '1.35rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>Sign in</h1>
      <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '1.25rem', lineHeight: 1.5 }}>
        Choose a role to open the matching screens. This is a demo gate (no password); add real authentication before
        production.
      </p>
      {error && <p style={{ color: '#f87171', marginBottom: '1rem' }}>{error}</p>}
      <form
        onSubmit={onSubmit}
        style={{ background: '#1e293b', padding: '1.25rem', borderRadius: 8, border: '1px solid #334155' }}
      >
        <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: 6 }}>User</label>
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          style={{
            width: '100%',
            padding: '0.6rem 0.5rem',
            borderRadius: 6,
            border: '1px solid #475569',
            background: '#0f172a',
            color: '#e2e8f0',
            marginBottom: '1rem',
          }}
        >
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name} ({u.role})
            </option>
          ))}
        </select>
        {selectedId && (
          <p style={{ fontSize: '0.82rem', color: '#64748b', marginTop: -8, marginBottom: '1rem', lineHeight: 1.45 }}>
            {ROLE_HELP[users.find((x) => String(x.id) === selectedId)?.role] || ''}
          </p>
        )}
        <button
          type="submit"
          disabled={!users.length}
          style={{
            width: '100%',
            padding: '0.65rem',
            borderRadius: 6,
            border: 'none',
            background: users.length ? '#0ea5e9' : '#475569',
            color: '#0f172a',
            fontWeight: 600,
            cursor: users.length ? 'pointer' : 'not-allowed',
          }}
        >
          Continue
        </button>
      </form>
    </div>
  )
}
