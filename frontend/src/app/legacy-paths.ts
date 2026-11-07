const exact: Record<string, string> = {
  '/login': '/',
  '/admin': '/admin',
  '/admin/login': '/admin/login',
  '/admin/dashboard': '/admin',
  '/profile': '/account',
  '/profile/edit': '/account',
  '/profile/change-password': '/account',
  '/teacher': '/',
  '/teacher/dashboard': '/',
  '/teacher/timetable': '/my-timetable',
  '/teacher/my-classes': '/my-classes',
  '/teacher/my-shifts': '/my-shifts',
  '/teacher/availability': '/my-availability',
  '/teacher/proxy-requests': '/my-proxy',
  '/teacher/attendance': '/my-attendance',
  '/teacher/attendance/report': '/my-attendance',
  '/student': '/',
  '/student/dashboard': '/',
  '/student/timetable': '/my-timetable',
  '/student/attendance': '/my-attendance',
  '/admin/rooms': '/admin/rooms',
  '/admin/departments': '/admin/departments',
  '/admin/courses': '/admin/courses',
  '/admin/academic': '/admin/academic-years',
  '/admin/academic/years': '/admin/academic-years',
  '/admin/academic/semesters': '/admin/semesters',
  '/admin/academic/subjects': '/admin/subjects',
  '/admin/academic/batches': '/admin/batches',
  '/admin/academic/allocations': '/admin/allocations',
  '/admin/holidays': '/admin/holidays',
  '/admin/students': '/admin/students',
  '/admin/students/bulk-invite': '/admin/invitations',
  '/admin/faculty': '/admin/faculty',
  '/admin/users': '/admin/users',
  '/admin/users/roles': '/admin/roles',
  '/admin/users/activity-log': '/admin/audit',
  '/admin/invitations': '/admin/invitations',
  '/admin/settings': '/admin/settings',
  '/admin/branding': '/admin/settings',
  '/admin/audit-logs': '/admin/audit',
  '/admin/timetable': '/admin/timetable',
  '/admin/timetable/generate': '/admin/timetable/generate',
  '/admin/attendance': '/admin/attendance',
  '/admin/attendance/defaulters': '/admin/attendance',
  '/admin/attendance/manage': '/admin/attendance/manage',
  '/admin/attendance/faculty': '/admin/attendance/faculty',
  '/admin/attendance/mobile-logs': '/admin/attendance/mobile',
  '/admin/attendance/faculty-mobile-logs': '/admin/attendance/mobile',
  '/admin/reports': '/admin/reports',
  '/admin/reports/attendance': '/admin/reports',
  '/admin/reports/timetable': '/admin/reports',
  '/admin/reports/audit-logs': '/admin/reports',
  '/admin/reports/shifts': '/admin/reports',
  '/admin/reports/proxy-log': '/admin/reports',
  '/admin/reports/invitations': '/admin/reports',
  '/admin/shifts': '/admin/shifts',
  '/admin/shifts/change-requests': '/admin/shifts/requests',
  '/admin/shifts/faculty-availability': '/admin/shifts/availability',
  '/admin/proxy': '/admin/proxy',
  '/admin/proxy-log': '/admin/proxy',
  '/admin/mobile-devices': '/admin/devices',
  '/admin/devices': '/admin/devices',
}

export function reactPath(pathname: string): string {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (exact[path]) return exact[path]
  const faculty = /^\/admin\/faculty\/(\d+)\/(details|sessions|availability|absences|proxy-log)$/.exec(path)
  if (faculty) {
    if (faculty[2] === 'details' || faculty[2] === 'sessions') return `/admin/faculty/${faculty[1]}`
    if (faculty[2] === 'availability') return '/admin/shifts/availability'
    return '/admin/proxy'
  }
  const role = /^\/admin\/users\/roles\/(\d+)\/permissions$/.exec(path)
  if (role) return `/admin/roles/${role[1]}`
  if (path.startsWith('/admin/users/permissions/')) {
    const userId = path.split('/').pop()
    return userId && /^\d+$/.test(userId) ? `/admin/users/${userId}/permissions` : '/admin/users'
  }
  if (/^\/admin\/attendance\/student\/\d+$/.test(path)) return '/admin/attendance'
  if (/^\/admin\/attendance\/faculty\/\d+$/.test(path)) return '/admin/attendance/faculty'
  if (/^\/admin\/audit-logs\/details\/\d+$/.test(path)) return '/admin/audit'
  if (/^\/admin\/audit-logs\/user-activity\/\d+$/.test(path)) return '/admin/audit'
  if (/^\/student\/attendance\/subject\/\d+$/.test(path)) return '/my-attendance'
  if (/^\/teacher\/attendance\//.test(path)) return '/my-attendance'
  return '/'
}
