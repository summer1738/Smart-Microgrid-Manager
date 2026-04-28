import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import AuthShell from '../components/AuthShell'
import PasswordField from '../components/PasswordField'
import { useAuth } from '../context/AuthContext'

const DEV_ACCOUNTS = [
  { label: 'Admin', username: 'admin', password: 'admin123' },
  { label: 'Operator', username: 'operator', password: 'operator123' },
  { label: 'Viewer', username: 'viewer', password: 'viewer123' },
]

export default function Login() {
  const { user, login, ready } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    setError(null)
  }, [username, password])

  if (ready && user) {
    return <Navigate to="/" replace />
  }

  const canSubmit = username.trim().length > 0 && password.length > 0 && !submitting

  const onSubmit = async (event) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    try {
      await login({ username: username.trim(), password })
      navigate('/', { replace: true })
    } catch (caught) {
      setError(caught.message || 'Could not sign in')
      setSubmitting(false)
    }
  }

  const fillDevelopmentAccount = (account) => {
    setUsername(account.username)
    setPassword(account.password)
  }

  return (
    <AuthShell
      panelTitle="Sign in"
      panelCopy="Use your account to open the live dashboard, scheduling tools, and system controls."
      switchPrompt="Need an account?"
      switchLabel="Create one"
      switchTo="/signup"
      footer={
        <>
          <div className="auth-card__footerTitle">Seeded development accounts</div>
          <div className="auth-demoGrid">
            {DEV_ACCOUNTS.map((account) => (
              <button
                key={account.username}
                type="button"
                className="auth-demoButton"
                onClick={() => fillDevelopmentAccount(account)}
              >
                <span>{account.label}</span>
                <strong>{account.username}</strong>
              </button>
            ))}
          </div>
          <p className="auth-card__footerNote">Tap one to fill the form for local testing.</p>
        </>
      }
    >
      <form onSubmit={onSubmit} className="auth-form">
        {error ? (
          <div className="auth-form__message" role="alert">
            {error}
          </div>
        ) : null}

        <div className="auth-form__field">
          <label htmlFor="username" className="auth-form__label">
            Username
          </label>
          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="admin"
            className="auth-form__input"
            disabled={submitting}
          />
        </div>

        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          placeholder="Enter your password"
          disabled={submitting}
        />

        <button type="submit" className="auth-form__submit" disabled={!canSubmit}>
          {submitting ? 'Signing in...' : 'Continue to dashboard'}
        </button>
      </form>
    </AuthShell>
  )
}
