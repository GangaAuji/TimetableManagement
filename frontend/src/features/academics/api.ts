import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { safeCount, safeText } from '../../shared/security/sanitize'

export type Permissions = { add: boolean; change: boolean; delete: boolean }
export type Option = { id: number; name: string }

const emptyPermissions: Permissions = { add: false, change: false, delete: false }

export function asId(value: unknown): number {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

export function permissionsOf(value: Partial<Permissions> | undefined): Permissions {
  return {
    add: value?.add === true,
    change: value?.change === true,
    delete: value?.delete === true,
  }
}

export function optionsOf(value: unknown): Option[] {
  if (!Array.isArray(value)) return []
  return value
    .map((row) => ({ id: asId(row?.id), name: safeText(row?.name, 160) }))
    .filter((row) => row.id > 0 && row.name)
}

export async function sendJson(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: object) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: body ? JSON.stringify(body) : undefined,
  })
}

export async function readList<T>(path: string): Promise<T & { permissions: Permissions }> {
  const data = await apiRequest<T & { permissions?: Permissions }>(path)
  return { ...data, permissions: permissionsOf(data.permissions) }
}

export { emptyPermissions }
