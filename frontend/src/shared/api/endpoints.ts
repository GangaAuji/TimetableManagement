import { ApiError, apiGet } from './client'
import { sanitizeBranding, sanitizeCsrfToken, sanitizeDashboard, sanitizeSession } from '../security/sanitize'

export type Branding = {
  site_title: string
  login_title: string
  admin_title: string
  tagline: string
  copyright_text: string
  welcome_message: string
  footer_text: string
  maintenance_title: string
  maintenance_message: string
  support_email: string
  support_phone: string
  site_logo: string
  login_logo: string
  favicon: string
  login_background: string
  admin_login_background: string
  register_background: string
  primary_color: string
  secondary_color: string
  accent_color: string
  sidebar_bg: string
  header_bg: string
  institution_name: string
  institution_short_name: string
}

export function getBranding(institutionCode = '') {
  const code = institutionCode.trim()
  const query = /^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$/.test(code) ? `?i=${encodeURIComponent(code)}` : ''
  return apiGet<Branding>(`/api/branding${query}`).then((data) => sanitizeBranding(data))
}

export type SessionInstitution = { id: number; name: string; code: string; short_name: string }

export type SessionInfo =
  | { authenticated: false; maintenance: boolean }
  | {
      authenticated: true
      maintenance: boolean
      username: string
      role: string
      profile_photo: string
      unrestricted: boolean
      permissions: string[]
      /** The institution this session works in; null for a Super Admin viewing the whole organization. */
      institution: SessionInstitution | null
      /** Institutions the user may switch to; empty when the tenant has one institution. */
      institutions: SessionInstitution[]
      organization_wide: boolean
      /** Optional features that are on for this tenant (server flag AND tenant switch). Missing = off. */
      capabilities: Record<string, boolean>
      /** True when the security policy requires a new password before the rest of the app opens. */
      password_expired: boolean
      /** Set for staff when the installation license is required and not acceptable. */
      license_problem: string
    }

/** True when the session is signed in and the named capability is on. */
export function hasCapability(session: SessionInfo, name: string): boolean {
  return session.authenticated && session.capabilities[name] === true
}

export function getSession() {
  return apiGet<SessionInfo>('/api/session').then((data) => sanitizeSession(data))
}

export async function getCsrfToken() {
  const data = await apiGet<{ csrf_token: string }>('/api/csrf-token')
  const token = sanitizeCsrfToken(data?.csrf_token)
  if (!token) {
    throw new ApiError('The request could not be completed.', 0)
  }
  return { csrf_token: token }
}

export type TodayClass = {
  start_time: string
  end_time: string
  subject_name: string
  faculty_name: string
  room_number: string
  class_name: string
  division_name: string
  session_type: string
}

export type AttendanceTrend = {
  date: string
  present: number
  late: number
  absent: number
  percentage: number | null
}

export type DashboardSummary = {
  today_day: string
  total_students: number
  total_faculty: number
  total_courses: number
  total_departments: number
  total_rooms: number
  total_batches: number
  classroom_count: number
  laboratory_count: number
  weekly_load: Record<string, number>
  session_types: Record<string, number>
  today_classes: TodayClass[]
  attendance: {
    present: number
    late: number
    absent: number
    excused: number
    not_marked: number
    countable: number
    lectures: number
    students: number
    percentage: number | null
    threshold: number
    defaulters: number
    unmarked_lectures: number
    trend: AttendanceTrend[]
  }
  pending_shifts: number
  unassigned_proxy: number
  pending_proxy: number
  pending_invitations: number
  departments: { name: string; students: number }[]
  workload: { name: string; classes: number; hours: number }[]
  holidays: { name: string; date: string }[]
}

export function getDashboardSummary() {
  return apiGet<DashboardSummary>('/api/dashboard/summary').then((data) => sanitizeDashboard(data))
}
