/**
 * Lightweight SVG charts (no extra dependencies).
 */
import { useMemo, useState } from 'react'

const pad = 40
const bottomPad = 28

function fmt(value, digits = 2) {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : '0.00'
}

/** Multi-series line chart. series: [{ name, color, values: number[] }] — same length arrays. */
export function MultiLineChart({ series, labels, height = 200, title }) {
  const [hoverIdx, setHoverIdx] = useState(null)
  if (!series?.length || !series[0]?.values?.length) return null
  const n = series[0].values.length
  const w = Math.min(900, Math.max(320, n * 8))
  const h = height
  const innerW = w - pad - 12
  const innerH = h - pad - bottomPad

  const allVals = series.flatMap((s) => s.values)
  const minY = Math.min(0, ...allVals)
  const maxY = Math.max(0.001, ...allVals)
  const range = maxY - minY || 1

  const xAt = (i) => pad + (i / Math.max(1, n - 1)) * innerW
  const yAt = (v) => pad + innerH - ((v - minY) / range) * innerH
  const summary = useMemo(
    () =>
      series.map((s) => {
        const vals = s.values.filter((v) => Number.isFinite(v))
        const sum = vals.reduce((a, b) => a + b, 0)
        return {
          name: s.name,
          color: s.color,
          min: vals.length ? Math.min(...vals) : 0,
          max: vals.length ? Math.max(...vals) : 0,
          avg: vals.length ? sum / vals.length : 0,
        }
      }),
    [series]
  )

  return (
    <div style={{ marginTop: 12, overflowX: 'auto' }}>
      {title && <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: 6 }}>{title}</div>}
      <svg
        width={w}
        height={h}
        style={{ display: 'block', background: '#0f172a', borderRadius: 8 }}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="gridFade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#334155" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#334155" stopOpacity="0.1" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = pad + innerH * (1 - t)
          return <line key={t} x1={pad} y1={y} x2={w - 12} y2={y} stroke="#334155" strokeWidth="0.5" />
        })}
        {series.map((s, si) => {
          const d = s.values
            .map((v, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)}`)
            .join(' ')
          return (
            <path key={si} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />
          )
        })}
        {hoverIdx != null && hoverIdx >= 0 && hoverIdx < n && (
          <>
            <line x1={xAt(hoverIdx)} y1={pad} x2={xAt(hoverIdx)} y2={pad + innerH} stroke="#64748b" strokeDasharray="3 3" strokeWidth="1" />
            {series.map((s, si) => (
              <circle key={si} cx={xAt(hoverIdx)} cy={yAt(s.values[hoverIdx])} r="3.5" fill={s.color} />
            ))}
          </>
        )}
        <text x={pad} y={14} fill="#94a3b8" fontSize="11">
          max {fmt(maxY)} | min {fmt(minY)}
        </text>
        {[0, 0.5, 1].map((t) => {
          const y = pad + innerH * (1 - t)
          const val = minY + range * t
          return (
            <text key={t} x={8} y={y + 4} fill="#64748b" fontSize="9">
              {fmt(val, 1)}
            </text>
          )
        })}
        {labels &&
          (n <= 12 ? labels : labels.filter((_, i) => i % Math.max(1, Math.floor(n / 8)) === 0)).map((lab, i, arr) => {
            const originalIdx = n <= 12 ? i : labels.findIndex((x, idx) => idx % Math.max(1, Math.floor(n / 8)) === 0 && x === lab && arr.indexOf(lab) === i)
            const idx = n <= 12 ? i : originalIdx
            return (
              <text key={`${lab}-${idx}`} x={xAt(idx)} y={h - 8} fill="#64748b" fontSize="9" textAnchor="middle">
                {String(lab).slice(0, 10)}
              </text>
            )
          })}
        <rect
          x={pad}
          y={pad}
          width={innerW}
          height={innerH}
          fill="transparent"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const x = e.clientX - rect.left
            const ratio = Math.max(0, Math.min(1, (x - pad) / innerW))
            setHoverIdx(Math.round(ratio * Math.max(1, n - 1)))
          }}
        />
      </svg>
      {hoverIdx != null && hoverIdx >= 0 && hoverIdx < n && (
        <div style={{ marginTop: 8, padding: '0.5rem 0.65rem', background: '#111827', borderRadius: 6, fontSize: '0.8rem', color: '#cbd5e1' }}>
          <div style={{ color: '#94a3b8', marginBottom: 4 }}>{labels?.[hoverIdx] ?? `Point ${hoverIdx + 1}`}</div>
          {series.map((s) => (
            <div key={s.name}>
              <span style={{ color: s.color, fontWeight: 600 }}>{s.name}:</span> {fmt(s.values[hoverIdx])}
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: 8, fontSize: '0.8rem' }}>
        {summary.map((s) => (
          <span key={s.name}>
            <span style={{ display: 'inline-block', width: 10, height: 10, background: s.color, borderRadius: 2, marginRight: 4, verticalAlign: 'middle' }} />
            {s.name} (min {fmt(s.min)}, avg {fmt(s.avg)}, max {fmt(s.max)})
          </span>
        ))}
      </div>
    </div>
  )
}

/** Donut chart for one value 0–100 (e.g. SOC). */
export function DonutChart({ value, label, color = '#0ea5e9', size = 120 }) {
  const v = Math.max(0, Math.min(100, value))
  const r = 42
  const c = 2 * Math.PI * r
  const dash = (v / 100) * c
  const band = v >= 80 ? 'High' : v >= 40 ? 'Moderate' : 'Low'
  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg width={size} height={size} viewBox="0 0 100 100" title={`${label || 'Value'}: ${v.toFixed(0)}% (${band})`}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="#334155" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={`${dash} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="54" textAnchor="middle" fill="#e2e8f0" fontSize="16" fontWeight="600">
          {v.toFixed(0)}%
        </text>
      </svg>
      {label && <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: 4 }}>{label}</span>}
      <span style={{ fontSize: '0.72rem', color: '#64748b', marginTop: 2 }}>{band}</span>
    </div>
  )
}

/** Horizontal bars: items [{ label, value, color? }], max optional. */
export function HorizontalBarChart({ items, title, unit = '' }) {
  if (!items?.length) return null
  const max = Math.max(...items.map((i) => i.value), 0.001)
  const total = items.reduce((sum, it) => sum + (Number(it.value) || 0), 0)
  return (
    <div style={{ marginTop: 12 }}>
      {title && <div style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: 8 }}>{title}</div>}
      <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: 8 }}>
        Total: {typeof total === 'number' ? total.toFixed(total < 10 ? 2 : 0) : total}
        {unit}
      </div>
      {items.map((it, i) => (
        <div key={i} style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: 2 }}>
            <span style={{ color: '#cbd5e1' }}>{it.label}</span>
            <span style={{ color: '#94a3b8' }}>
              {typeof it.value === 'number' ? it.value.toFixed(it.value < 10 ? 2 : 0) : it.value}
              {unit}
            </span>
          </div>
          <div style={{ height: 8, background: '#1e293b', borderRadius: 4, overflow: 'hidden' }}>
            <div
              title={`${it.label}: ${typeof it.value === 'number' ? it.value.toFixed(it.value < 10 ? 2 : 0) : it.value}${unit}${it.hoverTitle ? ` — ${it.hoverTitle}` : ''}`}
              style={{
                width: `${(it.value / max) * 100}%`,
                height: '100%',
                background: it.color || '#0ea5e9',
                borderRadius: 4,
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Schedule heatmap: rows = appliance names, cols = hours; cells on/off. */
export function ScheduleHeatmap({ matrix, applianceNames, hourLabels }) {
  if (!matrix?.length || !applianceNames?.length) return null
  const cols = matrix[0]?.length || 0
  const cellW = Math.min(28, Math.max(14, Math.floor(600 / cols)))
  const cellH = 22
  const w = cols * cellW + 120
  const h = applianceNames.length * cellH + 36

  return (
    <div style={{ marginTop: '1.5rem', overflowX: 'auto' }}>
      <h2 style={{ fontSize: '1rem', marginBottom: 8 }}>Schedule timeline (green = on, dark = off)</h2>
      <svg width={w} height={h} style={{ background: '#0f172a', borderRadius: 8 }}>
        {hourLabels?.slice(0, cols).map((_, j) => (
          <text key={j} x={120 + j * cellW + cellW / 2} y={14} fill="#64748b" fontSize="9" textAnchor="middle">
            {hourLabels[j]}
          </text>
        ))}
        {applianceNames.map((name, i) => (
          <g key={name}>
            <text x={4} y={36 + i * cellH + cellH / 2 + 4} fill="#e2e8f0" fontSize="10" style={{ maxWidth: 110 }}>
              {name.length > 14 ? `${name.slice(0, 12)}…` : name}
            </text>
            {matrix[i]?.map((on, j) => (
              <rect
                key={j}
                x={120 + j * cellW + 1}
                y={36 + i * cellH + 2}
                width={cellW - 2}
                height={cellH - 4}
                rx={2}
                fill={on ? '#22c55e' : '#1e293b'}
                stroke="#334155"
                strokeWidth={0.5}
                title={`${name} — hour ${hourLabels?.[j] ?? j}: ${on ? 'ON' : 'OFF'}`}
              />
            ))}
          </g>
        ))}
      </svg>
    </div>
  )
}

/** Build 24-column on/off matrix from IEBA slots. */
export function buildScheduleMatrix(slots) {
  if (!slots?.length) return { matrix: [], names: [], hours: [] }
  const names = [...new Set(slots.map((s) => s.appliance_name))].sort()
  const starts = slots.map((s) => new Date(s.start_ts).getTime())
  const minT = Math.min(...starts)
  const base = new Date(minT)
  base.setMinutes(0, 0, 0)
  const hours = Array.from({ length: 24 }, (_, h) => {
    const d = new Date(base)
    d.setHours(base.getHours() + h)
    return d.getHours()
  })
  const matrix = names.map((name) => {
    const row = Array(24).fill(false)
    slots
      .filter((s) => s.appliance_name === name)
      .forEach((s) => {
        const t0 = new Date(s.start_ts).getTime()
        const t1 = new Date(s.end_ts).getTime()
        const on = String(s.planned_state).toLowerCase() === 'on'
        for (let h = 0; h < 24; h++) {
          const hs = base.getTime() + h * 3600000
          const he = hs + 3600000
          if (t0 < he && t1 > hs && on) row[h] = true
        }
      })
    return row
  })
  return { matrix, names, hours }
}
