import { Navigate, useLocation, useOutletContext } from 'react-router-dom'
import { canOpenStaffHome } from '../../app/page-access'
import { useSessionRole } from '../../shared/components/data-list'
import type { SessionInfo } from '../../shared/api/endpoints'
import { DashboardRoute } from '../dashboard/pages/DashboardPage'
import { StudentDashboard, TeacherDashboard } from '../teacher/pages/TeacherHome'

export function RoleHome() {
  const role = useSessionRole()
  const location = useLocation()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  if (role !== 'Student' && role !== 'Teacher' && location.pathname === '/') return <Navigate to="/admin" replace />
  if (role === 'Student') return <StudentDashboard />
  if (role === 'Teacher') return <TeacherDashboard />
  if (!canOpenStaffHome(session)) {
    return (
      <section className="mx-auto max-w-lg rounded-2xl border border-gray-200 bg-white px-6 py-10 text-center shadow-sm">
        <h2 className="text-base font-bold text-gray-800">Welcome</h2>
        <p className="mt-2 text-sm text-gray-500">Open a page from the menu. Each item is limited to the permissions on this account.</p>
      </section>
    )
  }
  return <DashboardRoute />
}
