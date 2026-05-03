import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import AuthShell from '../components/AuthShell'
import PasswordField from '../components/PasswordField'
import { useAuth } from '../context/AuthContext'

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/

export default function Signup() {
  const { user, signup, ready } = useAuth()
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    setError(null)
  }, [name, username, password, confirmPassword])

  if (ready && user) {
    return <Navigate to="/" replace />
  }

  const trimmedName = name.trim()
  const trimmedUsername = username.trim()
  const passwordsMatch = password === confirmPassword
  const usernameLooksValid = USERNAME_PATTERN.test(trimmedUsername)
  const canSubmit =
    trimmedName.length >= 2 &&
    trimmedUsername.length >= 3 &&
    usernameLooksValid &&
    password.length >= 8 &&
    passwordsMatch &&
    !submitting

  const onSubmit = async (event) => {
    event.preventDefault()
    if (!passwordsMatch) {
      setError('Passwords do not match')
      return
    }
    if (!usernameLooksValid) {
      setError('Username can only use letters, numbers, dots, dashes, and underscores')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setSubmitting(true)
    try {
      await signup({ name: trimmedName, username: trimmedUsername, password })
      navigate('/', { replace: true })
    } catch (caught) {
      setError(caught.message || 'Could not create your account')
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      panelTitle="Create an account"
      panelCopy="New accounts start with viewer access, which is enough to explore dashboards, forecasts, and weather."
      switchPrompt="Already have an account?"
      switchLabel="Sign in"
      switchTo="/login"
      footer={<p className="auth-card__footerNote">Usernames are stored in lowercase when the account is created.</p>}
    >
      <form onSubmit={onSubmit} className="auth-form">
        {error ? (
          <div className="auth-form__message" role="alert">
            {error}
          </div>
        ) : null}

        <div className="auth-form__field">
          <label htmlFor="name" className="auth-form__label">
            Full name
          </label>
          <input
            id="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="name"
            placeholder="Site operator"
            className="auth-form__input"
            disabled={submitting}
          />
        </div>

        <div className="auth-form__field">
          <label htmlFor="signup-username" className="auth-form__label">
            Username
          </label>
          <input
            id="signup-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="operator.mutasa"
            className="auth-form__input"
            disabled={submitting}
          />
          <p className="auth-form__hint">Letters, numbers, dots, dashes, and underscores only.</p>
        </div>

        <PasswordField
          id="signup-password"
          label="Password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          placeholder="At least 8 characters"
          disabled={submitting}
        />

        <PasswordField
          id="signup-confirm-password"
          label="Confirm password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          autoComplete="new-password"
          placeholder="Re-enter your password"
          disabled={submitting}
        />

        <button type="submit" className="auth-form__submit" disabled={!canSubmit}>
          {submitting ? 'Creating account...' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  )
}
