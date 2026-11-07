import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ApiError } from '../../../shared/api/client'
import { useSetPageHeader } from '../../../app/page-header'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import {
  createRoom,
  deleteRoom,
  getRoom,
  getRoomSchedule,
  getRooms,
  roomTypes,
  updateRoom,
  type DepartmentOption,
  type RoomDraft,
  type RoomPermissions,
  type RoomRecord,
  type RoomSchedule,
  type RoomType,
} from '../api'

const emptyPermissions: RoomPermissions = { add: false, change: false, delete: false }
const roomColumns: TableColumnSpec[] = [
  { key: 'room_number', label: 'Room no' },
  { key: 'room_type', label: 'Type' },
  { key: 'capacity', label: 'Capacity', className: 'hidden sm:table-cell' },
  { key: 'department_name', label: 'Department', className: 'hidden md:table-cell' },
]

function roomValue(room: RoomRecord, key: string) {
  if (key === 'department_name') return room.department_name || 'Shared'
  return room[key as keyof RoomRecord]
}

function typeBadge(roomType: string) {
  if (roomType === 'Laboratory') return 'border-purple-100 bg-purple-50 text-purple-700'
  if (roomType === 'Conference') return 'border-orange-100 bg-orange-50 text-orange-700'
  if (roomType === 'Auditorium') return 'border-green-100 bg-green-50 text-green-700'
  return 'border-green-100 bg-green-50 text-green-700'
}

function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function RoomsPage() {
  const setPageHeader = useSetPageHeader()
  const [rooms, setRooms] = useState<RoomRecord[]>([])
  const [departments, setDepartments] = useState<DepartmentOption[]>([])
  const [permissions, setPermissions] = useState<RoomPermissions>(emptyPermissions)
  const [typeFilter, setTypeFilter] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [editor, setEditor] = useState<{ id: number | null; draft: RoomDraft } | null>(null)
  const [schedule, setSchedule] = useState<RoomSchedule | null>(null)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await getRooms()
    setRooms(data.rooms)
    setDepartments(data.departments)
    setPermissions(data.permissions)
  }

  useEffect(() => {
    setPageHeader('Room Configuration')
  }, [setPageHeader])

  useEffect(() => {
    void load()
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [])

  const rows = useMemo(() => rooms.filter((room) => {
    const departmentName = room.department_name || 'Shared'
    const matchesType = !typeFilter || room.room_type === typeFilter
    const matchesDepartment = !departmentFilter || (departmentFilter === 'Shared' ? !room.department_name : departmentName === departmentFilter)
    return matchesType && matchesDepartment
  }), [departmentFilter, rooms, typeFilter])
  const table = useDataTable(rows, roomColumns, roomValue)

  async function openEdit(roomId: number) {
    setError('')
    try {
      const room = await getRoom(roomId)
      setEditor({
        id: room.id,
        draft: {
          room_number: room.room_number,
          room_type: (room.room_type || 'Classroom') as RoomType,
          capacity: room.capacity,
          department_id: room.department_id,
        },
      })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function openSchedule(roomId: number) {
    setError('')
    try {
      setSchedule(await getRoomSchedule(roomId))
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (editor.id) await updateRoom(editor.id, editor.draft)
      else await createRoom(editor.draft)
      setEditor(null)
      setNotice(editor.id ? 'Room updated.' : 'Room added.')
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function onDelete(room: RoomRecord) {
    if (!window.confirm(`Delete room ${room.room_number}?`)) return
    setError('')
    setNotice('')
    try {
      await deleteRoom(room.id)
      setNotice('Room deleted.')
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col items-start justify-between gap-4 p-4 xl:flex-row xl:items-center">
          <div className="flex w-full items-center justify-between gap-4 xl:w-auto">
            <div>
              <h2 className="text-lg font-bold text-gray-800">Room Inventory</h2>
              <p className="text-xs text-gray-500">Classrooms, Labs & Capacity</p>
            </div>
            {permissions.add ? (
              <button type="button" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white shadow hover:bg-blue-700 xl:hidden" onClick={() => setEditor({ id: null, draft: { room_number: '', room_type: 'Classroom', capacity: 1, department_id: null } })}>
                <i className="fas fa-plus" />
              </button>
            ) : null}
          </div>
          <div className="flex w-full flex-col flex-wrap items-end gap-2 md:flex-row md:items-center xl:w-auto">
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="w-full rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 md:w-32">
              <option value="">All Types</option>
              {roomTypes.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
            <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)} className="w-full rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 md:w-40">
              <option value="">All Departments</option>
              <option value="Shared">Shared / General</option>
              {departments.map((department) => <option key={department.id} value={department.name}>{department.name}</option>)}
            </select>
            {permissions.add ? (
              <button type="button" className="hidden items-center rounded bg-blue-600 px-4 py-1.5 text-xs whitespace-nowrap text-white shadow transition-colors hover:bg-blue-700 xl:flex" onClick={() => setEditor({ id: null, draft: { room_number: '', room_type: 'Classroom', capacity: 1, department_id: null } })}>
                <i className="fas fa-plus mr-2" /> Add Room
              </button>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</p> : null}

      <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="max-h-[70vh] overflow-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="sticky top-0 z-10 bg-gray-50 shadow-sm">
              <DataTableHead columns={roomColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {loading ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-500">Loading rooms…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-500">No rooms match these filters.</td></tr>
              ) : table.rows.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-500">No rooms match these filters.</td></tr>
              ) : table.rows.map((room) => (
                <tr key={room.id} className="group transition-colors hover:bg-blue-50">
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-gray-100 text-xs font-bold text-gray-500">{room.room_number.slice(0, 2)}</div>
                      <div>
                        <div className="font-semibold text-gray-900">{room.room_number}</div>
                        <div className="text-[10px] text-gray-500 md:hidden">{room.department_name || 'Shared'}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <span className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${typeBadge(room.room_type)}`}>{room.room_type || 'Room'}</span>
                  </td>
                  <td className="hidden px-4 py-2 text-xs text-gray-600 sm:table-cell">
                    <i className="fas fa-chair mr-1.5 text-gray-300" />
                    <span className="font-mono font-medium">{room.capacity}</span>
                  </td>
                  <td className="hidden px-4 py-2 text-xs text-gray-600 md:table-cell">
                    {room.department_name || <span className="text-gray-400 italic">Shared / General</span>}
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <div className="flex justify-end gap-2 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100">
                      <button type="button" title="View Schedule" className="rounded p-1.5 text-teal-600 hover:bg-teal-50 hover:text-teal-800" onClick={() => void openSchedule(room.id)}>
                        <i className="fas fa-calendar-alt" />
                      </button>
                      {permissions.change ? (
                        <button type="button" title="Edit" className="rounded p-1.5 text-blue-600 hover:bg-blue-50 hover:text-blue-800" onClick={() => void openEdit(room.id)}>
                          <i className="fas fa-edit" />
                        </button>
                      ) : null}
                      {permissions.delete ? (
                        <button type="button" title="Delete" className="rounded p-1.5 text-red-600 hover:bg-red-50 hover:text-red-800" onClick={() => void onDelete(room)}>
                          <i className="fas fa-trash-alt" />
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
      </section>

      {editor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
          <button type="button" aria-label="Close" className="absolute inset-0 bg-gray-900/60" onClick={() => setEditor(null)} />
          <div className="relative m-4 w-full max-w-lg overflow-hidden rounded-lg bg-white shadow-2xl">
            <div className="flex items-center justify-between bg-blue-600 px-6 py-4">
              <h3 className="flex items-center gap-2 text-lg font-bold text-white"><i className={`fas ${editor.id ? 'fa-edit' : 'fa-plus'}`} /> {editor.id ? 'Edit Room' : 'Add Room'}</h3>
              <button type="button" className="text-xl text-white hover:text-gray-200" onClick={() => setEditor(null)}>&times;</button>
            </div>
            <form className="p-6" onSubmit={(event) => void onSave(event)}>
              <div className="grid grid-cols-2 gap-4">
                <label className="block text-xs font-semibold text-gray-700">
                  Room Number <span className="text-red-500">*</span>
                  <input required value={editor.draft.room_number} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, room_number: event.target.value } })} placeholder="e.g. 101" className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  Capacity <span className="text-red-500">*</span>
                  <input required type="number" min={1} max={10000} value={editor.draft.capacity} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, capacity: Number(event.target.value) } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500" />
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Room Type <span className="text-red-500">*</span>
                  <select required value={editor.draft.room_type} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, room_type: event.target.value as RoomType } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500">
                    {roomTypes.map((type) => <option key={type} value={type}>{type === 'Conference' ? 'Conference Room' : type}</option>)}
                  </select>
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Department
                  <select value={editor.draft.department_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, department_id: event.target.value ? Number(event.target.value) : null } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500">
                    <option value="">-- Shared / General Resource --</option>
                    {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                  <p className="mt-1 text-[10px] text-gray-500">Leave blank if this room is shared across departments.</p>
                </label>
              </div>
              <div className="mt-6 flex justify-end gap-3 border-t border-gray-100 pt-4">
                <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200" onClick={() => setEditor(null)}>Cancel</button>
                <button type="submit" disabled={saving} className="rounded-md bg-blue-600 px-6 py-2 text-sm font-medium text-white shadow hover:bg-blue-700 disabled:opacity-60">{saving ? 'Saving…' : 'Save Room'}</button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {schedule ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
          <button type="button" aria-label="Close schedule" className="absolute inset-0 bg-gray-900/60" onClick={() => setSchedule(null)} />
          <div className="relative m-4 flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
            <div className="flex items-center justify-between bg-teal-600 px-6 py-3">
              <h3 className="flex items-center gap-2 font-bold text-white"><i className="far fa-clock" /> Weekly Schedule · {schedule.room_number}</h3>
              <button type="button" className="text-xl text-white hover:text-gray-200" onClick={() => setSchedule(null)}>&times;</button>
            </div>
            <div className="flex-1 overflow-y-auto bg-gray-50">
              {schedule.schedule.length === 0 ? <p className="p-6 text-sm text-gray-500">No classes are assigned to this room.</p> : (
                <table className="min-w-full text-sm">
                  <thead className="bg-white text-left text-xs font-bold tracking-wider text-gray-500 uppercase">
                    <tr>
                      {['Day', 'Time', 'Subject', 'Class', 'Faculty'].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {schedule.schedule.map((entry, index) => (
                      <tr key={`${entry.day}-${entry.start_time}-${index}`}>
                        <td className="px-4 py-2">{entry.day}</td>
                        <td className="px-4 py-2 whitespace-nowrap">{entry.start_time} – {entry.end_time}</td>
                        <td className="px-4 py-2">{entry.subject_name}</td>
                        <td className="px-4 py-2">{entry.class_name} {entry.division_name}</td>
                        <td className="px-4 py-2">{entry.faculty_name || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
