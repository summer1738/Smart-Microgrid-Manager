import { MQTT_COLOR_GUIDE } from '../utils/mqttStatus'

/**
 * Hover panel: current color meaning + full color guide.
 * @param {{ compact?: boolean, mqttBadge: object }} props
 */
export function MqttStatusTooltip({ mqttBadge, compact = false }) {
  return (
    <div
      role="tooltip"
      style={{
        position: 'absolute',
        right: compact ? 0 : undefined,
        left: compact ? undefined : 0,
        top: '100%',
        marginTop: 8,
        zIndex: 50,
        width: compact ? 'min(300px, calc(100vw - 2rem))' : 'min(340px, calc(100vw - 3rem))',
        padding: '0.75rem 1rem',
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 8,
        boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
        fontSize: '0.8rem',
        lineHeight: 1.45,
        color: '#e2e8f0',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6, color: '#f1f5f9' }}>This color</div>
      <p style={{ margin: '0 0 0.75rem' }}>{mqttBadge.thisColorMeans}</p>
      <p style={{ margin: '0 0 0.5rem', color: '#94a3b8', fontSize: '0.75rem' }}>{mqttBadge.details}</p>
      <div style={{ fontWeight: 700, marginTop: 10, marginBottom: 6, color: '#f1f5f9' }}>Color guide</div>
      <ul style={{ margin: 0, paddingLeft: 18, color: '#cbd5e1' }}>
        {MQTT_COLOR_GUIDE.map((row) => (
          <li key={row.name} style={{ marginBottom: 6 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: row.swatch,
                  flexShrink: 0,
                }}
              />
              <strong style={{ color: '#f1f5f9' }}>{row.name}</strong>
            </span>
            {' — '}
            {row.text}
          </li>
        ))}
      </ul>
    </div>
  )
}
