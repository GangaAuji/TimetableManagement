import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { canOpenPage } from './page-access'
import { LoginPage } from '../features/auth/pages/LoginPage'
import { getBranding, getSession, type Branding, type SessionInfo } from '../shared/api/endpoints'
import { fallbackBranding } from '../shared/security/sanitize'
import { applyBrandingHead } from '../shared/theme'
import { AdminFrame } from './page-header'

const allowedRoles = new Set(['Admin', 'Super Admin', 'HOD', 'Teacher', 'Student'])

export function RootGate() {
  const location = useLocation()
  const [branding, setBranding] = useState<Branding>(fallbackBranding)
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [error, setError] = useState('')
  const adminLogin = location.pathname === '/admin/login' || location.pathname.startsWith('/admin/') || location.pathname === '/admin'

  const load = useCallback(async () => {
    setError('')
    const [nextBranding, nextSession] = await Promise.all([
      getBranding().catch(() => fallbackBranding),
      getSession(),
    ])
    setBranding(nextBranding)
    setSession(nextSession)
  }, [])

  useEffect(() => {
    void load().catch(() => setError('The Flask server is not reachable. Start it on port 5000 and try again.'))
  }, [load])

  useEffect(() => {
    applyBrandingHead(branding)
  }, [branding])

  useEffect(() => {
    const refresh = () => {
      void getBranding().then(setBranding).catch(() => undefined)
    }
    window.addEventListener('branding-updated', refresh)
    return () => window.removeEventListener('branding-updated', refresh)
  }, [])

  if (error) {
    return <div className="flex min-h-screen items-center justify-center bg-gray-100 p-6 text-sm text-red-700">{error}</div>
  }

  if (!session) {
    return <div className="min-h-screen bg-gray-100" />
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
