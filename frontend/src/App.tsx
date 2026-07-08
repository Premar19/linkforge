import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createLink, login, redirectUrl, signup, streamUrl } from './api'
import type { LinkStat } from './types'

const TOKEN_STORAGE_KEY = 'linkforge_token'

export default function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_STORAGE_KEY),
  )

  function handleAuthenticated(newToken: string) {
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken)
    setToken(newToken)
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
  }

  if (!token) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />
  }
  return <Dashboard token={token} onLogout={handleLogout} />
}

// ---------------------------------------------------------------------------

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [tenantName, setTenantName] = useState('')
  const [tenantSlug, setTenantSlug] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const result =
        mode === 'signup'
          ? await signup(tenantName, tenantSlug, email, password)
          : await login(tenantSlug, email, password)
      onAuthenticated(result.access_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <p className="auth-brand">LinkForge</p>
        <h1 className="auth-title">{mode === 'signup' ? 'Create your workspace' : 'Sign in'}</h1>

        {error && <p className="error-msg">{error}</p>}

        <form onSubmit={handleSubmit}>
          {mode === 'signup' && (
            <div className="field">
              <label htmlFor="tenantName">Team name</label>
              <input
                id="tenantName"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                placeholder="Acme Inc"
                required
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="tenantSlug">Workspace slug</label>
            <input
              id="tenantSlug"
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              placeholder="acme"
              pattern="[a-z0-9-]+"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              minLength={8}
              required
            />
          </div>
          <button className="btn-primary" type="submit" disabled={submitting}>
            {submitting ? 'Please wait…' : mode === 'signup' ? 'Create workspace' : 'Sign in'}
          </button>
        </form>

        <button
          className="link-toggle"
          onClick={() => {
            setError(null)
            setMode(mode === 'signup' ? 'login' : 'signup')
          }}
        >
          {mode === 'signup' ? 'Already have a workspace? Sign in' : "Don't have a workspace? Create one"}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function Dashboard({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [links, setLinks] = useState<LinkStat[]>([])
  const [isLive, setIsLive] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [pulsingCodes, setPulsingCodes] = useState<Set<string>>(new Set())
  const prevCounts = useRef<Map<string, number>>(new Map())

  useEffect(() => {
    const source = new EventSource(streamUrl(token))

    source.onopen = () => setIsLive(true)
    source.onerror = () => setIsLive(false)

    source.onmessage = (event) => {
      const data: LinkStat[] = JSON.parse(event.data)

      // Detect which rows actually increased since the last poll, so we
      // only pulse the ones that changed — not every row on every tick.
      const justIncreased = new Set<string>()
      for (const row of data) {
        const prev = prevCounts.current.get(row.code)
        if (prev !== undefined && row.clicks > prev) {
          justIncreased.add(row.code)
        }
        prevCounts.current.set(row.code, row.clicks)
      }

      setLinks(data)
      if (justIncreased.size > 0) {
        setPulsingCodes(justIncreased)
        setTimeout(() => setPulsingCodes(new Set()), 600)
      }
    }

    return () => source.close()
  }, [token])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setCreateError(null)
    setCreating(true)
    try {
      await createLink(token, newUrl)
      setNewUrl('')
      // The new link appears on the next poll tick (within
      // POLL_INTERVAL_SECONDS) — deliberately not merged in optimistically,
      // since the whole point of this view is showing what the live stream
      // actually reports, not a locally-faked state.
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Could not create link')
    } finally {
      setCreating(false)
    }
  }

  function handleCopy(code: string) {
    navigator.clipboard.writeText(redirectUrl(code))
  }

  return (
    <div className="dashboard">
      <div className="dash-header">
        <div className="dash-title">
          <h1>Links</h1>
          <span className="status-pill">
            <span className={`status-dot ${isLive ? 'live' : ''}`} />
            {isLive ? 'Live' : 'Connecting…'}
          </span>
        </div>
        <button className="btn-secondary" onClick={onLogout}>
          Sign out
        </button>
      </div>

      <form className="create-form" onSubmit={handleCreate}>
        <input
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          placeholder="https://example.com/your-long-url"
          type="url"
          required
        />
        <button type="submit" disabled={creating}>
          {creating ? 'Creating…' : 'Create link'}
        </button>
      </form>
      {createError && <p className="error-msg">{createError}</p>}

      {links.length === 0 ? (
        <div className="empty-state">No links yet — create one above.</div>
      ) : (
        <div className="link-table">
          {links.map((link) => (
            <div className="link-row" key={link.code}>
              <div className="link-info">
                <div className={`link-code ${link.is_active ? '' : 'inactive'}`}>
                  /r/{link.code}
                  <button className="copy-btn" onClick={() => handleCopy(link.code)}>
                    copy
                  </button>
                </div>
                <div className="link-target">{link.target_url}</div>
              </div>
              <div>
                <div className={`click-count ${pulsingCodes.has(link.code) ? 'pulse' : ''}`}>
                  {link.clicks}
                </div>
                <div className="clicks-label">clicks</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
