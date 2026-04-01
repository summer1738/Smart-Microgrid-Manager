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
  const [serverInverterKw, setServerInverterKw] = useState('')
  const [serverBatteryKwh, setServerBatteryKwh] = useState('')
  const [serverSocMin, setServerSocMin] = useState('')
  const [serverPackagePreset, setServerPackagePreset] = useState('custom')
  const [serverLoading, setServerLoading] = useState(true)
  const [serverError, setServerError] = useState(null)
  const [serverSaving, setServerSaving] = useState(false)

  const PACKAGE_PRESETS = [
    {
      id: 'custom',
      label: 'Custom (manual)',
      sizing: null,
      weather: null,
    },
    // Residential presets (SolarPro Zimbabwe list)
    {
      id: 'res_2kva_basic',
      label: '2kVA Basic (lights, TV, small fridge, Wi‑Fi)',
      sizing: { inverter_capacity_kw: 2.0, battery_capacity_kwh: 2.4 },
      weather: { weather_pv_capacity_kw: 0.6 },
    },
    {
      id: 'res_3kva_advanced',
      label: '3kVA Advanced (adds booster pump / medium fridge)',
      sizing: { inverter_capacity_kw: 3.0, battery_capacity_kwh: 2.7 },
      weather: { weather_pv_capacity_kw: 0.88 }, // 2 × 440W
    },
    {
      id: 'res_5_6kva_standard',
      label: '5–6kVA Standard/Premium (family home, borehole pump)',
      sizing: { inverter_capacity_kw: 5.0, battery_capacity_kwh: 5.12 },
      weather: { weather_pv_capacity_kw: 2.64 }, // 6 × 440W (conservative)
    },
    {
      id: 'res_10kva_high_demand',
      label: '8–10kVA High Demand (large home, AC, 1hp+ pump)',
      sizing: { inverter_capacity_kw: 10.0, battery_capacity_kwh: 10.0 },
      weather: { weather_pv_capacity_kw: 5.28 }, // 12 × 440W
    },

    // Commercial presets (generic defaults; edit as needed per client/site survey)
    {
      id: 'com_5kva_shop',
      label: 'Commercial: 5kVA Small shop/office (POS, lights, Wi‑Fi, fridge)',
      sizing: { inverter_capacity_kw: 5.0, battery_capacity_kwh: 5.12 },
      weather: { weather_pv_capacity_kw: 3.3 }, // ~6 × 550W
    },
    {
      id: 'com_10kva_sme',
      label: 'Commercial: 10kVA SME (multiple fridges/freezers, printers, CCTV)',
      sizing: { inverter_capacity_kw: 10.0, battery_capacity_kwh: 10.24 },
      weather: { weather_pv_capacity_kw: 6.6 }, // ~12 × 550W
    },
    {
      id: 'com_15kva_premium',
      label: 'Commercial: 15kVA Premium (heavier daytime loads, workshop equipment)',
      sizing: { inverter_capacity_kw: 15.0, battery_capacity_kwh: 15.36 },
      weather: { weather_pv_capacity_kw: 9.9 }, // ~18 × 550W
    },
    {
      id: 'com_20kva_high_demand',
      label: 'Commercial: 20kVA High demand (large office / clinic / small lodge)',
      sizing: { inverter_capacity_kw: 20.0, battery_capacity_kwh: 20.48 },
      weather: { weather_pv_capacity_kw: 13.2 }, // ~24 × 550W
    },
  ]

  const applyPreset = (presetId) => {
    setServerPackagePreset(presetId)
    const p = PACKAGE_PRESETS.find((x) => x.id === presetId)
    if (!p || !p.sizing) return
    if (p.sizing.inverter_capacity_kw != null) setServerInverterKw(String(p.sizing.inverter_capacity_kw))
    if (p.sizing.battery_capacity_kwh != null) setServerBatteryKwh(String(p.sizing.battery_capacity_kwh))
    if (p.weather?.weather_pv_capacity_kw != null) setServerPvKw(String(p.weather.weather_pv_capacity_kw))
  }

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
        setServerInverterKw(String(d.inverter_capacity_kw ?? ''))
        setServerBatteryKwh(String(d.battery_capacity_kwh ?? ''))
        setServerSocMin(String(d.soc_min_percent ?? ''))
        setServerPackagePreset('custom')
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
        inverter_capacity_kw: Number(serverInverterKw),
        battery_capacity_kwh: Number(serverBatteryKwh),
        soc_min_percent: Number(serverSocMin),
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
      setServerInverterKw(String(d.inverter_capacity_kw ?? ''))
      setServerBatteryKwh(String(d.battery_capacity_kwh ?? ''))
      setServerSocMin(String(d.soc_min_percent ?? ''))
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
        <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>Microgrid system sizing</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: 0 }}>
          Used by IEBA to respect inverter limits and battery SOC constraints. Default inverter capacity is 3 kW.
        </p>
        <div style={{ marginTop: 10 }}>
          <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: 6 }}>Residential package preset</div>
          <select
            value={serverPackagePreset}
            onChange={(e) => applyPreset(e.target.value)}
            disabled={serverLoading || serverSaving}
            style={{
              width: '100%',
              padding: '0.55rem',
              borderRadius: 8,
              border: '1px solid #334155',
              background: '#0f172a',
              color: '#e2e8f0',
            }}
          >
            {PACKAGE_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: 6, lineHeight: 1.35 }}>
            Choosing a preset auto-fills inverter kW, battery kWh, and PV nameplate kW (still editable below).
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <Field
            label="Inverter capacity (kW)"
            value={serverInverterKw}
            onChange={setServerInverterKw}
            placeholder="5.0"
            disabled={serverLoading || serverSaving}
          />
          <Field
            label="Battery capacity (kWh)"
            value={serverBatteryKwh}
            onChange={setServerBatteryKwh}
            placeholder="5.0"
            disabled={serverLoading || serverSaving}
          />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <Field
            label="Minimum SOC (%)"
            value={serverSocMin}
            onChange={setServerSocMin}
            placeholder="40"
            disabled={serverLoading || serverSaving}
          />
          <div />
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
        <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: '0.75rem' }}>System location (weather)</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: 0 }}>
          Used by Weather &amp; PV and expected PV forecasts. These are saved in MySQL (`system_settings`).
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
            {serverSaving ? 'Saving…' : 'Save server settings'}
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
