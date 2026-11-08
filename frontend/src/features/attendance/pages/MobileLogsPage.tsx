import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { Dialog } from '../../../shared/components/dialog'
import { Stat, messageFrom, postJson } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type LogRow = {
  id: number
  date: string
  student: string
  roll: string
  course: string
  className: string
  division: string
  subject: string
  status: string
  processing: string
  device: string
  markedBy: string
  confidence: string
  capturedAt: string
  processedAt: string
  error: string
}

const fieldClass = 'mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800'

function processingClass(status: string) {
  if (status === 'processed') return 'bg-green-50 text-green-700'
  if (status === 'pending') return 'bg-amber-50 text-amber-700'
  if (status === 'failed') return 'bg-red-50 text-red-700'
  return 'bg-gray-100 text-gray-500'
}

export function MobileLogsPage() {
  const setPageHeader = useSetPageHeader()
  const [date, setDate] = useState('')
  const [status, setStatus] = useState('')
  const [device, setDevice] = useState('')
  const [student, setStudent] = useState('')
  const [limit, setLimit] = useState('100')
  const [applied, setApplied] = useState({ date: '', status: '', device: '', student: '', limit: '100' })
  const [stats, setStats] = useState({ total: 0, processed: 0, pending: 0, failed: 0 })
  const [rows, setRows] = useState<LogRow[]>([])
  const [canReprocess, setCanReprocess] = useState(false)
  const [available, setAvailable] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function load(filters = applied) {
    const search = new URLSearchParams({ limit: filters.limit || '100' })
    if (filters.date) search.set('date', filters.date)
    if (filters.status) search.set('processing_status', filters.status)
    if (filters.device) search.set('device_id', filters.device)
    if (filters.student) search.set('student_query', filters.student)
    return apiRequest<Record<string, unknown>>(`/api/attendance/mobile?${search.toString()}`).then((data) => {
      const figures = (data.stats || {}) as Record<string, unknown>
      const source = Array.isArray(data.logs) ? data.logs : []
      setAvailable(data.available !== false)
      setCanReprocess(data.can_reprocess === true)
      setStats({
        total: safeCount(figures.total),
        processed: safeCount(figures.processed),
        pending: safeCount(figures.pending),
        failed: safeCount(figures.failed),
      })
      setRows(source.map((item) => {
        const row = item as Record<string, unknown>
        const score = row.confidence
        return {
          id: safeCount(row.id),
          date: safeText(row.date, 10),
          student: safeText(row.student, 100),
          roll: safeText(row.roll, 30),
          course: safeText(row.course, 100),
          className: safeText(row.class_name, 100),
          division: safeText(row.division, 50),
          subject: safeText(row.subject, 100),
          status: safeText(row.status, 20),
          processing: safeText(row.processing, 20),
          device: safeText(row.device, 64),
          markedBy: safeText(row.marked_by, 50),
          confidence: score === null || score === undefined || score === '' ? '' : safeText(score, 8),
          capturedAt: safeText(row.captured_at, 20),
          processedAt: safeText(row.processed_at, 20),
          error: safeText(row.error, 160),
        }
      }))
    })
  }

  useEffect(() => {
    setPageHeader('Student sync logs')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function show() {
    const next = { date, status, device: device.trim(), student: student.trim(), limit }
    setApplied(next)
    setError('')
    void load(next).catch((reason: unknown) => setError(messageFrom(reason)))
  }

  function reprocess() {
    if (busy) return
    setBusy(true)
    setError('')
    const amount = Number(limit) || 100
    void postJson<Record<string, unknown>>('/api/attendance/mobile/reprocess', { limit: amount })
      .then((data) => {
        setNotice(`Reprocess finished. Retried ${safeCount(data.retried)}, processed ${safeCount(data.processed)}, failed ${safeCount(data.failed)}.`)
        setConfirming(false)
        return load()
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-500">Marks sent from a device, and whether they were applied.</p>
        {canReprocess ? <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => setConfirming(true)}>Reprocess</button> : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-4">
        <Stat label="Total" value={stats.total} />
        <Stat label="Processed" value={stats.processed} />
        <Stat label="Pending" value={stats.pending} />
        <Stat label="Failed" value={stats.failed} />
      </div>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="rounded-r-lg border-l-4 border-green-500 bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      {!available ? <p className="text-sm text-gray-500">Student sync logs are not available yet.</p> : null}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm text-gray-700">Date
          <input className={fieldClass} type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Processing
          <select className={fieldClass} value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option value="processed">Processed</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label className="text-sm text-gray-700">Device
          <input className={fieldClass} value={device} maxLength={64} onChange={(event) => setDevice(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Student
          <input className={fieldClass} value={student} maxLength={80} onChange={(event) => setStudent(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Limit
          <input className={fieldClass} type="number" min={1} max={500} value={limit} onChange={(event) => setLimit(event.target.value)} />
        </label>
      </div>
      <div className="flex justify-end">
        <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white" onClick={show}>Show</button>
      </div>
      <div className="min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">Class and subject</th>
                <th className="px-4 py-3">Attendance</th>
                <th className="px-4 py-3">Processing</th>
                <th className="px-4 py-3">Device</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-16 text-center text-gray-500">No sync logs match these filters.</td></tr>
              ) : rows.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-3">
                    <p className="font-semibold text-gray-800">{row.student || '—'}</p>
                    <p className="text-xs text-gray-400">{row.roll}{row.course ? ` · ${row.course}` : ''}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{row.className}{row.division ? ` ${row.division}` : ''}{row.subject ? ` · ${row.subject}` : ''}</td>
                  <td className="px-4 py-3 text-gray-700">{row.date}<div className="text-xs text-gray-400">{row.status || '—'}</div></td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${processingClass(row.processing)}`}>{row.processing || '—'}</span>
                    {row.error ? <p className="mt-1 text-xs text-red-600">{row.error}</p> : null}
                    {row.processedAt ? <p className="mt-1 text-xs text-gray-400">{row.processedAt}</p> : null}
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {row.device || '—'}
                    <div className="text-xs text-gray-400">{row.markedBy}{row.confidence ? ` · ${row.confidence}` : ''}{row.capturedAt ? ` · ${row.capturedAt}` : ''}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {confirming ? (
        <Dialog title="Reprocess logs" onClose={() => { if (!busy) setConfirming(false) }}>
          <p className="text-sm text-gray-700">Apply up to {limit || '100'} pending or failed logs to attendance. Logs that still fail stay failed.</p>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="rounded-md border border-gray-300 px-3 py-2 text-sm" onClick={() => setConfirming(false)}>Cancel</button>
            <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={reprocess}>{busy ? 'Working…' : 'Reprocess'}</button>
          </div>
        </Dialog>
      ) : null}
    </section>
  )
}
