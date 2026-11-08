import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { submitLogin } from '../../../shared/api/auth'
import type { Branding } from '../../../shared/api/endpoints'
import { copyrightLine } from '../../../shared/components/layout/Footer'
import { ThemeModeButton } from '../../../shared/components/ThemeModeButton'
import { staticAssetUrl } from '../../../shared/security/sanitize'

type LoginPageProps = {
  mode: 'admin' | 'student'
  branding: Branding
  onSuccess: () => void
}

export function LoginPage({ mode, branding, onSuccess }: LoginPageProps) {
  const admin = mode === 'admin'
  const loginLogo = staticAssetUrl(branding.login_logo) || staticAssetUrl(branding.site_logo)
  const background = staticAssetUrl(admin ? branding.admin_login_background : branding.login_background)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const result = await submitLogin(admin ? '/admin/login' : '/login', username, password)
      if (result.ok) {
        onSuccess()
      } else {
        setError(result.message)
      }
    } catch {
      setError('The Flask server is not reachable. Start it on port 5000 and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className={`relative flex min-h-screen items-center justify-center p-6 font-sans ${background ? 'bg-slate-900 bg-cover bg-center' : 'bg-gray-100'}`}
      style={background ? { backgroundImage: `url("${background}")` } : undefined}
    >
      {background ? <div className="absolute inset-0 bg-slate-950/45" /> : null}
      <ThemeModeButton className="fixed top-4 right-4 z-20 border border-gray-200 bg-white text-gray-700 shadow-sm" />
      <div className="relative z-10 flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:h-[460px] md:flex-row">
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
              <p className="mt-2 text-sm text-gray-500">{admin ? 'Please identify yourself to continue.' : 'Please enter your details to sign in.'}</p>
            </div>
            {error ? (
              <div role="alert" className="mb-4 rounded-lg border-l-4 border-red-500 bg-red-50 p-4 text-sm text-red-700">
                {error}
              </div>
            ) : null}
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
