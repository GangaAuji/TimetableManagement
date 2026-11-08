import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { ListTable, displayValue, messageFrom, postJson, type DataRow } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Absence = { id: number; date: string; reason: string; status: string }
type ProxyEntry = { id: number; date: string; day: string; start: string; end: string; subject: string; original: string; proxy: string; status: string; approval: string }

const fieldClass = 'rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800'

function todayInput() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export function FacultySessionsPage() {
  const { facultyId } = useParams()
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [absences, setAbsences] = useState<Absence[]>([])
  const [entries, setEntries] = useState<ProxyEntry[]>([])
  const [canChange, setCanChange] = useState(false)
  const [canDelete, setCanDelete] = useState(false)
  const [date, setDate] = useState(todayInput)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function loadExtras() {
    return Promise.all([
      apiRequest<Record<string, unknown>>(`/api/faculty/${facultyId}/absences`),
      apiRequest<Record<string, unknown>>(`/api/faculty/${facultyId}/proxy`),
    ]).then(([absencePage, proxyPage]) => {
      const absenceRows = Array.isArray(absencePage.absences) ? absencePage.absences : []
      const proxyRows = Array.isArray(proxyPage.entries) ? proxyPage.entries : []
      setAbsences(absenceRows.map((item) => {
        const row = item as Record<string, unknown>
        return { id: safeCount(row.id), date: safeText(row.date, 10), reason: safeText(row.reason, 200), status: safeText(row.status, 20) }
      }))
      setEntries(proxyRows.map((item) => {
        const row = item as Record<string, unknown>
        return {
          id: safeCount(row.id),
          date: safeText(row.date, 10),
          day: safeText(row.day, 12),
          start: safeText(row.start_time, 8),
          end: safeText(row.end_time, 8),
          subject: safeText(row.subject, 100),
          original: safeText(row.original_faculty, 100),
          proxy: safeText(row.proxy_faculty, 100),
          status: safeText(row.status, 20),
          approval: safeText(row.approval, 20),
        }
      }))
      setCanChange(absencePage.can_change === true || proxyPage.can_change === true)
      setCanDelete(absencePage.can_delete === true)
    })
  }

  useEffect(() => {
    setPageHeader('Faculty timetable')
    void apiRequest<{ name?: unknown; sessions?: Record<string, unknown>[] }>(`/api/faculty/${facultyId}/sessions`)
      .then((data) => {
        setPageHeader(safeText(data.name, 100) || 'Faculty timetable')
        setRows((data.sessions || []).map((row) => ({
          day: displayValue(row.day),
          start_time: displayValue(row.start_time),
          end_time: displayValue(row.end_time),
          subject: displayValue(row.subject),
          class_name: displayValue(row.class_name),
          division_name: displayValue(row.division_name),
          room: displayValue(row.room),
        })))
      })
      .catch((reasonValue: unknown) => setError(messageFrom(reasonValue)))
    void loadExtras().catch((reasonValue: unknown) => setError(messageFrom(reasonValue)))
  }, [facultyId, setPageHeader])

  function run(path: string, done: string) {
    if (busy) return
    setBusy(true)
    setError('')
    void postJson(path, {})
      .then(() => loadExtras())
      .then(() => setNotice(done))
      .catch((reasonValue: unknown) => setError(messageFrom(reasonValue)))
      .finally(() => setBusy(false))
  }

  function addAbsence() {
    if (busy) return
    setBusy(true)
    setError('')
    void postJson(`/api/faculty/${facultyId}/absences`, { date, reason })
      .then(() => loadExtras())
      .then(() => {
        setReason('')
        setNotice('Absence recorded.')
      })
      .catch((reasonValue: unknown) => setError(messageFrom(reasonValue)))
      .finally(() => setBusy(false))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link to="/admin/faculty" className="text-sm font-semibold text-indigo-600">Back to faculty</Link>
        <div className="flex gap-2">
          <Link to="/admin/shifts/availability" className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700">Availability</Link>
          <Link to="/admin/shifts" className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700">Shifts</Link>
        </div>
      </div>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="rounded-r-lg border-l-4 border-green-500 bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      <ListTable columns={[{ key: 'day', label: 'Day' }, { key: 'start_time', label: 'Start' }, { key: 'end_time', label: 'End' }, { key: 'subject', label: 'Subject' }, { key: 'class_name', label: 'Class' }, { key: 'division_name', label: 'Division' }, { key: 'room', label: 'Room' }]} rows={rows} />
      <section className="rounded-2xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-bold text-gray-800">Absence history</h2>
        {canChange ? (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-sm text-gray-700">Date
              <input className={`${fieldClass} mt-1 block`} type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
            <label className="min-w-[220px] flex-1 text-sm text-gray-700">Reason
              <input className={`${fieldClass} mt-1 block w-full`} maxLength={200} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={addAbsence}>Log absence</button>
          </div>
        ) : null}
        <div className="mt-3 overflow-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr><th className="px-2 py-2">Date</th><th className="px-2 py-2">Reason</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Actions</th></tr>
            </thead>
            <tbody>
              {absences.length === 0 ? <tr><td colSpan={4} className="px-2 py-8 text-gray-500">No absences recorded.</td></tr> : absences.map((item) => (
                <tr key={item.id} className="border-t border-gray-100">
                  <td className="px-2 py-2">{item.date}</td>
                  <td className="px-2 py-2">{item.reason || '—'}</td>
                  <td className="px-2 py-2">{item.status || '—'}</td>
                  <td className="px-2 py-2">
                    <div className="flex gap-3">
                      {canChange && item.status !== 'PROCESSED' ? <button type="button" className="font-semibold text-indigo-600" disabled={busy} onClick={() => run(`/api/faculty/${facultyId}/absences/${item.id}/approve`, 'Absence approved.')}>Approve</button> : null}
                      {canChange && item.status !== 'REJECTED' ? <button type="button" className="font-semibold text-gray-700" disabled={busy} onClick={() => run(`/api/faculty/${facultyId}/absences/${item.id}/reject`, 'Absence rejected.')}>Reject</button> : null}
                      {canDelete && item.status === 'UNPROCESSED' ? <button type="button" className="font-semibold text-red-600" disabled={busy} onClick={() => run(`/api/faculty/${facultyId}/absences/${item.id}/delete`, 'Absence deleted.')}>Delete</button> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="rounded-2xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-bold text-gray-800">Proxy log</h2>
        <div className="mt-3 overflow-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr><th className="px-2 py-2">Date</th><th className="px-2 py-2">Time</th><th className="px-2 py-2">Subject</th><th className="px-2 py-2">Original</th><th className="px-2 py-2">Proxy</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Actions</th></tr>
            </thead>
            <tbody>
              {entries.length === 0 ? <tr><td colSpan={7} className="px-2 py-8 text-gray-500">No proxy records.</td></tr> : entries.map((item) => (
                <tr key={item.id} className="border-t border-gray-100">
                  <td className="px-2 py-2">{item.date}<div className="text-xs text-gray-400">{item.day}</div></td>
                  <td className="px-2 py-2">{item.start} – {item.end}</td>
                  <td className="px-2 py-2">{item.subject}</td>
                  <td className="px-2 py-2">{item.original || '—'}</td>
                  <td className="px-2 py-2">{item.proxy || 'Not assigned'}</td>
                  <td className="px-2 py-2">{item.status}{item.approval ? ` · ${item.approval}` : ''}</td>
                  <td className="px-2 py-2">
                    {canChange && item.approval !== 'APPROVED' ? (
                      <div className="flex gap-3">
                        <button type="button" className="font-semibold text-indigo-600" disabled={busy} onClick={() => run(`/api/faculty/${facultyId}/proxy/${item.id}/approve`, 'Proxy approved.')}>Approve</button>
                        <button type="button" className="font-semibold text-gray-700" disabled={busy} onClick={() => run(`/api/faculty/${facultyId}/proxy/${item.id}/reject`, 'Proxy rejected.')}>Reject</button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
