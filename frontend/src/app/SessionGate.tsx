import { FailureNotice } from '../shared/components/success-notice'
import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useMatches } from 'react-router-dom'
import { canOpenPage } from './page-access'
import { PasswordExpiredScreen } from '../features/account/PasswordExpiredScreen'
import { LoginPage } from '../features/auth/pages/LoginPage'
import { MaintenancePage } from '../features/errors/MaintenancePage'
import { getBranding, getSession, type Branding, type SessionInfo } from '../shared/api/endpoints'
import { fallbackBranding } from '../shared/security/sanitize'
import { applyBrandingHead } from '../shared/theme'
import { AdminFrame } from './page-header'

const allowedRoles = new Set(['Admin', 'Super Admin', 'HOD', 'Teacher', 'Student'])
const staffRoles = new Set(['Admin', 'Super Admin', 'HOD'])

function adminPanel(pathname: string) {
  return pathname === '/admin' || pathname.startsWith('/admin/')
}

export function RootGate() {
  const location = useLocation()
  const [branding, setBranding] = useState<Branding>(fallbackBranding)
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [error, setError] = useState('')
  const adminLogin = location.pathname === '/admin/login' || location.pathname.startsWith('/admin/') || location.pathname === '/admin'

  const institutionCode = new URLSearchParams(location.search).get('i') || ''
  const load = useCallback(async () => {
    setError('')
    const [nextBranding, nextSession] = await Promise.all([
      getBranding(institutionCode).catch(() => fallbackBranding),
      getSession(),
    ])
    setBranding(nextBranding)
    setSession(nextSession)
  }, [institutionCode])

  useEffect(() => {
    void load().catch(() => setError('The Flask server is not reachable. Start it on port 5000 and try again.'))
  }, [load])

  useEffect(() => {
    applyBrandingHead(branding)
  }, [branding])

  useEffect(() => {
    const refresh = () => {
      void getBranding(institutionCode).then(setBranding).catch(() => undefined)
    }
    window.addEventListener('branding-updated', refresh)
    return () => window.removeEventListener('branding-updated', refresh)
  }, [institutionCode])

  if (error) {
    return <div className="flex min-h-screen items-center justify-center bg-gray-100 p-6 text-sm text-gray-600"><FailureNotice message={error} hold />The application could not be opened.</div>
  }

  if (!session) {
    return <div className="min-h-screen bg-gray-100" />
  }

  const staff = session.authenticated && staffRoles.has(session.role)
  if (session.maintenance && (!adminPanel(location.pathname) || (session.authenticated && !staff))) {
    return <MaintenancePage branding={branding} />
  }

  if (session.authenticated && session.password_expired) {
    return <PasswordExpiredScreen branding={branding} onSuccess={() => void load()} />
  }

  if (!session.authenticated) {
    return (
      <LoginPage
        mode={adminLogin ? 'admin' : 'student'}
        branding={branding}
        onSuccess={() => void load()}
      />
    )
  }

  if (session.role === 'Teacher' || session.role === 'Student' || allowedRoles.has(session.role) || session.role) {
    return (
      <AdminFrame branding={branding} session={session}>
        <GuardedOutlet session={session} />
      </AdminFrame>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-6 text-sm text-gray-700">
      This account does not have access to the dashboard.
    </div>
  )
}

function GuardedOutlet({ session }: { session: Extract<SessionInfo, { authenticated: true }> }) {
  const location = useLocation()
  const matches = useMatches()
  if (matches.some((match) => (match.handle as { errorPage?: boolean } | undefined)?.errorPage)) {
    return <Outlet context={session} />
  }
  if (!canOpenPage(location.pathname, session)) {
    return (
      <section className="mx-auto max-w-lg rounded-2xl border border-gray-200 bg-white px-6 py-10 text-center shadow-sm">
        <h2 className="text-base font-bold text-gray-800">You do not have permission to open this page.</h2>
        <p className="mt-2 text-sm text-gray-500">The menu lists the pages this account is allowed to use.</p>
      </section>
    )
  }
  return <Outlet context={session} />
}
