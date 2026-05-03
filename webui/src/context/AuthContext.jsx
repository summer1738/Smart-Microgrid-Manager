import { createContext, useCallback, useContext, useMemo, useState, useEffect } from 'react'
import { apiFetch } from '../utils/api'

const AuthContext = createContext(null)

function parseAuthError(data, fallbackMessage) {
  return data?.detail || data?.message || fallbackMessage
}

export function AuthProvider({ api, children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)

  const refreshValidation = useCallback(async () => {
    try {
      const response = await apiFetch(`${api}/auth/me`)
      if (response.status === 401) {
        setUser(null)
        return
      }
      if (!response.ok) throw new Error(response.statusText)
      const found = await response.json()
      setUser(found ? { id: found.id, name: found.name, username: found.username, role: found.role } : null)
    } catch {
      setUser(null)
    } finally {
      setReady(true)
    }
  }, [api])

  useEffect(() => {
    refreshValidation()
  }, [refreshValidation])

  const login = useCallback(async ({ username, password }) => {
    const response = await apiFetch(`${api}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(parseAuthError(data, response.statusText || 'Login failed'))
    }
    const found = data?.user
    if (!found) throw new Error('Login response did not include a user session')
    setUser({ id: found.id, name: found.name, username: found.username, role: found.role })
    return found
  }, [api])

  const signup = useCallback(async ({ name, username, password }) => {
    const response = await apiFetch(`${api}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, username, password }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(parseAuthError(data, response.statusText || 'Registration failed'))
    }
    const found = data?.user
    if (!found) throw new Error('Signup response did not include a user session')
    setUser({ id: found.id, name: found.name, username: found.username, role: found.role })
    return found
  }, [api])

  const logout = useCallback(async () => {
    try {
      await apiFetch(`${api}/auth/logout`, { method: 'POST' })
    } catch {
      /* ignore */
    } finally {
      setUser(null)
    }
  }, [api])

  const value = useMemo(
    () => ({ user, ready, login, signup, logout, refreshValidation }),
    [user, ready, login, signup, logout, refreshValidation],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
