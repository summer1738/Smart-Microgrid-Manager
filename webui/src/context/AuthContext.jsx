import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const AuthContext = createContext(null)

function parseAuthError(data, fallbackMessage) {
  return data?.detail || data?.message || fallbackMessage
}

export function AuthProvider({ api, children }) {
  const [user, setUserState] = useState(null)
  const [ready, setReady] = useState(false)

  const refreshValidation = useCallback(async () => {
    try {
      const r = await fetch(`${api}/auth/me`, { credentials: 'include' })
      if (r.status === 401) {
        setUserState(null)
        return
      }
      if (!r.ok) throw new Error(r.statusText)
      const found = await r.json()
      setUserState(found ? { id: found.id, name: found.name, username: found.username, role: found.role } : null)
    } catch {
      setUserState(null)
    } finally {
      setReady(true)
    }
  }, [api])

  useEffect(() => {
    refreshValidation()
  }, [refreshValidation])

  const login = useCallback(async ({ username, password }) => {
    const r = await fetch(`${api}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) {
      throw new Error(parseAuthError(data, r.statusText || 'Login failed'))
    }
    const u = data?.user
    if (!u) throw new Error('Login response did not include a user session')
    setUserState({ id: u.id, name: u.name, username: u.username, role: u.role })
    return u
  }, [api])

  const signup = useCallback(async ({ name, username, password }) => {
    const r = await fetch(`${api}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ name, username, password }),
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) {
      throw new Error(parseAuthError(data, r.statusText || 'Registration failed'))
    }
    const u = data?.user
    if (!u) throw new Error('Signup response did not include a user session')
    setUserState({ id: u.id, name: u.name, username: u.username, role: u.role })
    return u
  }, [api])

  const logout = useCallback(async () => {
    try {
      await fetch(`${api}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      /* ignore */
    } finally {
      setUserState(null)
    }
  }, [api])

  const value = useMemo(
    () => ({ user, login, signup, logout, ready, refreshValidation }),
    [user, login, signup, logout, ready, refreshValidation],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
