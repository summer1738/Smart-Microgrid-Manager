import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'smart-microgrid-user-v1'

const AuthContext = createContext(null)

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const u = JSON.parse(raw)
    if (u && typeof u.id === 'number' && typeof u.role === 'string' && typeof u.name === 'string') {
      return u
    }
  } catch {
    /* ignore */
  }
  return null
}

export function AuthProvider({ api, children }) {
  const [user, setUserState] = useState(() => loadStoredUser())
  const [ready, setReady] = useState(false)

  const refreshValidation = useCallback(async () => {
    const stored = loadStoredUser()
    if (!stored) {
      setUserState(null)
      setReady(true)
      return
    }
    try {
      const r = await fetch(`${api}/users`)
      if (!r.ok) throw new Error(r.statusText)
      const list = await r.json()
      const found = Array.isArray(list) ? list.find((u) => u.id === stored.id) : null
      if (found && found.role === stored.role) {
        setUserState({ id: found.id, name: found.name, role: found.role })
      } else {
        localStorage.removeItem(STORAGE_KEY)
        setUserState(null)
      }
    } catch {
      setUserState(stored)
    } finally {
      setReady(true)
    }
  }, [api])

  useEffect(() => {
    refreshValidation()
  }, [refreshValidation])

  const setUser = useCallback((u) => {
    if (u) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: u.id, name: u.name, role: u.role }))
      } catch {
        /* ignore */
      }
      setUserState({ id: u.id, name: u.name, role: u.role })
    } else {
      localStorage.removeItem(STORAGE_KEY)
      setUserState(null)
    }
  }, [])

  const logout = useCallback(() => setUser(null), [setUser])

  const value = useMemo(
    () => ({ user, setUser, logout, ready, refreshValidation }),
    [user, setUser, logout, ready, refreshValidation],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
