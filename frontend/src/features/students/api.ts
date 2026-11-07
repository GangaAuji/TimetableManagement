import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { safeCount, safeText } from '../../shared/security/sanitize'

export type StudentPermissions = { add: boolean; change: boolean; delete: boolean; invite: boolean }
export type StudentOption = { id: number; name: string }
export type StudentRecord = {
  id: number
  name: string
  email: string
  phone: string
  roll_number: string
  course_id: number
  class_id: number
  division_id: number
  course_name: string
  class_name: string
  division_name: string
  username?: string
}
export type StudentDraft = {
  username: string
  password: string
  name: string
  email: string
  phone: string
  roll_number: string
  course_id: number | null
  class_id: number | null
  division_id: number | null
}
export type StudentQuery = {
  search: string
  course: string
  name: string
  roll: string
  courseName: string
  className: string
  email: string
  page: number
  perPage: number
  sort: string
  order: 'ASC' | 'DESC'
}
export type StudentList = {
  students: StudentRecord[]
  page: number
  totalPages: number
  total: number
  totalActive: number
  courses: StudentOption[]
  classes: StudentOption[]
  divisions: StudentOption[]
  permissions: StudentPermissions
}

const emptyPermissions: StudentPermissions = { add: false, change: false, delete: false, invite: false }

function asId(value: unknown) {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

function record(value: Partial<StudentRecord> | undefined, withUsername: boolean): StudentRecord {
  const row: StudentRecord = {
    id: asId(value?.id),
    name: safeText(value?.name, 100),
    email: safeText(value?.email, 100),
    phone: safeText(value?.phone, 20),
    roll_number: safeText(value?.roll_number, 50),
    course_id: asId(value?.course_id),
    class_id: asId(value?.class_id),
    division_id: asId(value?.division_id),
    course_name: safeText(value?.course_name, 100),
    class_name: safeText(value?.class_name, 100),
    division_name: safeText(value?.division_name, 100),
  }
  if (withUsername) row.username = safeText(value?.username, 50)
  return row
}

function options(value: unknown): StudentOption[] {
  if (!Array.isArray(value)) return []
  return value
    .map((row) => ({ id: asId(row?.id), name: safeText(row?.name, 100) }))
    .filter((row) => row.id > 0 && row.name)
}

function listPath(query: StudentQuery) {
  const params = new URLSearchParams()
  if (query.search) params.set('search', query.search.slice(0, 100))
  if (query.name) params.set('name', query.name.slice(0, 100))
  if (query.roll) params.set('roll', query.roll.slice(0, 100))
  if (query.courseName) params.set('course_name', query.courseName.slice(0, 100))
  if (query.className) params.set('class_name', query.className.slice(0, 100))
  if (query.email) params.set('email', query.email.slice(0, 100))
  if (query.course) params.set('course', query.course)
  params.set('page', String(query.page > 0 ? query.page : 1))
  if (query.perPage > 0) params.set('per_page', String(query.perPage))
  params.set('sort', query.sort)
  params.set('order', query.order)
  return `/api/students?${params.toString()}`
}

async function send(method: 'POST' | 'PUT', path: string, payload: object) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload),
  })
}

export async function getStudents(query: StudentQuery): Promise<StudentList> {
  const data = await apiRequest<{
    students?: Partial<StudentRecord>[]
    page?: unknown
    total_pages?: unknown
    total?: unknown
    total_active?: unknown
    courses?: unknown
    classes?: unknown
    divisions?: unknown
    permissions?: Partial<StudentPermissions>
  }>(listPath(query))
  return {
    students: Array.isArray(data.students) ? data.students.map((row) => record(row, false)).filter((row) => row.id > 0) : [],
    page: safeCount(data.page) || 1,
    totalPages: safeCount(data.total_pages),
    total: safeCount(data.total),
    totalActive: safeCount(data.total_active),
    courses: options(data.courses),
    classes: options(data.classes),
    divisions: options(data.divisions),
    permissions: {
      add: data.permissions?.add === true,
      change: data.permissions?.change === true,
      delete: data.permissions?.delete === true,
      invite: data.permissions?.invite === true,
    },
  }
}

export async function getStudent(id: number) {
  const data = await apiRequest<Partial<StudentRecord>>(`/api/students/${id}`)
  return record(data, true)
}

function payload(draft: StudentDraft, includeUsername: boolean) {
  const body: Record<string, unknown> = {
    name: draft.name,
    email: draft.email,
    phone: draft.phone,
    roll_number: draft.roll_number,
    course_id: draft.course_id,
    class_id: draft.class_id,
    division_id: draft.division_id,
    password: draft.password,
  }
  if (includeUsername) body.username = draft.username
  return body
}

export function createStudent(draft: StudentDraft) {
  return send('POST', '/api/students', payload(draft, true))
}

export function updateStudent(id: number, draft: StudentDraft) {
  return send('PUT', `/api/students/${id}`, payload(draft, false))
}

export function deactivateStudents(ids: number[]) {
  return send('POST', '/api/students/deactivate', { ids })
}

export { emptyPermissions }
