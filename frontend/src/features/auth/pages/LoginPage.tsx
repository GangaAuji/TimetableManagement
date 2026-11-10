import { FailureNotice } from '../../../shared/components/success-notice'
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { loadPendingSignIn, submitLogin, submitSecondFactor } from '../../../shared/api/auth'
import { RecoveryCodes } from '../../account/SecondFactorCard'
import { apiRequest } from '../../../shared/api/client'
import type { Branding } from '../../../shared/api/endpoints'
import { safeText } from '../../../shared/security/sanitize'
import { copyrightLine } from '../../../shared/components/layout/Footer'
import { ThemeModeButton } from '../../../shared/components/ThemeModeButton'
import { staticAssetUrl } from '../../../shared/security/sanitize'

type LoginPageProps = {
  mode: 'admin' | 'student'
  branding: Branding
  onSuccess: () => void
}

type SsoDescriptor = { enabled: boolean; provider: string; button_label: string }

const ssoMessages: Record<string, string> = {
  sso_disabled: 'Single sign-on is not enabled.',
  sso_incomplete: 'Single sign-on is not fully configured. Contact the administrator.',
  sso_provider_unavailable: 'The sign-in provider could not be reached. Try again later.',
  sso_provider_denied: 'The sign-in provider did not complete the sign-in.',
  sso_state_mismatch: 'The sign-in request expired or did not start here. Try again.',
  sso_token_failed: 'The sign-in provider rejected the request. Contact the administrator.',
  sso_token_invalid: 'The sign-in provider returned an invalid token. Contact the administrator.',
  sso_email_unverified: 'Your provider account has no verified email address.',
  sso_domain_not_allowed: 'Your email domain is not allowed to sign in here.',
  sso_no_account: 'No staff account matches your sign-in. Contact the administrator.',
  sso_account_locked: 'Your account has been locked. Contact the administrator.',
  sso_account_inactive: 'Your account has been deactivated. Contact the administrator.',
  sso_second_factor: 'The authenticator could not be started. Contact the administrator.',
  sso_network: 'Sign-in is not allowed from this network.',
}

function ssoErrorFromUrl() {
  const code = safeText(new URLSearchParams(window.location.search).get('sso_error'), 40)
  return code ? ssoMessages[code] || 'Single sign-on failed.' : ''
}

export function LoginPage({ mode, branding, onSuccess }: LoginPageProps) {
  const admin = mode === 'admin'
  const loginLogo = staticAssetUrl(branding.login_logo) || staticAssetUrl(branding.site_logo)
  const background = staticAssetUrl(admin ? branding.admin_login_background : branding.login_background)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(ssoErrorFromUrl)
  const [submitting, setSubmitting] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [sso, setSso] = useState<SsoDescriptor | null>(null)
  const [step, setStep] = useState<'password' | 'totp' | 'enroll' | 'codes'>('password')
  const [code, setCode] = useState('')
  const [setupSecret, setSetupSecret] = useState('')
  const [setupAccount, setSetupAccount] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    apiRequest<Record<string, unknown>>('/api/sso')
      .then((data) => {
        if (cancelled || data.enabled !== true) return
        setSso({ enabled: true, provider: safeText(data.provider, 20), button_label: safeText(data.button_label, 60) || 'Sign in with SSO' })
      })
      .catch(() => { /* no SSO button */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    void loadPendingSignIn()
      .then((pending) => {
        if (cancelled || !pending) return
        setStep(pending.pending)
        setSetupSecret(pending.secret)
        setSetupAccount(pending.account)
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [])

  const ssoIcon = sso?.provider === 'google' ? 'fab fa-google' : sso?.provider === 'microsoft' ? 'fab fa-microsoft' : 'fas fa-id-badge'

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const result = await submitLogin(admin ? '/admin/login' : '/login', username, password)
      if (result.ok) {
        onSuccess()
      } else if ('pending' in result) {
        setStep(result.pending)
        setSetupSecret(result.secret)
        setSetupAccount(result.account)
        setCode('')
      } else {
        setError(result.message)
      }
    } catch {
      setError('The Flask server is not reachable. Start it on port 5000 and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function onCode(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const result = await submitSecondFactor(code)
      if (result.ok) {
        if (result.recoveryCodes?.length) {
          setRecoveryCodes(result.recoveryCodes)
          setStep('codes')
        } else {
          onSuccess()
        }
      } else if ('message' in result) {
        setError(result.message)
        if (result.cleared) {
          setStep('password')
          setCode('')
        }
      }
    } catch {
      setError('The Flask server is not reachable. Start it on port 5000 and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const groupedSecret = setupSecret.replace(/(.{4})/g, '$1 ').trim()

  return (
    <div
      className={`relative flex min-h-screen items-center justify-center p-6 font-sans ${background ? 'bg-slate-900 bg-cover bg-center' : 'bg-gray-100'}`}
      style={background ? { backgroundImage: `url("${background}")` } : undefined}
    >
      {background ? <div className="absolute inset-0 bg-slate-950/45" /> : null}
      <ThemeModeButton className="fixed top-4 right-4 z-20 border border-gray-200 bg-white text-gray-700 shadow-sm" />
      <div className="relative z-10 flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:min-h-[460px] md:flex-row">
        <div className={`relative hidden flex-col justify-between overflow-hidden p-8 text-white md:flex md:w-5/12 ${admin ? 'bg-slate-900' : 'bg-blue-900'}`}>
          <div className="relative z-10">
            <div className="mb-4 flex items-center gap-2">
              {loginLogo ? (
                <img src={loginLogo} alt="" className="h-10 w-auto max-w-[140px] object-contain" />
              ) : (
                <i className={`fas ${admin ? 'fa-shield-alt text-red-500' : 'fa-graduation-cap text-blue-300'} text-2xl`} />
              )}
              <span className={`text-lg font-bold tracking-wider ${admin ? 'text-red-500' : ''}`}>
                {admin ? 'ADMIN' : branding.institution_short_name}
              </span>
            </div>
            <h2 className="mb-3 text-2xl leading-tight font-bold">
              {admin ? 'System Administration' : branding.tagline}
            </h2>
            <p className={admin ? 'text-slate-300' : 'text-blue-200'}>
              {admin
                ? 'Secure access for managing courses, faculty allocations, and system configurations.'
                : branding.welcome_message}
            </p>
          </div>
          <div className="relative z-10">
            {admin ? (
              <Link to="/" className="flex items-center text-sm text-slate-300 transition hover:text-white">
                <i className="fas fa-arrow-left mr-2" /> Student and teacher sign in
              </Link>
            ) : (
              <div className="text-sm text-blue-300">
                {copyrightLine(branding)}
              </div>
            )}
          </div>
        </div>

        <div className="relative flex w-full flex-col justify-center p-6 md:w-7/12 md:p-8">
          <div className="mx-auto w-full max-w-sm">
            {loginLogo ? <img src={loginLogo} alt="" className="mb-4 h-9 w-auto max-w-[120px] object-contain md:hidden" /> : null}
            <div className={`mb-5 ${admin ? 'border-b border-gray-100 pb-3' : ''}`}>
              <h1 className="text-2xl font-bold text-gray-900">{admin ? 'Admin Sign In' : branding.login_title}</h1>
              <p className="mt-2 text-sm text-gray-500">
                {step === 'codes'
                  ? 'Save these codes before continuing.'
                  : step === 'enroll'
                    ? 'Add this key to your authenticator app, then enter the 6-digit code.'
                    : step === 'totp'
                      ? 'Enter the 6-digit code from your authenticator app, or a recovery code.'
                      : admin ? 'Please identify yourself to continue.' : 'Please enter your details to sign in.'}
              </p>
            </div>
            <FailureNotice message={error} />
            {step === 'codes' ? (
              <div className="space-y-4">
                <RecoveryCodes codes={recoveryCodes} />
                <button
                  type="button"
                  onClick={onSuccess}
                  className={`flex w-full justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white ${admin ? 'bg-red-600 hover:bg-red-700' : ''}`}
                  style={admin ? undefined : { backgroundColor: branding.primary_color || '#059669' }}
                >
                  I have saved these codes
                </button>
              </div>
            ) : null}
            {step === 'totp' || step === 'enroll' ? (
              <form onSubmit={(event) => void onCode(event)} className="space-y-4">
                {step === 'enroll' && setupSecret ? (
                  <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
                    <p>In your authenticator app, choose “enter a setup key”. Time-based, 6 digits.</p>
                    <p className="mt-2">Account <span className="font-semibold text-gray-900">{setupAccount || username}</span></p>
                    <p className="mt-1 font-mono text-sm tracking-wide text-gray-900">{groupedSecret}</p>
                  </div>
                ) : null}
                {step === 'enroll' && !setupSecret ? (
                  <p className="text-sm text-gray-600">The setup key is no longer available. Sign in with your password again.</p>
                ) : null}
                <div>
                  <label htmlFor="otp-code" className="mb-1 block text-sm font-medium text-gray-700">
                    {step === 'enroll' ? '6-digit code' : 'Code'}
                  </label>
                  <input
                    id="otp-code"
                    name="code"
                    required
                    autoComplete="one-time-code"
                    value={code}
                    maxLength={20}
                    onChange={(event) => setCode(event.target.value)}
                    className={`w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 font-mono text-sm outline-none focus:border-transparent focus:ring-2 ${admin ? 'focus:ring-red-500' : 'focus:ring-blue-500'}`}
                  />
                </div>
                <button
                  type="submit"
                  disabled={submitting}
                  className={`flex w-full justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60 ${admin ? 'bg-red-600 hover:bg-red-700' : ''}`}
                  style={admin ? undefined : { backgroundColor: branding.primary_color || '#059669' }}
                >
                  {submitting ? 'Checking…' : 'Continue'}
                </button>
                <button
                  type="button"
                  className="w-full text-sm font-medium text-gray-500 hover:text-gray-800"
                  onClick={() => { setStep('password'); setCode(''); setError('') }}
                >
                  Use password again
                </button>
              </form>
            ) : null}
            {step === 'password' ? (
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label htmlFor="username" className="mb-1 block text-sm font-medium text-gray-700">
                  {admin ? 'Username' : 'Username / ID'}
                </label>
                <div className="relative">
                  {admin ? null : (
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                      <i className="fas fa-user text-gray-400" />
                    </div>
                  )}
                  <input
                    id="username"
                    name="username"
                    required
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder={admin ? undefined : 'Enter your ID'}
                    className={`${admin ? '' : 'pl-10'} w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm transition-all outline-none focus:border-transparent focus:ring-2 ${admin ? 'focus:ring-red-500' : 'focus:ring-blue-500'}`}
                  />
                </div>
              </div>
              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">Password</label>
                <div className="relative">
                  {admin ? null : (
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                      <i className="fas fa-lock text-gray-400" />
                    </div>
                  )}
                  <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={admin ? undefined : '••••••••'}
                    className={`${admin ? '' : 'pl-10'} w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm transition-all outline-none focus:border-transparent focus:ring-2 ${admin ? 'focus:ring-red-500' : 'focus:ring-blue-500'}`}
                  />
                </div>
              </div>
              <div className={`flex items-center ${admin ? 'justify-end' : 'justify-between'}`}>
                {admin ? null : (
                  <label className="flex items-center text-sm text-gray-900">
                    <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    <span className="ml-2">Remember me</span>
                  </label>
                )}
                <button type="button" onClick={() => setForgotOpen(true)} className={`text-sm font-medium hover:underline ${admin ? 'text-red-600 hover:text-red-500' : 'text-blue-600 hover:text-blue-500'}`}>
                  Forgot password?
                </button>
              </div>
              <button
                type="submit"
                disabled={submitting}
                className={`flex w-full justify-center rounded-lg border border-transparent px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all focus:ring-2 focus:ring-offset-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 ${admin ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500' : 'focus:ring-blue-500'}`}
                style={admin ? undefined : { backgroundColor: branding.primary_color || '#059669' }}
              >
                {admin ? <i className="fas fa-lock mt-1 mr-2" /> : null}
                {submitting ? 'Signing in…' : admin ? 'Access Dashboard' : 'Sign In'}
              </button>
            </form>
            ) : null}
            {step === 'password' && sso && !admin ? (
              <div className="mt-4">
                <div className="mb-3 flex items-center gap-3 text-[11px] font-medium tracking-wide text-gray-400 uppercase">
                  <span className="h-px flex-1 bg-gray-200" />staff<span className="h-px flex-1 bg-gray-200" />
                </div>
                <a
                  href="/auth/sso/start"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-800 shadow-sm transition hover:bg-gray-50"
                >
                  <i className={ssoIcon} aria-hidden="true" />
                  {sso.button_label}
                </a>
              </div>
            ) : null}
            {admin ? (
              <Link to="/" className="mt-6 block text-sm text-slate-500 hover:text-slate-800 md:hidden">
                Student and teacher sign in
              </Link>
            ) : (
              <div className="mt-5 text-center text-sm text-gray-500">
                Not a member? Contact the <span className="font-medium text-gray-700">Administration Office</span>.
                <Link to="/admin/login" className="mt-3 block w-full font-medium text-slate-600 hover:text-slate-900">
                  Admin sign in
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>

      {forgotOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/50 p-4 backdrop-blur-sm">
          <div className={`w-full max-w-md rounded-xl bg-white p-8 shadow-2xl ${admin ? 'border-t-4 border-red-600' : ''}`}>
            <div className="mb-6 text-center">
              {admin ? null : (
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100">
                  <i className="fas fa-key text-xl text-blue-600" />
                </div>
              )}
              <h3 className="text-xl font-bold text-gray-900">{admin ? 'Admin Recovery' : 'Reset Password'}</h3>
              <p className="mt-2 text-sm text-gray-500">
                {admin
                  ? 'Contact the system super-admin or IT department, or enter your recovery email below.'
                  : "Enter your email address and we'll send you a link to reset your password."}
              </p>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                window.alert(admin ? 'Reset request logged.' : 'If this email exists, a reset link has been sent.')
                setForgotOpen(false)
              }}
            >
              <label htmlFor="reset-email" className="mb-1 block text-sm font-medium text-gray-700">
                {admin ? 'Recovery Email' : 'Email Address'}
              </label>
              <input id="reset-email" type="email" required className={`mb-6 w-full rounded-lg border border-gray-300 px-4 py-2 outline-none focus:ring-2 ${admin ? 'focus:ring-red-500' : 'focus:ring-blue-500'}`} />
              <div className="flex gap-3">
                <button type="button" onClick={() => setForgotOpen(false)} className="w-1/2 rounded-lg border border-gray-300 px-4 py-2 font-medium text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button type="submit" className={`w-1/2 rounded-lg px-4 py-2 font-medium text-white ${admin ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}`}>
                  {admin ? 'Request' : 'Send Link'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  )
}
