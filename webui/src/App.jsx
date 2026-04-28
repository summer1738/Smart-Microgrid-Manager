import { BrowserRouter, Routes, Route, Link, Outlet, Navigate, useNavigate } from 'react-router-dom'
import { AppSettingsProvider } from './context/AppSettingsContext'
import { AuthProvider, useAuth } from './context/AuthContext'
import { roleMeetsMin } from './auth/roles'
import RequireRole from './components/RequireRole'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Dashboard from './pages/Dashboard'
import Appliances from './pages/Appliances'
import Forecast from './pages/Forecast'
import Schedule from './pages/Schedule'
import ModelMonitor from './pages/ModelMonitor'
import Settings from './pages/Settings'
import Training from './pages/Training'
import Weather from './pages/Weather'
import HardwareMonitor from './pages/HardwareMonitor'
import MqttNavIndicator from './components/MqttNavIndicator'

const API = '/api'

function Nav() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  if (!user) return null

  const linkStyle = { color: '#cbd5e1', textDecoration: 'none' }
  const onLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <nav
      style={{
        padding: '1rem 1.5rem',
        borderBottom: '1px solid #334155',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '1.5rem',
      }}
    >
      <Link
        to="/"
        style={{
          fontWeight: 700,
          fontSize: '1.05rem',
          color: '#f1f5f9',
          textDecoration: 'none',
          marginRight: 'auto',
        }}
      >
        Smart Microgrid Manager
      </Link>
      {roleMeetsMin(user.role, 'viewer') && (
        <Link to="/" style={linkStyle}>
          Dashboard
        </Link>
      )}
      {roleMeetsMin(user.role, 'operator') && (
        <Link to="/appliances" style={linkStyle}>
          Appliances
        </Link>
      )}
      {roleMeetsMin(user.role, 'operator') && (
        <Link to="/hardware" style={linkStyle}>
          Hardware
        </Link>
      )}
      {roleMeetsMin(user.role, 'viewer') && (
        <Link to="/forecast" style={linkStyle}>
          Forecast
        </Link>
      )}
      {roleMeetsMin(user.role, 'viewer') && (
        <Link to="/weather" style={linkStyle}>
          Weather &amp; PV
        </Link>
      )}
      {roleMeetsMin(user.role, 'operator') && (
        <Link to="/schedule" style={linkStyle}>
          Schedule
        </Link>
      )}
      {roleMeetsMin(user.role, 'admin') && (
        <Link to="/model-monitor" style={linkStyle}>
          Model monitor
        </Link>
      )}
      {roleMeetsMin(user.role, 'admin') && (
        <Link to="/training" style={linkStyle}>
          Training
        </Link>
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
          {user.name} · {user.role}
        </span>
        <MqttNavIndicator />
        {roleMeetsMin(user.role, 'admin') && (
          <Link to="/settings" style={linkStyle}>
            Settings
          </Link>
        )}
        <button
          type="button"
          onClick={onLogout}
          style={{
            padding: '0.35rem 0.65rem',
            borderRadius: 6,
            border: '1px solid #475569',
            background: '#0f172a',
            color: '#e2e8f0',
            cursor: 'pointer',
            fontSize: '0.85rem',
          }}
        >
          Sign out
        </button>
      </div>
    </nav>
  )
}

function AppShell() {
  const { user, ready } = useAuth()
  if (!ready) {
    return <p style={{ color: '#94a3b8', padding: '1.5rem' }}>Loading session…</p>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  return (
    <>
      <Nav />
      <main style={{ padding: '1.5rem', maxWidth: 1200, margin: '0 auto' }}>
        <Outlet />
      </main>
    </>
  )
}

export default function App() {
  return (
    <AppSettingsProvider>
      <AuthProvider api={API}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route element={<AppShell />}>
              <Route path="/" element={<RequireRole minRole="viewer"><Dashboard api={API} /></RequireRole>} />
              <Route
                path="/appliances"
                element={<RequireRole minRole="operator"><Appliances api={API} /></RequireRole>}
              />
              <Route
                path="/hardware"
                element={<RequireRole minRole="operator"><HardwareMonitor api={API} /></RequireRole>}
              />
              <Route path="/forecast" element={<RequireRole minRole="viewer"><Forecast api={API} /></RequireRole>} />
              <Route path="/weather" element={<RequireRole minRole="viewer"><Weather api={API} /></RequireRole>} />
              <Route path="/schedule" element={<RequireRole minRole="operator"><Schedule api={API} /></RequireRole>} />
              <Route path="/training" element={<RequireRole minRole="admin"><Training api={API} /></RequireRole>} />
              <Route
                path="/model-monitor"
                element={<RequireRole minRole="admin"><ModelMonitor api={API} /></RequireRole>}
              />
              <Route path="/settings" element={<RequireRole minRole="admin"><Settings api={API} /></RequireRole>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </AppSettingsProvider>
  )
}

export { API }
