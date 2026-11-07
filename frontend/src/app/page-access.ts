export type AccessSession = {
  role: string
  unrestricted: boolean
  permissions: readonly string[]
}

export type PagePermission = string | readonly string[]

/**
 * Staff pages and the permission the matching API already requires.
 * A new page must be added here with that permission. An unlisted address
 * stays closed for every account except Super Admin.
 */
export const pagePermission = {
  students: 'students_view_student',
  faculty: 'faculty_view_faculty',
  departments: 'departments_view',
  years: 'academicyears_view',
  semesters: 'semesters_view',
  subjects: 'subjects_view_subject',
  courses: 'courses_view_course',
  batches: 'batches_view',
  allocations: 'allocations_view',
  holidays: 'holidays_view',
  rooms: 'rooms_view_room',
  timetable: 'timetable_change',
  generate: 'timetable_generate',
  proxy: 'faculty_view_proxy',
  shifts: 'shifts_view',
  reports: 'reports_view',
  attendance: 'attendance_view',
  attendanceRecords: 'attendance_manage',
  facultyAttendance: 'attendance_view_faculty',
  users: 'users_view_user',
  userAccess: 'users_change_user',
  roles: ['roles_view_role', 'roles_change_role'],
  permissions: ['roles_view_role', 'roles_change_role'],
  invitations: 'users_change_user',
  settings: 'admin_view_settings',
  audit: ['reports_view_audit', 'users_view_activity_log'],
} as const

export const deviceRoles = ['Admin', 'Super Admin'] as const
const staffHomeRoles = new Set(['Admin', 'Super Admin', 'HOD'])

const staffRules: { pattern: RegExp; permission?: PagePermission; roles?: readonly string[]; open?: boolean }[] = [
  { pattern: /^\/timetable\/generate$/, permission: pagePermission.generate },
  { pattern: /^\/timetable$/, permission: pagePermission.timetable },
  { pattern: /^\/attendance\/manage$/, permission: pagePermission.attendanceRecords },
  { pattern: /^\/attendance\/faculty$/, permission: pagePermission.facultyAttendance },
  { pattern: /^\/attendance\/mobile$/, permission: pagePermission.attendance },
  { pattern: /^\/attendance$/, permission: pagePermission.attendance },
  { pattern: /^\/shifts\/requests$/, permission: pagePermission.shifts },
  { pattern: /^\/shifts\/availability$/, permission: pagePermission.shifts },
  { pattern: /^\/shifts$/, permission: pagePermission.shifts },
  { pattern: /^\/users\/[^/]+\/permissions$/, permission: pagePermission.userAccess },
  { pattern: /^\/users$/, permission: pagePermission.users },
  { pattern: /^\/permissions$/, permission: pagePermission.permissions },
  { pattern: /^\/roles(\/|$)/, permission: pagePermission.roles },
  { pattern: /^\/faculty(\/|$)/, permission: pagePermission.faculty },
  { pattern: /^\/reports(\/|$)/, permission: pagePermission.reports },
  { pattern: /^\/students$/, permission: pagePermission.students },
  { pattern: /^\/departments$/, permission: pagePermission.departments },
  { pattern: /^\/academic-years$/, permission: pagePermission.years },
  { pattern: /^\/semesters$/, permission: pagePermission.semesters },
  { pattern: /^\/subjects$/, permission: pagePermission.subjects },
  { pattern: /^\/courses$/, permission: pagePermission.courses },
  { pattern: /^\/batches$/, permission: pagePermission.batches },
  { pattern: /^\/allocations$/, permission: pagePermission.allocations },
  { pattern: /^\/holidays$/, permission: pagePermission.holidays },
  { pattern: /^\/rooms$/, permission: pagePermission.rooms },
  { pattern: /^\/proxy$/, permission: pagePermission.proxy },
  { pattern: /^\/invitations$/, permission: pagePermission.invitations },
  { pattern: /^\/settings$/, permission: pagePermission.settings },
  { pattern: /^\/audit(\/|$)/, permission: pagePermission.audit },
  { pattern: /^\/devices$/, roles: deviceRoles },
  { pattern: /^\/account$/, open: true },
  { pattern: /^\/$/, open: true },
]

const teacherPaths = /^\/(my-timetable|my-classes|my-shifts|my-availability|my-proxy|my-attendance(?:\/(?:mark|history)\/\d+)?|account|profile)$/
const studentPaths = /^\/(my-timetable|my-attendance(?:\/\d+)?|account|profile)$/
const legacyPaths = /^\/(login|teacher|student|profile)(\/|$)/
const formerStaffPaths = /^\/(rooms|departments|courses|academics|academic-years|semesters|subjects|batches|allocations|holidays|students|faculty|users|permissions|roles|invitations|settings|audit|timetable|attendance|reports|shifts|proxy|devices)(\/|$)/

export function hasPermission(session: AccessSession, permission?: PagePermission) {
  if (!permission) return false
  if (session.unrestricted) return true
  const names = typeof permission === 'string' ? [permission] : permission
  return names.some((name) => session.permissions.includes(name))
}

export function linkVisible(session: AccessSession, link: { permission?: PagePermission; roles?: readonly string[] }) {
  if (session.unrestricted) return true
  if (link.roles && !link.roles.includes(session.role)) return false
  if (link.permission) return hasPermission(session, link.permission)
  return true
}

export function canOpenStaffHome(session: AccessSession) {
  return session.unrestricted || staffHomeRoles.has(session.role)
}

function staffDecision(inner: string, session: AccessSession) {
  if (session.unrestricted) return true
  const rule = staffRules.find((item) => item.pattern.test(inner))
  if (!rule) return false
  if (rule.open) return true
  if (rule.roles && !rule.roles.includes(session.role)) return false
  if (rule.permission) return hasPermission(session, rule.permission)
  return Boolean(rule.roles)
}

export function canOpenPage(pathname: string, session: AccessSession) {
  const path = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
  if (path === '/login' || path === '/admin/login') return true
  if (legacyPaths.test(path) || formerStaffPaths.test(path)) return true
  if (path === '/admin' || path.startsWith('/admin/')) {
    if (session.role === 'Teacher' || session.role === 'Student') return false
    return staffDecision(path === '/admin' ? '/' : path.slice('/admin'.length), session)
  }
  if (session.role === 'Teacher') return path === '/' || teacherPaths.test(path)
  if (session.role === 'Student') return path === '/' || studentPaths.test(path)
  if (/^\/my-/.test(path)) return false
  return path === '/' || path === '/account' || path === '/profile'
}
