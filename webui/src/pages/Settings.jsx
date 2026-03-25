import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAppSettings } from '../context/AppSettingsContext'

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

export default function Settings({ api }) {
  const { settings, setSettings } = useAppSettings()
  const [serverAutoTrain, setServerAutoTrain] = useState(null)
  const [serverWeatherEnabled, setServerWeatherEnabled] = useState(null)
  const [serverLat, setServerLat] = useState('')
  const [serverLon, setServerLon] = useState('')
  const [serverPvKw, setServerPvKw] = useState('')
  const [serverDerate, setServerDerate] = useState('')
  const [serverLoading, setServerLoading] = useState(true)
  const [serverError, setServerError] = useState(null)
  const [serverSaving, setServerSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    setServerLoading(true)
    setServerError(null)
    fetch(`${api}/system/settings`)
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText)
        return r.json()
      })
      .then((d) => {
        if (cancelled) return
        setServerAutoTrain(!!d.auto_train_enabled)
        setServerWeatherEnabled(!!d.weather_forecast_enabled)
        setServerLat(String(d.weather_latitude ?? ''))
        setServerLon(String(d.weather_longitude ?? ''))
        setServerPvKw(String(d.weather_pv_capacity_kw ?? ''))
        setServerDerate(String(d.weather_panel_derate ?? ''))
      })
      .catch((e) => {
        if (!cancelled) setServerError(e.message || 'Failed to load server settings')
      })
      .finally(() => {
        if (!cancelled) setServerLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  const setAutoTrain = async (enabled) => {
    setServerSaving(true)
    setServerError(null)
    try {
      const r = await fetch(`${api}/system/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_train_enabled: enabled }),
      })
      if (!r.ok) throw new Error(await r.text())
      const d = await r.json()
      setServerAutoTrain(!!d.auto_train_enabled)
    } catch (e) {
      setServerError(e.message || 'Save failed')
    } finally {
      setServerSaving(false)
    }
  }

  const saveWeatherSettings = async () => {
    setServerSaving(true)
    setServerError(null)
    try {
      const payload = {
        auto_train_enabled: !!serverAutoTrain,
        weather_forecast_enabled: !!serverWeatherEnabled,
        weather_latitude: Number(serverLat),
        weather_longitude: Number(serverLon),
        weather_pv_capacity_kw: Number(serverPvKw),
        weather_panel_derate: Number(serverDerate),
      }
      const r = await fetch(`${api}/system/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())
      const d = await r.json()
      setServerAutoTrain(!!d.auto_train_enabled)
      setServerWeatherEnabled(!!d.weather_forecast_enabled)
      setServerLat(String(d.weather_latitude ?? ''))
      setServerLon(String(d.weather_longitude ?? ''))
      setServerPvKw(String(d.weather_pv_capacity_kw ?? ''))
      setServerDerate(String(d.weather_panel_derate ?? ''))
    } catch (e) {
      setServerError(e.message || 'Save failed')
    } finally {
      setServerSaving(false)
    }
  }

  return (
    <div>
      <p style={{ marginBottom: '1rem' }}>
        <Link to="/">← Back to dashboard</Link>
      </p>
      <h1>Settings</h1>

      <section
        style={{
          marginTop: '1.5rem',
          background: '#1e293b',
          padding: '1rem 1.25rem',
          borderRadius: 8,
          maxWidth: 560,
        }}
      >
        <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>Server (scheduled)</h2>

        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            cursor: serverSaving ? 'wait' : 'pointer',
            opacity: serverSaving ? 0.7 : 1,
          }}
        >
          <ToggleSwitch
            checked={serverAutoTrain === true}
            disabled={serverSaving || serverLoading}
            onChange={(val) => setAutoTrain(val)}
          />
          <span>
            <strong>Enable automatic LSTM training</strong>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: 6, lineHeight: 1.45 }}>
              When on, the backend periodically exports readings and retrains models (export → dataset prep → training).
            </div>
          </span>
        </label>

        {serverLoading && <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: 10 }}>Loading server settings…</p>}
        {serverError && <p style={{ color: '#f87171', fontSize: '0.9rem', marginTop: 10 }}>{serverError}</p>}
      </section>

      <section
        style={{
          marginTop: '1.5rem',
          background: '#1e293b',
          padding: '1rem 1.25rem',
          borderRadius: 8,
          maxWidth: 560,
        }}
      >
        <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>System location (weather)</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: 0 }}>
          Used by Weather &amp; PV and expected PV forecasts. These are saved in SQLite (system settings).
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <Field label="Latitude" value={serverLat} onChange={setServerLat} placeholder="-17.8" disabled={serverLoading || serverSaving} />
          <Field label="Longitude" value={serverLon} onChange={setServerLon} placeholder="31.05" disabled={serverLoading || serverSaving} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <Field label="PV nameplate (kW)" value={serverPvKw} onChange={setServerPvKw} placeholder="1.0" disabled={serverLoading || serverSaving} />
          <Field label="Derate (0–1)" value={serverDerate} onChange={setServerDerate} placeholder="0.85" disabled={serverLoading || serverSaving} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
          <ToggleSwitch
            checked={serverWeatherEnabled === true}
            disabled={serverLoading || serverSaving}
            onChange={(val) => setServerWeatherEnabled(val)}
          />
          <span style={{ color: '#e2e8f0' }}>Enable Open-Meteo weather forecast</span>
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 14 }}>
          <button
            type="button"
            onClick={saveWeatherSettings}
            disabled={serverLoading || serverSaving}
            style={{
              padding: '0.55rem 1rem',
              background: serverLoading || serverSaving ? '#334155' : '#0ea5e9',
              border: 'none',
              borderRadius: 8,
              color: serverLoading || serverSaving ? '#94a3b8' : '#0b1220',
              fontWeight: 700,
              cursor: serverLoading || serverSaving ? 'not-allowed' : 'pointer',
            }}
          >
            {serverSaving ? 'Saving…' : 'Save weather settings'}
          </button>
        </div>
      </section>

      <section
        style={{
          marginTop: '1.5rem',
          background: '#1e293b',
          padding: '1rem 1.25rem',
          borderRadius: 8,
          maxWidth: 560,
        }}
      >
        <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>This browser</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: 520, marginBottom: '1rem' }}>
          UI preferences are stored in localStorage on this device only.
        </p>
        <label
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            cursor: 'pointer',
          }}
        >
          <ToggleSwitch
            checked={settings.showHoverColorInterpretations}
            onChange={(val) => setSettings({ showHoverColorInterpretations: val })}
          />
          <span>
            <strong>Show hover color interpretations</strong>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: 6, lineHeight: 1.45 }}>
              MQTT status colors and load-bar tooltips on the dashboard. Turn off for a cleaner UI.
            </div>
          </span>
        </label>
      </section>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, disabled }) {
  return (
    <label style={{ display: 'block' }}>
      <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: 6 }}>{label}</div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{
          width: '100%',
          padding: '0.55rem 0.7rem',
          borderRadius: 8,
          border: '1px solid #334155',
          background: '#0f172a',
          color: '#e2e8f0',
        }}
      />
    </label>
  )
}
