import { Navigate } from 'react-router-dom'
import { roleMeetsMin } from '../auth/roles'
import { useAuth } from '../context/AuthContext'

export default function RequireRole({ minRole, children }) {
  const { user, ready } = useAuth()
  if (!ready) {
    return <p style={{ color: '#94a3b8', padding: '1.5rem' }}>Loading session…</p>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (!roleMeetsMin(user.role, minRole)) {
    return <Navigate to="/" replace />
  }
  return children
}
