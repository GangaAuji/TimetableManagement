import { useEffect, useMemo, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { DirectoryFrame, ListScreen, messageFrom, postJson, type DataRow } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

const patternColumns = [
  { key: 'name', label: 'Shift' },
  { key: 'code', label: 'Code' },
  { key: 'start_time', label: 'Start' },
  { key: 'end_time', label: 'End' },
  { key: 'is_active', label: 'Active' },
]
const availabilityColumns = [
  { key: 'faculty', label: 'Faculty' },
  { key: 'department', label: 'Department' },
  { key: 'day', label: 'Day' },
  { key: 'shift', label: 'Shift' },
  { key: 'start_time', label: 'Start' },
  { key: 'end_time', label: 'End' },
  { key: 'available', label: 'Available' },
]
export const ShiftsPage = () => <ListScreen title="Shifts" path="/api/shifts" rowsKey="shifts" columns={patternColumns} />
export function AvailabilityPage() {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-gray-500">This is the availability faculty save from My Availability.</p>
      <ListScreen title="Faculty availability" path="/api/availability" rowsKey="rows" columns={availabilityColumns} />
    </div>
  )
}
export { MyAvailabilityPage, MyShiftsPage } from '../../teacher/pages/FacultyPortal'

const requestColumns = [
  { key: 'faculty', label: 'Faculty' },
  { key: 'department', label: 'Department' },
  { key: 'day', label: 'Day' },
  { key: 'current_shift', label: 'Current' },
  { key: 'requested_shift', label: 'Requested' },
  { key: 'reason', label: 'Reason' },
  { key: 'status', label: 'Status' },
  { key: 'action', label: 'Action' },
]

const fieldClass = 'rounded-xl border border-gray-200/80 bg-white px-3 py-2 text-xs font-medium text-gray-600 shadow-sm outline-none'

export function ShiftRequestsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [canRespond, setCanRespond] = useState(false)
  const [status, setStatus] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  function load() {
    void apiRequest<{ requests?: Record<string, unknown>[]; can_respond?: boolean }>('/api/shift-requests')
      .then((data) => {
        setCanRespond(data.can_respond === true)
        setRows((data.requests || []).map((row) => ({
          id: safeCount(row.id),
          faculty: safeText(row.faculty, 100),
          department: safeText(row.department, 100),
          day: safeText(row.day, 12),
          current_shift: safeText(row.current_shift, 80),
          requested_shift: safeText(row.requested_shift, 80),
          reason: safeText(row.reason, 300),
          status: safeText(row.status, 20).toLowerCase(),
        })))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }

  useEffect(() => {
    setPageHeader('Shift requests')
    load()
  }, [setPageHeader])

  const visible = useMemo(
    () => rows.filter((row) => !status || row.status === status),
    [rows, status],
  )
  const pending = rows.filter((row) => row.status === 'pending').length

  async function respond(id: number, action: 'approve' | 'reject') {
    setSaving(true)
    setError('')
    try {
      await postJson(`/api/shift-requests/${id}`, { action, note })
      setNotice(action === 'approve' ? 'Shift request approved.' : 'Shift request rejected.')
      setNote('')
      load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <DirectoryFrame
      title="Shift requests"
      subtitle={`${rows.length} faculty requests${pending ? ` • ${pending} pending` : ''}`}
      icon="fa-exchange-alt"
      error={error}
      notice={notice}
      columns={requestColumns}
      rows={visible}
      empty="No shift requests match this filter."
      toolbar={(
        <>
          <select value={status} onChange={(event) => setStatus(event.target.value)} className={fieldClass}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          {canRespond && (
            <input value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} placeholder="Review note" className={`${fieldClass} w-52`} />
          )}
        </>
      )}
      renderCell={(row, key) => {
        if (key !== 'action') return row[key]
        if (!canRespond || row.status !== 'pending') return ''
        return (
          <span className="inline-flex gap-2">
            <button type="button" disabled={saving} className="text-[10px] font-bold text-emerald-700 disabled:opacity-40" onClick={() => void respond(Number(row.id), 'approve')}>Approve</button>
            <button type="button" disabled={saving} className="text-[10px] font-bold text-red-700 disabled:opacity-40" onClick={() => void respond(Number(row.id), 'reject')}>Reject</button>
          </span>
        )
      }}
    />
  )
}
