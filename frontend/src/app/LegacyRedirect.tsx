import { Navigate, useLocation } from 'react-router-dom'
import { ErrorPage } from '../features/errors/ErrorPage'
import { reactPath } from './legacy-paths'

export function LegacyRedirect() {
  const location = useLocation()
  const target = reactPath(location.pathname)
  if (target === location.pathname) return <ErrorPage status={404} />
  return <Navigate to={target} replace />
}

export function LegacyStaffAlias() {
  const location = useLocation()
  const target = reactPath(location.pathname)
  if (target.startsWith('/admin') && target !== location.pathname) return <Navigate to={target} replace />
  return <ErrorPage status={404} />
}

export function PrefixedRedirect() {
  const location = useLocation()
  return <Navigate to={`/admin${location.pathname}${location.search}`} replace />
}
