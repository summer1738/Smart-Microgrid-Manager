/**
 * Shows actionable issues from GET /health/mqtt → sensor_pipeline.issues
 * when live ESP32 sensor data is blocked or missing.
 */
export default function SensorPipelineAlert({ pipeline, title = 'Live sensors' }) {
  const issues = pipeline?.issues
  if (!issues?.length) return null

  return (
    <div
      style={{
        marginBottom: '1rem',
        padding: '0.85rem 1rem',
        borderRadius: 8,
        border: '1px solid #b45309',
        background: '#422006',
        color: '#fef3c7',
        fontSize: '0.9rem',
      }}
      role="status"
    >
      <div style={{ fontWeight: 700, marginBottom: '0.5rem', color: '#fde68a' }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: '1.25rem', lineHeight: 1.55 }}>
        {issues.map((issue) => (
          <li key={issue.code} style={{ marginBottom: '0.5rem' }}>
            <span style={{ color: issue.severity === 'error' ? '#fecaca' : '#fde68a' }}>{issue.message}</span>
            {issue.fix && (
              <div
                style={{
                  marginTop: 6,
                  color: '#cbd5e1',
                  fontSize: '0.85rem',
                  whiteSpace: 'pre-line',
                  lineHeight: 1.5,
                }}
              >
                <strong style={{ color: '#94a3b8' }}>Fix:</strong>
                {'\n'}
                {issue.fix}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
