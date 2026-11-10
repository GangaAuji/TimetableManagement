import { deviceRoles, pagePermission, type PagePermission } from '../../app/page-access'

export type NavLink = {
  label: string
  icon: string
  href: string
  active?: boolean
  primary?: boolean
  permission?: PagePermission
  roles?: readonly string[]
  /** Optional feature this page belongs to. The menu still lists it; the page stays empty while the feature is off. */
  capability?: string
}

export type NavMenu = {
  label: string
  icon: string
  children: NavLink[]
}

export type NavEntry = NavLink | NavMenu

export type NavGroup = {
  title: string
  /** Ordered mix of links and menus. When omitted, menus are shown, then links. */
  items?: NavEntry[]
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
      title: 'Teaching',
      items: [
        {
          label: 'Timetable',
          icon: 'fa-calendar-week',
          children: [
            { label: 'View timetable', icon: 'fa-calendar-week', href: '/admin/timetable', active: exact('/timetable'), permission: pagePermission.timetable },
            { label: 'Generate', icon: 'fa-cogs', href: '/admin/timetable/generate', active: within('/timetable/generate'), permission: pagePermission.generate },
            { label: 'Versions', icon: 'fa-code-branch', href: '/admin/timetable/versions', active: within('/timetable/versions'), permission: pagePermission.versions, capability: 'timetable_versions' },
            { label: 'Rules', icon: 'fa-sliders-h', href: '/admin/timetable/rules', active: within('/timetable/rules'), permission: pagePermission.rules, capability: 'timetable_preferences' },
            { label: 'Workload norms', icon: 'fa-balance-scale', href: '/admin/timetable/workload', active: within('/timetable/workload'), permission: pagePermission.workload, capability: 'workload_norms' },
            { label: 'Rooms', icon: 'fa-door-open', href: '/admin/rooms', active: exact('/rooms'), permission: pagePermission.rooms },
            { label: 'Bookings', icon: 'fa-calendar-check', href: '/admin/rooms/bookings', active: within('/rooms/bookings'), permission: pagePermission.bookings, capability: 'bookings' },
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
        { label: 'Reports', icon: 'fa-chart-pie', href: '/admin/reports', active: within('/reports'), permission: pagePermission.reports },
      ],
    },
    {
      title: 'People',
      links: [
        { label: 'Students', icon: 'fa-user-graduate', href: '/admin/students', active: within('/students'), permission: pagePermission.students },
        { label: 'Faculty', icon: 'fa-chalkboard-teacher', href: '/admin/faculty', active: within('/faculty'), permission: pagePermission.faculty },
      ],
    },
    {
      title: 'Academics',
      items: [
        {
          label: 'Structure',
          icon: 'fa-sitemap',
          children: [
            { label: 'Departments', icon: 'fa-university', href: '/admin/departments', active: within('/departments'), permission: pagePermission.departments },
            { label: 'Courses', icon: 'fa-book-open', href: '/admin/courses', active: within('/courses'), permission: pagePermission.courses },
            { label: 'Academic years', icon: 'fa-calendar-alt', href: '/admin/academic-years', active: within('/academic-years'), permission: pagePermission.years },
            { label: 'Semesters', icon: 'fa-hourglass-half', href: '/admin/semesters', active: within('/semesters'), permission: pagePermission.semesters },
            { label: 'Calendar', icon: 'fa-calendar-day', href: '/admin/academic-terms', active: within('/academic-terms'), permission: pagePermission.calendar, capability: 'academic_terms' },
            { label: 'Holidays', icon: 'fa-umbrella-beach', href: '/admin/holidays', active: within('/holidays'), permission: pagePermission.holidays },
            { label: 'Batches', icon: 'fa-layer-group', href: '/admin/batches', active: within('/batches'), permission: pagePermission.batches },
            { label: 'Lab batches', icon: 'fa-flask', href: '/admin/lab-batches', active: within('/lab-batches'), permission: pagePermission.batches },
          ],
        },
        {
          label: 'Curriculum',
          icon: 'fa-book',
          children: [
            { label: 'Subjects', icon: 'fa-swatchbook', href: '/admin/subjects', active: within('/subjects'), permission: pagePermission.subjects },
            { label: 'Syllabus', icon: 'fa-list-ol', href: '/admin/academic-syllabus', active: within('/academic-syllabus'), permission: pagePermission.syllabus, capability: 'syllabus' },
            { label: 'Faculty allocations', icon: 'fa-tasks', href: '/admin/allocations', active: within('/allocations'), permission: pagePermission.allocations },
            { label: 'Internals', icon: 'fa-clipboard-list', href: '/admin/academic-assessments', active: within('/academic-assessments'), permission: pagePermission.assessments, capability: 'assessments' },
            { label: 'Exams', icon: 'fa-file-alt', href: '/admin/academic-exams', active: within('/academic-exams'), permission: pagePermission.exams, capability: 'exams' },
          ],
        },
      ],
    },
    {
      title: 'Administration',
      items: [
        { label: 'Users', icon: 'fa-users', href: '/admin/users', active: within('/users'), permission: pagePermission.users },
        { label: 'Invitations', icon: 'fa-envelope-open-text', href: '/admin/invitations', active: within('/invitations'), permission: pagePermission.invitations },
        { label: 'Roles', icon: 'fa-user-shield', href: '/admin/roles', active: within('/roles'), permission: pagePermission.roles },
        { label: 'Permissions', icon: 'fa-key', href: '/admin/permissions', active: exact('/permissions'), permission: pagePermission.permissions },
        { label: 'Mobile devices', icon: 'fa-mobile-alt', href: '/admin/devices', active: within('/devices'), roles: deviceRoles },
        {
          label: 'Settings',
          icon: 'fa-cog',
          children: [
            { label: 'Institutions', icon: 'fa-building', href: '/admin/settings/institutions', active: within('/settings/institutions'), permission: pagePermission.institutions },
            { label: 'Branding', icon: 'fa-palette', href: '/admin/settings', active: exact('/settings'), permission: pagePermission.settings },
            { label: 'Notifications', icon: 'fa-bell', href: '/admin/settings/notifications', active: within('/settings/notifications'), permission: pagePermission.notifications },
            { label: 'Integrations', icon: 'fa-plug', href: '/admin/settings/integrations', active: within('/settings/integrations'), permission: pagePermission.integrations },
            { label: 'Capabilities', icon: 'fa-toggle-on', href: '/admin/settings/capabilities', active: within('/settings/capabilities'), permission: pagePermission.capabilities },
            { label: 'Security', icon: 'fa-lock', href: '/admin/settings/security', active: within('/settings/security'), permission: pagePermission.security },
          ],
        },
        { label: 'Audit', icon: 'fa-shield-alt', href: '/admin/audit', active: within('/audit'), permission: pagePermission.audit },
      ],
    },
  ]
}

export function portalNavigation(role: string, pathname: string, capabilities?: Readonly<Record<string, boolean>>): NavGroup[] {
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
          ...(capabilities?.assessments ? [{ label: 'Internals', icon: 'fa-clipboard-list', href: '/my-internals', active: active('/my-internals') }] : []),
          ...(capabilities?.exams ? [{ label: 'Exam duties', icon: 'fa-file-alt', href: '/my-duties', active: active('/my-duties') }] : []),
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
        ...(capabilities?.assessments ? [{ label: 'Internals', icon: 'fa-clipboard-list', href: '/my-internals', active: active('/my-internals') }] : []),
      ],
    },
  ]
}
