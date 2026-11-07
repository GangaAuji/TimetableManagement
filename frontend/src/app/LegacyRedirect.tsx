import { Navigate, useLocation } from 'react-router-dom'
import { reactPath } from './legacy-paths'

export function LegacyRedirect() {
  const location = useLocation()
  const target = reactPath(location.pathname)
  if (target === location.pathname) return <Navigate to="/" replace />
  return <Navigate to={target} replace />
}

export function LegacyStaffAlias() {
  const location = useLocation()
  const target = reactPath(location.pathname)
  if (!target.startsWith('/admin') || target === location.pathname) return <Navigate to="/admin" replace />
  return <Navigate to={target} replace />
}

export function PrefixedRedirect() {
  const location = useLocation()
  return <Navigate to={`/admin${location.pathname}${location.search}`} replace />
}
