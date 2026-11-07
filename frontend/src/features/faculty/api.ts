import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { safeCount, safeText } from '../../shared/security/sanitize'

export type FacultyPermissions = { add: boolean; change: boolean; delete: boolean; invite: boolean }
export type FacultyOption = { id: number; name: string }
export type FacultyRecord = {
  id: number
  name: string
  email: string
  phone: string
  username: string
  employee_id: string
  designation: string
  department_id: number
  department_name: string
  is_active: boolean
}
export type FacultyDraft = {
  username: string
  password: string
  name: string
  email: string
  phone: string
  designation: string
  employee_id: string
  department_id: number | null
  is_active: boolean
}
export type FacultyList = {
  faculty: FacultyRecord[]
  page: number
  totalPages: number
  total: number
  totalActive: number
  totalInactive: number
  departments: FacultyOption[]
  permissions: FacultyPermissions
}

export const emptyFacultyPermissions: FacultyPermissions = { add: false, change: false, delete: false, invite: false }

function asId(value: unknown) {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

function record(value: Partial<FacultyRecord> | undefined): FacultyRecord {
  return {
    id: asId(value?.id),
    name: safeText(value?.name, 100),
    email: safeText(value?.email, 100),
    phone: safeText(value?.phone, 20),
    username: safeText(value?.username, 50),
    employee_id: safeText(value?.employee_id, 20),
    designation: safeText(value?.designation, 50),
    department_id: asId(value?.department_id),
    department_name: safeText(value?.department_name, 100),
    is_active: value?.is_active === true,
  }
}

async function send(method: 'POST' | 'PUT', path: string, payload: object) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload),
  })
}

export type FacultyQueryFields = {
  name: string
  email: string
  designation: string
  username: string
  sort: string
  order: 'ASC' | 'DESC'
}

export async function getFaculty(search: string, department: string, page: number, perPage: number, fields: FacultyQueryFields): Promise<FacultyList> {
  const params = new URLSearchParams()
  if (search) params.set('search', search.slice(0, 100))
  if (fields.name) params.set('name', fields.name.slice(0, 100))
  if (fields.username) params.set('username', fields.username.slice(0, 100))
  if (fields.email) params.set('email', fields.email.slice(0, 100))
  if (fields.designation) params.set('designation', fields.designation.slice(0, 100))
  if (fields.sort) params.set('sort', fields.sort)
  if (fields.order) params.set('order', fields.order)
  if (department) params.set('department', department)
  params.set('page', String(page > 0 ? page : 1))
  if (perPage > 0) params.set('per_page', String(perPage))
  const data = await apiRequest<{
    faculty?: Partial<FacultyRecord>[]
    page?: unknown
    total_pages?: unknown
    total?: unknown
    total_active?: unknown
    total_inactive?: unknown
    departments?: { id?: unknown; name?: unknown }[]
    permissions?: Partial<FacultyPermissions>
  }>(`/api/faculty?${params.toString()}`)
  return {
    faculty: Array.isArray(data.faculty) ? data.faculty.map(record).filter((row) => row.id > 0) : [],
    page: safeCount(data.page) || 1,
    totalPages: safeCount(data.total_pages),
    total: safeCount(data.total),
    totalActive: safeCount(data.total_active),
    totalInactive: safeCount(data.total_inactive),
    departments: Array.isArray(data.departments)
      ? data.departments.map((row) => ({ id: asId(row.id), name: safeText(row.name, 100) })).filter((row) => row.id > 0 && row.name)
      : [],
    permissions: {
      add: data.permissions?.add === true,
      change: data.permissions?.change === true,
      delete: data.permissions?.delete === true,
      invite: data.permissions?.invite === true,
    },
  }
}

export async function getFacultyMember(id: number) {
  return record(await apiRequest<Partial<FacultyRecord>>(`/api/faculty/${id}`))
}

function payload(draft: FacultyDraft, includeAccount: boolean) {
  const body: Record<string, unknown> = {
    name: draft.name,
    email: draft.email,
    phone: draft.phone,
    designation: draft.designation,
    department_id: draft.department_id,
    is_active: draft.is_active,
    password: draft.password,
  }
  if (includeAccount) {
    body.username = draft.username
    body.employee_id = draft.employee_id
  }
  return body
}

export function createFaculty(draft: FacultyDraft) {
  return send('POST', '/api/faculty', payload(draft, true))
}

export function updateFaculty(id: number, draft: FacultyDraft) {
  return send('PUT', `/api/faculty/${id}`, payload(draft, false))
}

export function deactivateFaculty(ids: number[]) {
  return send('POST', '/api/faculty/deactivate', { ids })
}

export async function invitationToken() {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return csrfToken
}
