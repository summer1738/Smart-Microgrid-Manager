import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAppSettings } from '../context/AppSettingsContext'
import { getMqttBadge } from '../utils/mqttStatus'
import { MqttStatusTooltip } from './MqttStatusTooltip'

const API = '/api'

export default function MqttNavIndicator() {
  const { settings } = useAppSettings()
  const showColorHover = settings.showHoverColorInterpretations
  const [mqttHealth, setMqttHealth] = useState(null)
  const [hover, setHover] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function fetchHealth() {
      try {
        const r = await fetch(`${API}/health/mqtt`)
        if (!r.ok) throw new Error('bad status')
        const data = await r.json()
        if (!cancelled) setMqttHealth(data)
      } catch {
        if (!cancelled) setMqttHealth(null)
      }
    }
    fetchHealth()
    const id = setInterval(fetchHealth, 15000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const badge = mqttHealth ? getMqttBadge(mqttHealth) : null
  const color = badge?.color ?? '#64748b'
  const label = badge?.label ?? 'MQTT: …'
  const shortLabel = badge ? label.replace(/^MQTT:\s*/i, '') : 'offline'

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
      onMouseEnter={() => showColorHover && setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <Link
        to="/"
        title={showColorHover ? undefined : badge ? `${label}. ${badge.details}` : 'Could not load MQTT status (is the backend running?)'}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '0.25rem 0.6rem',
          borderRadius: 999,
          border: `1px solid ${color}`,
          background: '#1e293b',
          fontSize: '0.75rem',
          color: '#cbd5e1',
          textDecoration: 'none',
          cursor: showColorHover ? 'help' : 'pointer',
        }}
      >
        <span
          title={showColorHover && badge ? `Status: ${badge.thisColorMeans}` : undefined}
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: color,
            flexShrink: 0,
          }}
        />
        <span style={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{shortLabel}</span>
      </Link>
      {showColorHover && hover && badge && <MqttStatusTooltip mqttBadge={badge} compact />}
      {!badge && showColorHover && hover && (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            right: 0,
            top: '100%',
            marginTop: 8,
            zIndex: 50,
            width: 'min(280px, calc(100vw - 2rem))',
            padding: '0.6rem 0.85rem',
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: 8,
            fontSize: '0.75rem',
            color: '#94a3b8',
          }}
        >
          Could not load <code style={{ color: '#e2e8f0' }}>/health/mqtt</code>. Start the backend or check the Vite proxy.
        </div>
      )}
    </div>
  )
}
