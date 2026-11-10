import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { messageFrom } from '../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../shared/components/success-notice'
import { safeText } from '../../shared/security/sanitize'

type Status = { active: boolean; ready: boolean; enrolled: boolean; required: boolean }
type Setup = { secret: string; otpauthUri: string; account: string }

function readStatus(data: Record<string, unknown>): Status {
  return {
    active: data.active === true,
    ready: data.ready === true,
    enrolled: data.enrolled === true,
    required: data.required === true,
  }
}

function readSetup(data: Record<string, unknown>): Setup | null {
  const secret = typeof data.secret === 'string' && /^[A-Z2-7]{16,64}$/.test(data.secret) ? data.secret : ''
  const otpauthUri = typeof data.otpauth_uri === 'string' && data.otpauth_uri.startsWith('otpauth://totp/') ? data.otpauth_uri : ''
  if (!secret) return null
  return { secret, otpauthUri, account: safeText(data.account, 64) }
}

function readCodes(data: Record<string, unknown>) {
  const value = data.recovery_codes
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && /^[0-9A-F]{4}-[0-9A-F]{4}$/.test(item)).slice(0, 8)
}

function grouped(secret: string) {
  return secret.replace(/(.{4})/g, '$1 ').trim()
}

async function post(path: string, payload: Record<string, string>) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest<Record<string, unknown>>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload),
  })
}

export function RecoveryCodes({ codes }: { codes: string[] }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
      <p className="text-xs text-amber-900">Save these recovery codes somewhere safe. Each one signs you in once, and they will not be shown again.</p>
      <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm text-gray-900">
        {codes.map((code) => <li key={code}>{code}</li>)}
      </ul>
    </div>
  )
}

function SetupKey({ setup }: { setup: Setup }) {
  const [copied, setCopied] = useState('')
  async function copy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(label)
    } catch {
      setCopied('')
    }
  }
  return (
    <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
      <p>In your authenticator app, choose “enter a setup key”. The account is time-based and uses 6 digits.</p>
      <p className="mt-2">Account <span className="font-semibold text-gray-900">{setup.account || 'your username'}</span></p>
      <p className="mt-1 font-mono text-sm tracking-wide text-gray-900">{grouped(setup.secret)}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className="rounded-md border border-gray-300 bg-white px-2 py-1 font-semibold" onClick={() => void copy(setup.secret, 'Key copied')}>Copy key</button>
        {setup.otpauthUri ? (
          <button type="button" className="rounded-md border border-gray-300 bg-white px-2 py-1 font-semibold" onClick={() => void copy(setup.otpauthUri, 'Link copied')}>Copy setup link</button>
        ) : null}
        {copied ? <span className="self-center text-emerald-700">{copied}</span> : null}
      </div>
    </div>
  )
}

export function SecondFactorCard() {
  const [status, setStatus] = useState<Status | null>(null)
  const [setup, setSetup] = useState<Setup | null>(null)
  const [codes, setCodes] = useState<string[]>([])
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [mode, setMode] = useState<'idle' | 'start' | 'confirm' | 'replace' | 'recovery' | 'disable'>('idle')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)

  function load() {
    return apiRequest<Record<string, unknown>>('/api/account/second-factor')
      .then((data) => setStatus(readStatus(data)))
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }

  useEffect(() => {
    void load()
  }, [])

  async function run(task: () => Promise<void>) {
    setBusy(true)
    setError('')
    setSaved('')
    try {
      await task()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  function onStart(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const data = await post('/api/account/second-factor', { current_password: password })
      const next = readSetup(data)
      if (!next) {
        setError('The setup key could not be read. Try again.')
        return
      }
      setSetup(next)
      setPassword('')
      setMode('confirm')
      setSaved('Add the key to your authenticator app, then enter the 6-digit code.')
    })
  }

  function onConfirm(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const data = await post('/api/account/second-factor/confirm', { code })
      const next = readCodes(data)
      if (!next.length) {
        setError('The recovery codes could not be read. Sign in with the app and replace them from this page.')
        return
      }
      setCodes(next)
      setCode('')
      setSetup(null)
      setMode('idle')
      setSaved('Authenticator app is on.')
      await load()
    })
  }

  function onReplace(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const data = await post('/api/account/second-factor/replace', { code })
      const next = readSetup(data)
      if (!next) {
        setError('The setup key could not be read. Try again.')
        return
      }
      setSetup(next)
      setCode('')
      setMode('confirm')
      setSaved('Your current app still works until you confirm a code from the new one.')
    })
  }

  function onRecovery(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const data = await post('/api/account/second-factor/recovery', { code })
      const next = readCodes(data)
      if (!next.length) {
        setError('The recovery codes could not be read. Try again with the next code.')
        return
      }
      setCodes(next)
      setCode('')
      setMode('idle')
      setSaved('New recovery codes are ready. The previous codes no longer work.')
    })
  }

  function onDisable(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      await post('/api/account/second-factor/disable', { current_password: password, code })
      setPassword('')
      setCode('')
      setCodes([])
      setSetup(null)
      setMode('idle')
      setSaved('Authenticator app removed.')
      await load()
    })
  }

  if (!status?.active) return null

  return (
    <section className="space-y-3 rounded-2xl border border-gray-200 bg-white p-5">
      <h2 className="text-sm font-bold text-gray-800">Authenticator app</h2>
      <FailureNotice message={error} />
      <SuccessNotice message={saved} />
      {!status.ready ? (
        <p className="text-xs text-amber-800">Second factor is switched on, and it starts working after the database migration is applied.</p>
      ) : null}
      {status.ready && status.enrolled ? (
        <p className="text-xs text-gray-600">
          Sign-in asks for a 6-digit code from your authenticator app. A recovery code works once in place of that code.
          {status.required ? ' Your role must keep an authenticator app.' : ''}
        </p>
      ) : null}
      {status.ready && !status.enrolled ? (
        <p className="text-xs text-gray-600">
          {status.required
            ? 'Your role requires an authenticator app. Set it up before the next sign-in.'
            : 'Add an authenticator app if you want a 6-digit code at sign-in.'}
        </p>
      ) : null}
      {codes.length > 0 ? <RecoveryCodes codes={codes} /> : null}
      {setup && mode === 'confirm' ? <SetupKey setup={setup} /> : null}
      {status.ready && !status.enrolled && mode !== 'confirm' ? (
        <form className="space-y-2" onSubmit={onStart}>
          <label className="block text-xs text-gray-600">Current password
            <input type="password" autoComplete="current-password" required value={password} maxLength={128} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" />
          </label>
          <button type="submit" disabled={busy} className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white disabled:opacity-60">Set up authenticator</button>
        </form>
      ) : null}
      {mode === 'confirm' ? (
        <form className="space-y-2" onSubmit={onConfirm}>
          <label className="block text-xs text-gray-600">6-digit code
            <input inputMode="numeric" autoComplete="one-time-code" required value={code} maxLength={12} onChange={(event) => setCode(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-mono" />
          </label>
          <button type="submit" disabled={busy} className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white disabled:opacity-60">Confirm and show recovery codes</button>
        </form>
      ) : null}
      {status.ready && status.enrolled && mode === 'idle' ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-700" onClick={() => { setMode('replace'); setCode(''); setError(''); setSaved('') }}>Use a new phone</button>
          <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-700" onClick={() => { setMode('recovery'); setCode(''); setError(''); setSaved('') }}>New recovery codes</button>
          {!status.required ? (
            <button type="button" className="rounded-lg border border-red-200 px-3 py-2 text-xs font-bold text-red-700" onClick={() => { setMode('disable'); setCode(''); setPassword(''); setError(''); setSaved('') }}>Turn off</button>
          ) : null}
        </div>
      ) : null}
      {mode === 'replace' ? (
        <form className="space-y-2" onSubmit={onReplace}>
          <label className="block text-xs text-gray-600">Current 6-digit code or a recovery code
            <input autoComplete="one-time-code" required value={code} maxLength={20} onChange={(event) => setCode(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-mono" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white disabled:opacity-60">Show the new key</button>
            <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-700" onClick={() => setMode('idle')}>Cancel</button>
          </div>
        </form>
      ) : null}
      {mode === 'recovery' ? (
        <form className="space-y-2" onSubmit={onRecovery}>
          <label className="block text-xs text-gray-600">Current 6-digit code
            <input inputMode="numeric" autoComplete="one-time-code" required value={code} maxLength={12} onChange={(event) => setCode(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-mono" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white disabled:opacity-60">Replace recovery codes</button>
            <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-700" onClick={() => setMode('idle')}>Cancel</button>
          </div>
        </form>
      ) : null}
      {mode === 'disable' ? (
        <form className="space-y-2" onSubmit={onDisable}>
          <label className="block text-xs text-gray-600">Current password
            <input type="password" autoComplete="current-password" required value={password} maxLength={128} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" />
          </label>
          <label className="block text-xs text-gray-600">6-digit code or a recovery code
            <input autoComplete="one-time-code" required value={code} maxLength={20} onChange={(event) => setCode(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 font-mono" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="rounded-lg bg-red-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-60">Turn off</button>
            <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-700" onClick={() => setMode('idle')}>Cancel</button>
          </div>
        </form>
      ) : null}
    </section>
  )
}
