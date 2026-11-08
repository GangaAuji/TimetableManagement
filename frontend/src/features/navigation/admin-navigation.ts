import { deviceRoles, pagePermission, type PagePermission } from '../../app/page-access'

export type NavLink = {
  label: string
  icon: string
  href: string
  active?: boolean
  primary?: boolean
  permission?: PagePermission
  roles?: readonly string[]
}

export type NavMenu = {
  label: string
  icon: string
  children: NavLink[]
}

export type NavGroup = {
  title: string
  links?: NavLink[]
  menus?: NavMenu[]
}

export function adminNavigation(pathname: string): NavGroup[] {
  const exact = (href: string) => pathname === `/admin${href === '/' ? '' : href}`
  const within = (href: string) => {
    const full = href === '/' ? '/admin' : `/admin${href}`
    return pathname === full || pathname.startsWith(`${full}/`)
  }
  return [
    {
      title: '',
      links: [{ label: 'Dashboard', icon: 'fa-tachometer-alt', href: '/admin', active: exact('/'), primary: true }],
    },
    {
      title: 'People',
      links: [
        { label: 'Students', icon: 'fa-user-graduate', href: '/admin/students', active: within('/students'), permission: pagePermission.students },
        { label: 'Faculty', icon: 'fa-chalkboard-teacher', href: '/admin/faculty', active: within('/faculty'), permission: pagePermission.faculty },
      ],
    },
    {
      title: 'Teaching',
      links: [
        { label: 'Reports', icon: 'fa-chart-pie', href: '/admin/reports', active: within('/reports'), permission: pagePermission.reports },
      ],
      menus: [
        {
          label: 'Timetable',
          icon: 'fa-calendar-week',
          children: [
            { label: 'View timetable', icon: 'fa-calendar-week', href: '/admin/timetable', active: exact('/timetable'), permission: pagePermission.timetable },
            { label: 'Generate', icon: 'fa-cogs', href: '/admin/timetable/generate', active: within('/timetable/generate'), permission: pagePermission.generate },
            { label: 'Rooms', icon: 'fa-door-open', href: '/admin/rooms', active: within('/rooms'), permission: pagePermission.rooms },
            { label: 'Holidays', icon: 'fa-umbrella-beach', href: '/admin/holidays', active: within('/holidays'), permission: pagePermission.holidays },
          ],
        },
        {
          label: 'Attendance',
          icon: 'fa-user-check',
          children: [
            { label: 'Overview', icon: 'fa-chart-line', href: '/admin/attendance', active: exact('/attendance'), permission: pagePermission.attendance },
            { label: 'Records', icon: 'fa-list', href: '/admin/attendance/manage', active: exact('/attendance/manage'), permission: pagePermission.attendanceRecords },
            { label: 'Faculty attendance', icon: 'fa-user-tie', href: '/admin/attendance/faculty', active: exact('/attendance/faculty'), permission: pagePermission.facultyAttendance },
            { label: 'Mobile logs', icon: 'fa-mobile-alt', href: '/admin/attendance/mobile', active: exact('/attendance/mobile'), permission: pagePermission.attendance },
          ],
        },
        {
          label: 'Scheduling',
          icon: 'fa-clock',
          children: [
            { label: 'Shifts', icon: 'fa-clock', href: '/admin/shifts', active: exact('/shifts'), permission: pagePermission.shifts },
            { label: 'Shift requests', icon: 'fa-exchange-alt', href: '/admin/shifts/requests', active: exact('/shifts/requests'), permission: pagePermission.shifts },
            { label: 'Availability', icon: 'fa-calendar-check', href: '/admin/shifts/availability', active: exact('/shifts/availability'), permission: pagePermission.shifts },
            { label: 'Proxy log', icon: 'fa-user-clock', href: '/admin/proxy', active: within('/proxy'), permission: pagePermission.proxy },
          ],
        },
      ],
    },
    {
      title: 'Setup',
      menus: [
        {
          label: 'Academics',
          icon: 'fa-book',
          children: [
            { label: 'Departments', icon: 'fa-university', href: '/admin/departments', active: within('/departments'), permission: pagePermission.departments },
            { label: 'Courses', icon: 'fa-book-open', href: '/admin/courses', active: within('/courses'), permission: pagePermission.courses },
            { label: 'Academic years', icon: 'fa-calendar-alt', href: '/admin/academic-years', active: within('/academic-years'), permission: pagePermission.years },
            { label: 'Semesters', icon: 'fa-hourglass-half', href: '/admin/semesters', active: within('/semesters'), permission: pagePermission.semesters },
            { label: 'Batches', icon: 'fa-layer-group', href: '/admin/batches', active: within('/batches'), permission: pagePermission.batches },
            { label: 'Subjects', icon: 'fa-swatchbook', href: '/admin/subjects', active: within('/subjects'), permission: pagePermission.subjects },
            { label: 'Faculty allocations', icon: 'fa-tasks', href: '/admin/allocations', active: within('/allocations'), permission: pagePermission.allocations },
          ],
        },
      ],
    },
    {
      title: 'Administration',
      links: [
        { label: 'Users', icon: 'fa-users', href: '/admin/users', active: within('/users'), permission: pagePermission.users },
        { label: 'Invitations', icon: 'fa-envelope-open-text', href: '/admin/invitations', active: within('/invitations'), permission: pagePermission.invitations },
        { label: 'Roles', icon: 'fa-user-shield', href: '/admin/roles', active: within('/roles'), permission: pagePermission.roles },
        { label: 'Permissions', icon: 'fa-key', href: '/admin/permissions', active: exact('/permissions'), permission: pagePermission.permissions },
        { label: 'Mobile devices', icon: 'fa-mobile-alt', href: '/admin/devices', active: within('/devices'), roles: deviceRoles },
        { label: 'Settings', icon: 'fa-palette', href: '/admin/settings', active: within('/settings'), permission: pagePermission.settings },
        { label: 'Audit', icon: 'fa-shield-alt', href: '/admin/audit', active: within('/audit'), permission: pagePermission.audit },
      ],
    },
  ]
}

export function portalNavigation(role: string, pathname: string): NavGroup[] {
  const active = (href: string) => (href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`))
  const home = { label: 'Dashboard', icon: 'fa-home', href: '/', active: active('/'), primary: true }
  if (role === 'Teacher') {
    return [
      {
        title: 'Today',
        links: [
          { ...home, icon: 'fa-tachometer-alt' },
          { label: 'Timetable', icon: 'fa-calendar-alt', href: '/my-timetable', active: active('/my-timetable') },
          { label: 'Attendance', icon: 'fa-user-check', href: '/my-attendance', active: active('/my-attendance') },
        ],
      },
      {
        title: 'My classes',
        links: [
          { label: 'Classes', icon: 'fa-user-graduate', href: '/my-classes', active: active('/my-classes') },
          { label: 'Assigned subjects', icon: 'fa-book-open', href: '/my-assignments', active: active('/my-assignments') },
          { label: 'Availability', icon: 'fa-clipboard-check', href: '/my-availability', active: active('/my-availability') },
          { label: 'Proxy requests', icon: 'fa-user-clock', href: '/my-proxy', active: active('/my-proxy') },
          { label: 'Shifts', icon: 'fa-clock', href: '/my-shifts', active: active('/my-shifts') },
        ],
      },
    ]
  }
  return [
    {
      title: '',
      links: [
        home,
        { label: 'My timetable', icon: 'fa-calendar-alt', href: '/my-timetable', active: active('/my-timetable') },
        { label: 'Attendance', icon: 'fa-clipboard-check', href: '/my-attendance', active: active('/my-attendance') },
      ],
    },
  ]
}
