import { Link } from 'react-router-dom'

const platformPoints = [
  {
    title: 'Forecast-aware decisions',
    detail: 'Weather, PV output, battery headroom, and load scheduling stay visible in one flow.',
  },
  {
    title: 'Role-based access',
    detail: 'Viewers, operators, and admins each land in the parts of the workspace they actually need.',
  },
  {
    title: 'Development ready',
    detail: 'Seeded accounts and simulation mode make it easy to test without waiting on hardware.',
  },
]

const platformStats = [
  { value: '24h', label: 'forecast window' },
  { value: '3', label: 'built-in roles' },
  { value: '1', label: 'shared control surface' },
]

export default function AuthShell({
  panelTitle,
  panelCopy,
  switchPrompt,
  switchLabel,
  switchTo,
  children,
  footer = null,
}) {
  return (
    <div className="auth-shell">
      <section className="auth-shell__intro">
        <div>
          <div className="auth-shell__eyebrow">Smart Microgrid Manager</div>
          <h1 className="auth-shell__headline">Keep the microgrid in view without losing the details.</h1>
          <p className="auth-shell__lead">
            Track live power conditions, manage appliance schedules, and move from simulation into operations with the
            same workspace.
          </p>
        </div>

        <div className="auth-shell__stats" aria-label="platform highlights">
          {platformStats.map((item) => (
            <div key={item.label} className="auth-shell__stat">
              <div className="auth-shell__statValue">{item.value}</div>
              <div className="auth-shell__statLabel">{item.label}</div>
            </div>
          ))}
        </div>

        <div className="auth-shell__points" aria-label="platform details">
          {platformPoints.map((item) => (
            <div key={item.title} className="auth-shell__point">
              <h2>{item.title}</h2>
              <p>{item.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="auth-shell__formColumn">
        <div className="auth-card">
          <div className="auth-card__header">
            <div>
              <h2 className="auth-card__title">{panelTitle}</h2>
              <p className="auth-card__copy">{panelCopy}</p>
            </div>
            <p className="auth-card__switch">
              {switchPrompt} <Link to={switchTo}>{switchLabel}</Link>
            </p>
          </div>

          {children}

          {footer ? <div className="auth-card__footer">{footer}</div> : null}
        </div>
      </section>
    </div>
  )
}
