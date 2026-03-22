import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Appliances from './pages/Appliances'
import Forecast from './pages/Forecast'
import Schedule from './pages/Schedule'
import ModelMonitor from './pages/ModelMonitor'

const API = '/api'

function Nav() {
  return (
    <nav style={{ padding: '1rem 1.5rem', borderBottom: '1px solid #334155', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '1.5rem' }}>
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
      <Link to="/">Dashboard</Link>
      <Link to="/appliances">Appliances</Link>
      <Link to="/forecast">Forecast</Link>
      <Link to="/schedule">Schedule</Link>
      <Link to="/model-monitor">Model monitor</Link>
    </nav>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main style={{ padding: '1.5rem', maxWidth: 1200, margin: '0 auto' }}>
        <Routes>
          <Route path="/" element={<Dashboard api={API} />} />
          <Route path="/appliances" element={<Appliances api={API} />} />
          <Route path="/forecast" element={<Forecast api={API} />} />
          <Route path="/schedule" element={<Schedule api={API} />} />
          <Route path="/model-monitor" element={<ModelMonitor api={API} />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export { API }
