import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { asInstitutionOptions, type InstitutionOption } from '../../shared/institutions'
import { safeCount, safeText } from '../../shared/security/sanitize'

export type DepartmentRecord = {
  id: number
  name: string
  code: string
  description: string
  head_of_department: string
  is_active: boolean
  course_count: number
  institution_id: number | null
  institution_name: string
}

export type DepartmentPermissions = {
  add: boolean
  change: boolean
  delete: boolean
  invite: boolean
}

export type DepartmentList = {
  departments: DepartmentRecord[]
  institutions: InstitutionOption[]
  institution_id: number | null
  permissions: DepartmentPermissions
}

export type DepartmentDraft = {
  name: string
  code: string
  description: string
  head_of_department: string
  is_active: boolean
  institution_id?: number | null
}

function asId(value: unknown): number {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

function asDepartment(value: Partial<DepartmentRecord> | null | undefined): DepartmentRecord | null {
  const id = asId(value?.id)
  const name = safeText(value?.name, 100)
  if (!id || !name) return null
  return {
    id,
    name,
    code: safeText(value?.code, 20),
    description: safeText(value?.description, 4000),
    head_of_department: safeText(value?.head_of_department, 100),
    is_active: value?.is_active === true,
    course_count: safeCount(value?.course_count),
    institution_id: asId(value?.institution_id) || null,
    institution_name: safeText(value?.institution_name, 150),
  }
}

export async function getDepartments(): Promise<DepartmentList> {
  const data = await apiRequest<Partial<DepartmentList>>('/api/departments')
  const departments = Array.isArray(data.departments)
    ? data.departments.map((row) => asDepartment(row)).filter((row): row is DepartmentRecord => row !== null)
    : []
  return {
    departments,
    institutions: asInstitutionOptions(data.institutions),
    institution_id: asId(data.institution_id) || null,
    permissions: {
      add: data.permissions?.add === true,
      change: data.permissions?.change === true,
      delete: data.permissions?.delete === true,
      invite: data.permissions?.invite === true,
    },
  }
}

export async function getDepartment(departmentId: number): Promise<DepartmentRecord> {
  const department = asDepartment(await apiRequest<DepartmentRecord>(`/api/departments/${departmentId}`))
  if (!department) throw new Error('That department was not found.')
  return department
}

async function send(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: DepartmentDraft) {
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

export function createDepartment(draft: DepartmentDraft) {
  return send('POST', '/api/departments', draft)
}

export function updateDepartment(departmentId: number, draft: DepartmentDraft) {
  return send('PUT', `/api/departments/${departmentId}`, draft)
}

export function deleteDepartment(departmentId: number) {
  return send('DELETE', `/api/departments/${departmentId}`)
}
