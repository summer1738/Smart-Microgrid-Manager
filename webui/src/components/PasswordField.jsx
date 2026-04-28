import { useState } from 'react'

export default function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  placeholder,
  disabled = false,
}) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="auth-form__field">
      <label htmlFor={id} className="auth-form__label">
        {label}
      </label>
      <div className="auth-passwordRow">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          placeholder={placeholder}
          className="auth-form__input auth-form__input--password"
          disabled={disabled}
        />
        <button
          type="button"
          className="auth-passwordRow__toggle"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
        >
          {visible ? 'Hide' : 'Show'}
        </button>
      </div>
    </div>
  )
}
