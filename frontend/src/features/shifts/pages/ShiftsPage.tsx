import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { Dialog } from '../../../shared/components/dialog'
import { messageFrom, postJson, Stat } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Shift = {
  id: number
  name: string
  code: string
  start: string
  end: string
  order: number
  description: string
  active: boolean
  facultyCount: number
}

type Draft = {
  name: string
  code: string
  start: string
  end: string
  order: string
  description: string
  active: boolean
}

const fieldClass = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 outline-none focus:border-indigo-500'
const emptyDraft: Draft = { name: '', code: '', start: '09:00', end: '17:00', order: '1', description: '', active: true }

function readShift(row: Record<string, unknown>): Shift {
  return {
    id: safeCount(row.id),
    name: safeText(row.name, 80),
    code: safeText(row.code, 20),
    start: safeText(row.start_time, 8),
    end: safeText(row.end_time, 8),
    order: safeCount(row.shift_order) || 1,
    description: safeText(row.description, 200),
    active: row.is_active === true,
    facultyCount: safeCount(row.faculty_count),
  }
}

function draftFrom(shift: Shift): Draft {
  return {
    name: shift.name,
    code: shift.code,
    start: shift.start || '09:00',
    end: shift.end || '17:00',
    order: String(shift.order || 1),
    description: shift.description,
    active: shift.active,
  }
}

export function ShiftsPage() {
  const setPageHeader = useSetPageHeader()
  const [shifts, setShifts] = useState<Shift[]>([])
  const [activeCount, setActiveCount] = useState(0)
  const [facultyCount, setFacultyCount] = useState(0)
  const [canAdd, setCanAdd] = useState(false)
  const [canChange, setCanChange] = useState(false)
  const [canDelete, setCanDelete] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [editing, setEditing] = useState<Shift | null>(null)
  const [removing, setRemoving] = useState<Shift | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function load() {
    return apiRequest<Record<string, unknown>>('/api/shifts').then((data) => {
      const source = Array.isArray(data.shifts) ? data.shifts : []
      setShifts(source.map((item) => readShift(item as Record<string, unknown>)))
      setActiveCount(safeCount(data.active_count))
      setFacultyCount(safeCount(data.faculty_count))
      setCanAdd(data.can_add === true)
      setCanChange(data.can_change === true)
      setCanDelete(data.can_delete === true)
    })
  }

  useEffect(() => {
    setPageHeader('Shift Patterns')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function save() {
    if (!draft || busy) return
    setBusy(true)
    setError('')
    const payload = {
      name: draft.name,
      code: draft.code,
      start_time: draft.start,
      end_time: draft.end,
      shift_order: Number(draft.order) || 1,
      description: draft.description,
      is_active: draft.active,
    }
    const path = editing ? `/api/shifts/${editing.id}` : '/api/shifts'
    void postJson(path, payload)
      .then(() => load())
      .then(() => {
        setDraft(null)
        setEditing(null)
        setNotice(editing ? 'Shift updated.' : 'Shift added.')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  function remove() {
    if (!removing || busy) return
    setBusy(true)
    setError('')
    void postJson(`/api/shifts/${removing.id}/delete`, {})
      .then(() => load())
      .then(() => {
        setRemoving(null)
        setNotice('Shift deleted.')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-500">Name, hours, and who is assigned to each pattern.</p>
        <div className="flex gap-2">
          <Link to="/admin/shifts/availability" className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700">Faculty availability</Link>
          {canAdd ? <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => { setEditing(null); setDraft(emptyDraft) }}>Add shift</button> : null}
        </div>
      </div>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="rounded-r-lg border-l-4 border-green-500 bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Stat label="Active shifts" value={activeCount} />
        <Stat label="Faculty with shifts" value={facultyCount} />
      </div>
      <div className="min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Shift</th>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Faculty</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {shifts.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-16 text-center text-gray-500">No shift patterns yet.</td></tr>
              ) : shifts.map((shift) => (
                <tr key={shift.id} className="hover:bg-indigo-50/40">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-gray-800">{shift.name}</p>
                    <p className="text-xs text-gray-400">{shift.code}{shift.description ? ` · ${shift.description}` : ''}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{shift.start} – {shift.end}</td>
                  <td className="px-4 py-3 text-gray-700">{shift.facultyCount}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${shift.active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{shift.active ? 'Active' : 'Inactive'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      {canChange ? <button type="button" className="text-sm font-semibold text-indigo-600" onClick={() => { setEditing(shift); setDraft(draftFrom(shift)) }}>Edit</button> : null}
                      {canDelete ? (
                        <button type="button" className="text-sm font-semibold text-red-600 disabled:text-gray-300" disabled={shift.facultyCount > 0} title={shift.facultyCount > 0 ? 'Assigned to faculty' : 'Delete'} onClick={() => setRemoving(shift)}>Delete</button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {draft ? (
        <Dialog title={editing ? 'Edit shift' : 'Add shift'} onClose={() => { if (!busy) { setDraft(null); setEditing(null) } }}>
          <div className="grid gap-3">
            <label className="text-sm text-gray-700">Name
              <input className={fieldClass} value={draft.name} maxLength={80} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label className="text-sm text-gray-700">Code
              <input className={fieldClass} value={draft.code} maxLength={20} onChange={(event) => setDraft({ ...draft, code: event.target.value })} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-sm text-gray-700">Start
                <input className={fieldClass} type="time" value={draft.start} onChange={(event) => setDraft({ ...draft, start: event.target.value })} />
              </label>
              <label className="text-sm text-gray-700">End
                <input className={fieldClass} type="time" value={draft.end} onChange={(event) => setDraft({ ...draft, end: event.target.value })} />
              </label>
            </div>
            <label className="text-sm text-gray-700">Order
              <input className={fieldClass} type="number" min={1} max={99} value={draft.order} onChange={(event) => setDraft({ ...draft, order: event.target.value })} />
            </label>
            <label className="text-sm text-gray-700">Description
              <textarea className={fieldClass} maxLength={200} rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={draft.active} onChange={(event) => setDraft({ ...draft, active: event.target.checked })} />
              Active
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className="rounded-md border border-gray-300 px-3 py-2 text-sm" onClick={() => { setDraft(null); setEditing(null) }}>Cancel</button>
              <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </Dialog>
      ) : null}
      {removing ? (
        <Dialog title="Delete shift" onClose={() => { if (!busy) setRemoving(null) }}>
          <p className="text-sm text-gray-700">Delete {removing.name}? This cannot be undone.</p>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="rounded-md border border-gray-300 px-3 py-2 text-sm" onClick={() => setRemoving(null)}>Cancel</button>
            <button type="button" className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={remove}>Delete</button>
          </div>
        </Dialog>
      ) : null}
    </section>
  )
}

export { AvailabilityPage } from './AvailabilityPage'
export { ShiftRequestsPage } from './ShiftRequestsPage'
export { MyAvailabilityPage, MyShiftsPage } from '../../teacher/pages/FacultyPortal'
