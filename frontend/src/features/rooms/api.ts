import { apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { safeCount, safeText } from '../../shared/security/sanitize'

export const roomTypes = ['Classroom', 'Laboratory', 'Conference', 'Auditorium'] as const
export type RoomType = (typeof roomTypes)[number]

export type RoomRecord = {
  id: number
  room_number: string
  room_type: RoomType | ''
  capacity: number
  department_id: number | null
  department_name: string
}

export type DepartmentOption = { id: number; name: string }

export type RoomPermissions = { add: boolean; change: boolean; delete: boolean }

export type RoomList = {
  rooms: RoomRecord[]
  departments: DepartmentOption[]
  permissions: RoomPermissions
}

export type RoomScheduleEntry = {
  day: string
  start_time: string
  end_time: string
  subject_name: string
  class_name: string
  division_name: string
  faculty_name: string
}

export type RoomSchedule = { room_number: string; schedule: RoomScheduleEntry[] }

export type RoomDraft = {
  room_number: string
  room_type: RoomType
  capacity: number
  department_id: number | null
}

function asId(value: unknown): number {
  const number = safeCount(value)
  return number > 0 ? number : 0
}

function asRoom(value: Partial<RoomRecord> | null | undefined): RoomRecord | null {
  const id = asId(value?.id)
  const roomType = roomTypes.includes(value?.room_type as RoomType) ? (value?.room_type as RoomType) : ''
  if (!id) return null
  return {
    id,
    room_number: safeText(value?.room_number, 20),
    room_type: roomType,
    capacity: safeCount(value?.capacity),
    department_id: asId(value?.department_id) || null,
    department_name: safeText(value?.department_name, 120),
  }
}

export async function getRooms(): Promise<RoomList> {
  const data = await apiRequest<Partial<RoomList>>('/api/rooms')
  const rooms = Array.isArray(data.rooms) ? data.rooms.map((row) => asRoom(row)).filter((row): row is RoomRecord => row !== null) : []
  const departments = Array.isArray(data.departments)
    ? data.departments
        .map((row) => ({ id: asId(row?.id), name: safeText(row?.name, 120) }))
        .filter((row) => row.id > 0 && row.name)
    : []
  return {
    rooms,
    departments,
    permissions: {
      add: data.permissions?.add === true,
      change: data.permissions?.change === true,
      delete: data.permissions?.delete === true,
    },
  }
}

export async function getRoom(roomId: number): Promise<RoomRecord> {
  const room = asRoom(await apiRequest<RoomRecord>(`/api/rooms/${roomId}`))
  if (!room) throw new Error('That room was not found.')
  return room
}

async function send(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: RoomDraft) {
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

export function createRoom(draft: RoomDraft) {
  return send('POST', '/api/rooms', draft)
}

export function updateRoom(roomId: number, draft: RoomDraft) {
  return send('PUT', `/api/rooms/${roomId}`, draft)
}

export function deleteRoom(roomId: number) {
  return send('DELETE', `/api/rooms/${roomId}`)
}

export async function getRoomSchedule(roomId: number): Promise<RoomSchedule> {
  const data = await apiRequest<Partial<RoomSchedule>>(`/api/rooms/${roomId}/schedule`)
  const schedule = Array.isArray(data.schedule)
    ? data.schedule.map((row) => ({
        day: safeText(row?.day, 20),
        start_time: safeText(row?.start_time, 20),
        end_time: safeText(row?.end_time, 20),
        subject_name: safeText(row?.subject_name, 160),
        class_name: safeText(row?.class_name, 120),
        division_name: safeText(row?.division_name, 80),
        faculty_name: safeText(row?.faculty_name, 160),
      }))
    : []
  return { room_number: safeText(data.room_number, 20), schedule }
}
