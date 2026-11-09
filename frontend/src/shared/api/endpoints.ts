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

export function getBranding() {
  return apiGet<Branding>('/api/branding').then((data) => sanitizeBranding(data))
}

export type SessionInfo =
  | { authenticated: false }
  | { authenticated: true; username: string; role: string; profile_photo: string; unrestricted: boolean; permissions: string[] }

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
