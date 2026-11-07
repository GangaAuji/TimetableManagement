import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { safeCount, safeText } from '../../shared/security/sanitize'

export const programs = ['UG', 'PG'] as const
export type Program = (typeof programs)[number]

export type CourseRecord = {
  id: number
  name: string
  code: string
  program: Program | ''
  department_id: number
  department_name: string
  duration_years: number
  total_semesters: number
  description: string
  is_active: boolean
  subject_count: number
  batch_count: number
}

export type DepartmentOption = { id: number; name: string }

export type CoursePermissions = { add: boolean; change: boolean; delete: boolean }

export type CourseList = {
  courses: CourseRecord[]
  departments: DepartmentOption[]
  permissions: CoursePermissions
}

export type CourseDraft = {
  name: string
  code: string
  program: Program
  department_id: number | null
  duration_years: number
  total_semesters: number
  description: string
  is_active: boolean
}

function asId(value: unknown): number {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

function asCourse(value: Partial<CourseRecord> | null | undefined): CourseRecord | null {
  const id = asId(value?.id)
  const name = safeText(value?.name, 100)
  const program = programs.includes(value?.program as Program) ? (value?.program as Program) : ''
  if (!id || !name) return null
  return {
    id,
    name,
    code: safeText(value?.code, 20),
    program,
    department_id: asId(value?.department_id),
    department_name: safeText(value?.department_name, 100),
    duration_years: safeCount(value?.duration_years),
    total_semesters: safeCount(value?.total_semesters),
    description: safeText(value?.description, 4000),
    is_active: value?.is_active === true,
    subject_count: safeCount(value?.subject_count),
    batch_count: safeCount(value?.batch_count),
  }
}

export async function getCourses(): Promise<CourseList> {
  const data = await apiRequest<Partial<CourseList>>('/api/courses')
  const courses = Array.isArray(data.courses)
    ? data.courses.map((row) => asCourse(row)).filter((row): row is CourseRecord => row !== null)
    : []
  const departments = Array.isArray(data.departments)
    ? data.departments
        .map((row) => ({ id: asId(row?.id), name: safeText(row?.name, 100) }))
        .filter((row) => row.id > 0 && row.name)
    : []
  return {
    courses,
    departments,
    permissions: {
      add: data.permissions?.add === true,
      change: data.permissions?.change === true,
      delete: data.permissions?.delete === true,
    },
  }
}

export async function getCourse(courseId: number): Promise<CourseRecord> {
  const course = asCourse(await apiRequest<CourseRecord>(`/api/courses/${courseId}`))
  if (!course) throw new Error('That course was not found.')
  return course
}

async function send(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: CourseDraft) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
}

export function createCourse(draft: CourseDraft) {
  return send('POST', '/api/courses', draft)
}

export function updateCourse(courseId: number, draft: CourseDraft) {
  return send('PUT', `/api/courses/${courseId}`, draft)
}

export function deleteCourse(courseId: number) {
  return send('DELETE', `/api/courses/${courseId}`)
}
