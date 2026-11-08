import type { Branding, DashboardSummary, SessionInfo, TodayClass } from '../api/endpoints'

const hexColor = /^#[0-9A-Fa-f]{6}$/
const assetPath = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$/
const csrfToken = /^[A-Za-z0-9._\-=]{16,400}$/
const roleName = /^[A-Za-z][A-Za-z0-9 _-]{0,49}$/
const permissionName = /^[a-z0-9_]{1,80}$/
const weekDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export const fallbackBranding: Branding = {
  site_title: 'Timetable Management System',
  login_title: 'Welcome Back',
  admin_title: 'Admin Dashboard',
  tagline: 'Efficient Scheduling Made Simple',
  copyright_text: '© 2025',
  welcome_message: 'Welcome to our academic management system',
  footer_text: 'Powered by Timetable Management System',
  site_logo: '',
  login_logo: '',
  favicon: '',
  login_background: '',
  admin_login_background: '',
  register_background: '',
  primary_color: '#059669',
  secondary_color: '#10b981',
  accent_color: '#047857',
  sidebar_bg: '#111827',
  header_bg: '#ffffff',
  institution_name: 'College Timetable System',
  institution_short_name: 'ACADEMIA',
}

export function safeText(value: unknown, limit: number): string {
  if (typeof value !== 'string' && typeof value !== 'number') return ''
  return String(value)
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .trim()
    .slice(0, limit)
}

export function safeColor(value: unknown, fallback: string): string {
  const text = safeText(value, 7)
  return hexColor.test(text) ? text : fallback
}

export function safeAsset(value: unknown): string {
  const text = safeText(value, 180)
  if (!text || text.startsWith('/') || text.includes('..') || text.includes('\\') || text.includes('://')) return ''
  return assetPath.test(text) ? text : ''
}

export function staticAssetUrl(value: unknown): string {
  const asset = safeAsset(value)
  return asset ? `/static/${asset}` : ''
}

export function safeCount(value: unknown): number {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number) || number < 0) return 0
  return Math.min(Math.floor(number), 1_000_000)
}

export function sanitizeBranding(input: Partial<Branding> | null | undefined): Branding {
  const source = input ?? {}
  return {
    site_title: safeText(source.site_title, 80) || fallbackBranding.site_title,
    login_title: safeText(source.login_title, 80) || fallbackBranding.login_title,
    admin_title: safeText(source.admin_title, 80) || fallbackBranding.admin_title,
    tagline: safeText(source.tagline, 160) || fallbackBranding.tagline,
    copyright_text: safeText(source.copyright_text, 120) || fallbackBranding.copyright_text,
    welcome_message: safeText(source.welcome_message, 240) || fallbackBranding.welcome_message,
    footer_text: safeText(source.footer_text, 160) || fallbackBranding.footer_text,
    site_logo: safeAsset(source.site_logo),
    login_logo: safeAsset(source.login_logo),
    favicon: safeAsset(source.favicon),
    login_background: safeAsset(source.login_background),
    admin_login_background: safeAsset(source.admin_login_background),
    register_background: safeAsset(source.register_background),
    primary_color: safeColor(source.primary_color, fallbackBranding.primary_color),
    secondary_color: safeColor(source.secondary_color, fallbackBranding.secondary_color),
    accent_color: safeColor(source.accent_color, fallbackBranding.accent_color),
    sidebar_bg: safeColor(source.sidebar_bg, fallbackBranding.sidebar_bg),
    header_bg: safeColor(source.header_bg, fallbackBranding.header_bg),
    institution_name: safeText(source.institution_name, 160) || fallbackBranding.institution_name,
    institution_short_name: safeText(source.institution_short_name, 40) || fallbackBranding.institution_short_name,
  }
}

export function sanitizeSession(input: Partial<SessionInfo> | null | undefined): SessionInfo {
  if (!input || input.authenticated !== true) return { authenticated: false }
  const role = roleName.test(input.role ?? '') ? (input.role as string) : ''
  const permissions = Array.isArray(input.permissions)
    ? input.permissions.filter((item): item is string => typeof item === 'string' && permissionName.test(item)).slice(0, 400)
    : []
  return {
    authenticated: true,
    username: safeText(input.username, 80) || 'User',
    role,
    profile_photo: safeAsset(input.profile_photo) || 'default-avatar.svg',
    unrestricted: input.unrestricted === true && role === 'Super Admin',
    permissions,
  }
}

export function sanitizeCsrfToken(value: unknown): string {
  const token = typeof value === 'string' ? value : ''
  return csrfToken.test(token) ? token : ''
}

function sanitizeClass(input: Partial<TodayClass> | null | undefined): TodayClass {
  const source = input ?? {}
  return {
    start_time: safeText(source.start_time, 20),
    end_time: safeText(source.end_time, 20),
    subject_name: safeText(source.subject_name, 160),
    faculty_name: safeText(source.faculty_name, 160),
    room_number: safeText(source.room_number, 40),
    class_name: safeText(source.class_name, 120),
    division_name: safeText(source.division_name, 80),
    session_type: safeText(source.session_type, 40),
  }
}

export function sanitizeDashboard(input: Partial<DashboardSummary> | null | undefined): DashboardSummary {
  const source = input ?? {}
  const weeklyLoad: Record<string, number> = {}
  for (const day of weekDays) {
    weeklyLoad[day] = safeCount(source.weekly_load?.[day])
  }

  const sessionTypes: Record<string, number> = {}
  const rawTypes = source.session_types
  if (rawTypes && typeof rawTypes === 'object') {
    for (const [name, count] of Object.entries(rawTypes)) {
      const label = safeText(name, 40)
      if (label) sessionTypes[label] = safeCount(count)
    }
  }

  const classes = Array.isArray(source.today_classes) ? source.today_classes.slice(0, 50).map((row) => sanitizeClass(row)) : []

  return {
    today_day: safeText(source.today_day, 40) || 'Today',
    total_students: safeCount(source.total_students),
    total_faculty: safeCount(source.total_faculty),
    total_courses: safeCount(source.total_courses),
    total_departments: safeCount(source.total_departments),
    total_rooms: safeCount(source.total_rooms),
    total_batches: safeCount(source.total_batches),
    classroom_count: safeCount(source.classroom_count),
    laboratory_count: safeCount(source.laboratory_count),
    weekly_load: weeklyLoad,
    session_types: sessionTypes,
    today_classes: classes,
  }
}

const allowedPathPrefixes = ['/admin', '/admin/', '/teacher/', '/student/', '/profile', '/logout', '/login', '/register', '/rooms', '/departments', '/courses', '/academics', '/academic-years', '/semesters', '/subjects', '/batches', '/allocations', '/holidays', '/students', '/faculty', '/users', '/roles', '/invitations', '/settings', '/audit', '/timetable', '/attendance', '/reports', '/shifts', '/proxy', '/devices', '/account', '/my-timetable', '/my-classes', '/my-shifts', '/my-availability', '/my-proxy', '/my-attendance']

export function appPath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\') || path.includes('..') || path.includes('://')) {
    return '/'
  }
  const allowed = path === '/' || allowedPathPrefixes.some((prefix) => path === prefix || path.startsWith(prefix))
  return allowed ? path : '/'
}
