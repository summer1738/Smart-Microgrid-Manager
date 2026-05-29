const severityStyles = {
  critical: {
    border: '#ef4444',
    glow: 'rgba(239, 68, 68, 0.16)',
    chipBg: 'rgba(239, 68, 68, 0.18)',
    chipColor: '#fecaca',
  },
  warning: {
    border: '#f59e0b',
    glow: 'rgba(245, 158, 11, 0.14)',
    chipBg: 'rgba(245, 158, 11, 0.16)',
    chipColor: '#fde68a',
  },
  success: {
    border: '#22c55e',
    glow: 'rgba(34, 197, 94, 0.14)',
    chipBg: 'rgba(34, 197, 94, 0.16)',
    chipColor: '#bbf7d0',
  },
  info: {
    border: '#38bdf8',
    glow: 'rgba(56, 189, 248, 0.14)',
    chipBg: 'rgba(56, 189, 248, 0.16)',
    chipColor: '#bae6fd',
  },
}

function prettyLabel(value) {
  if (!value) return ''
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function InsightPanel({ title = 'AI insights', summary, insights = [], footnote }) {
  if (!summary && !insights.length) return null

  return (
    <section
      style={{
        marginTop: '1.5rem',
        padding: '1.1rem',
        borderRadius: 14,
        background:
          'linear-gradient(145deg, rgba(15,23,42,0.98), rgba(20,33,61,0.92) 55%, rgba(13,20,35,0.98))',
        border: '1px solid rgba(56, 189, 248, 0.18)',
        boxShadow: '0 16px 40px rgba(2, 6, 23, 0.28)',
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '0.75rem' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>{title}</h2>
        <span style={{ fontSize: '0.75rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#7dd3fc' }}>
          Descriptive layer
        </span>
      </div>

      {summary && (
        <p
          style={{
            marginTop: '0.85rem',
            marginBottom: 0,
            color: '#e2e8f0',
            lineHeight: 1.6,
            fontSize: '0.95rem',
            maxWidth: 920,
          }}
        >
          {summary}
        </p>
      )}

      {insights.length > 0 && (
        <div
          style={{
            marginTop: '1rem',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '0.9rem',
          }}
        >
          {insights.map((insight, idx) => {
            const palette = severityStyles[insight.severity] || severityStyles.info
            return (
              <article
                key={`${insight.category}-${idx}`}
                style={{
                  padding: '0.95rem',
                  borderRadius: 12,
                  border: `1px solid ${palette.border}`,
                  background: `linear-gradient(180deg, ${palette.glow}, rgba(15, 23, 42, 0.88) 55%)`,
                }}
              >
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', alignItems: 'center' }}>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      padding: '0.18rem 0.42rem',
                      borderRadius: 999,
                      background: palette.chipBg,
                      color: palette.chipColor,
                    }}
                  >
                    {prettyLabel(insight.severity)}
                  </span>
                  <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>{prettyLabel(insight.category)}</span>
                </div>

                <h3 style={{ marginTop: '0.7rem', marginBottom: '0.45rem', fontSize: '0.95rem' }}>{insight.title}</h3>
                <p style={{ margin: 0, color: '#cbd5e1', fontSize: '0.88rem', lineHeight: 1.55 }}>{insight.message}</p>

                {insight.recommendation && (
                  <p style={{ marginTop: '0.7rem', marginBottom: 0, color: '#f8fafc', fontSize: '0.84rem', lineHeight: 1.5 }}>
                    <strong style={{ color: '#7dd3fc' }}>Recommended action:</strong> {insight.recommendation}
                  </p>
                )}

                {insight.evidence?.length > 0 && (
                  <div style={{ marginTop: '0.8rem', display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
                    {insight.evidence.map((item, evidenceIdx) => (
                      <span
                        key={`${item.label}-${evidenceIdx}`}
                        style={{
                          fontSize: '0.74rem',
                          color: '#cbd5e1',
                          background: 'rgba(15, 23, 42, 0.62)',
                          border: '1px solid rgba(148, 163, 184, 0.18)',
                          borderRadius: 999,
                          padding: '0.22rem 0.48rem',
                        }}
                      >
                        <strong style={{ color: '#f8fafc' }}>{item.label}:</strong> {item.value}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}

      {footnote && <p style={{ marginTop: '0.9rem', marginBottom: 0, color: '#64748b', fontSize: '0.78rem' }}>{footnote}</p>}
    </section>
  )
}
