import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { pageFill } from '../../../shared/layout/page-frame'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type RequestRow = {
  id: number
  faculty: string
  department: string
  day: string
  currentShift: string
  requestedShift: string
  reason: string
  status: string
  response: string
  submitted: string
  reviewer: string
  reviewedAt: string
}

const fieldClass = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 outline-none focus:border-indigo-500'

function readRequest(row: Record<string, unknown>): RequestRow {
  return {
    id: safeCount(row.id),
    faculty: safeText(row.faculty, 100),
    department: safeText(row.department, 100),
    day: safeText(row.day, 12),
    currentShift: safeText(row.current_shift, 80),
    requestedShift: safeText(row.requested_shift, 80),
    reason: safeText(row.reason, 500),
    status: safeText(row.status, 20).toLowerCase(),
    response: safeText(row.response, 1000),
    submitted: safeText(row.submitted, 20),
    reviewer: safeText(row.reviewer, 80),
    reviewedAt: safeText(row.reviewed_at, 20),
  }
}

function statusClass(status: string) {
  if (status === 'approved') return 'bg-green-100 text-green-800'
  if (status === 'pending') return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function statusLabel(status: string) {
  if (status === 'approved') return 'Approved'
  if (status === 'pending') return 'Pending'
  return 'Rejected'
}

export function ShiftRequestsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<RequestRow[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [canRespond, setCanRespond] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [responding, setResponding] = useState<RequestRow | null>(null)
  const [details, setDetails] = useState<RequestRow | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setPageHeader('Faculty Shift Change Requests')
  }, [setPageHeader])

  useEffect(() => {
    let active = true
    setLoading(true)
    void apiRequest<{ requests?: Record<string, unknown>[]; pending_count?: number; can_respond?: boolean }>('/api/shift-requests')
      .then((data) => {
        if (!active) return
        setCanRespond(data.can_respond === true)
        setPendingCount(safeCount(data.pending_count))
        setRows((data.requests || []).map(readRequest))
        setError('')
      })
      .catch((reason: unknown) => {
        if (active) setError(messageFrom(reason))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  async function submit(action: 'approve' | 'reject') {
    if (!responding) return
    setSaving(true)
    setError('')
    try {
      await postJson(`/api/shift-requests/${responding.id}`, { action, note })
      setNotice(action === 'approve' ? 'Request approved successfully.' : 'Request rejected successfully.')
      setResponding(null)
      setNote('')
      setReloadKey((value) => value + 1)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${pageFill} gap-2`}>
      <div className="flex shrink-0 flex-col justify-between gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm md:flex-row md:items-center">
        <div>
          <h2 className="text-lg font-bold text-gray-800">Shift Change Requests</h2>
          <p className="text-xs text-gray-500">Review and respond to faculty shift modification requests</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-2">
            <div className="text-xs font-semibold text-yellow-600">Pending</div>
            <div className="text-2xl font-bold text-yellow-800">{pendingCount}</div>
          </div>
          <Link to="/admin/shifts/availability" className="rounded bg-blue-600 px-4 py-2 text-xs text-white shadow hover:bg-blue-700">
            <i className="fas fa-calendar-alt mr-2" />
            View Schedules
          </Link>
        </div>
      </div>

      {error && <p className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="shrink-0 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        <div className="flex-1 overflow-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="sticky top-0 bg-gray-50">
              <tr>
                {['Faculty', 'Day', 'Current', 'Requested', 'Reason', 'Submitted', 'Status', 'Actions'].map((label) => (
                  <th key={label} className={`px-4 py-3 text-xs font-bold tracking-wider text-gray-600 uppercase ${label === 'Status' ? 'text-center' : label === 'Actions' ? 'text-right' : 'text-left'}`}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {loading && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-500">Loading requests…</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    <i className="fas fa-inbox mb-2 text-4xl opacity-50" />
                    <p>No shift change requests</p>
                  </td>
                </tr>
              )}
              {!loading && rows.map((row) => (
                <tr key={row.id} className="hover:bg-indigo-50">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-gray-900">{row.faculty}</div>
                    <div className="text-xs text-gray-500">{row.department || 'No Department'}</div>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{row.day}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{row.currentShift}</td>
                  <td className="px-4 py-3 text-sm font-semibold text-gray-900">{row.requestedShift}</td>
                  <td className="max-w-xs px-4 py-3 text-sm text-gray-600">
                    <div className="truncate" title={row.reason}>{row.reason || '-'}</div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{row.submitted}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {row.status === 'pending' && canRespond && (
                      <button
                        type="button"
                        className="text-sm font-medium text-blue-600 hover:text-blue-800"
                        onClick={() => {
                          setNote('')
                          setResponding(row)
                        }}
                      >
                        <i className="fas fa-reply" /> Respond
                      </button>
                    )}
                    {row.status !== 'pending' && (
                      <button type="button" className="text-sm text-gray-600 hover:text-gray-800" onClick={() => setDetails(row)}>
                        <i className="fas fa-eye" /> Details
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {responding && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-600/50" onClick={() => setResponding(null)}>
          <div className="relative top-20 mx-auto w-full max-w-lg rounded-md border bg-white p-5 shadow-lg" onClick={(event) => event.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Respond to Shift Change Request</h3>
              <button type="button" className="text-gray-400 hover:text-gray-600" onClick={() => setResponding(null)} aria-label="Close">
                <i className="fas fa-times" />
              </button>
            </div>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <div className="text-xs text-gray-600">Request from:</div>
              <div className="font-bold text-gray-900">{responding.faculty}</div>
              <div className="mt-1 text-sm text-gray-600">
                <span className="font-semibold">{responding.day}</span>
                {' → '}
                <span className="font-semibold text-indigo-600">{responding.requestedShift}</span>
              </div>
            </div>
            <label className="mt-4 block text-sm font-medium text-gray-700" htmlFor="admin-response">Admin Response</label>
            <textarea id="admin-response" rows={3} maxLength={300} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a note to faculty (optional)" className={`${fieldClass} mt-1`} />
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-gray-700 hover:bg-gray-200" onClick={() => setResponding(null)}>Cancel</button>
              <button type="button" disabled={saving} className="rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700 disabled:opacity-40" onClick={() => void submit('reject')}>
                <i className="fas fa-times" /> Reject
              </button>
              <button type="button" disabled={saving} className="rounded-md bg-green-600 px-4 py-2 text-white hover:bg-green-700 disabled:opacity-40" onClick={() => void submit('approve')}>
                <i className="fas fa-check" /> Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {details && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-600/50" onClick={() => setDetails(null)}>
          <div className="relative top-20 mx-auto w-full max-w-md rounded-md border bg-white p-5 shadow-lg" onClick={(event) => event.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Request Details</h3>
              <button type="button" className="text-gray-400 hover:text-gray-600" onClick={() => setDetails(null)} aria-label="Close">
                <i className="fas fa-times" />
              </button>
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-600">Admin Response:</div>
              <div className="mt-1 text-sm whitespace-pre-wrap text-gray-900">{details.response || 'No response provided'}</div>
            </div>
            <div className="mt-3 flex justify-between text-sm">
              <div>
                <div className="text-xs text-gray-600">Reviewed By:</div>
                <div className="font-medium">{details.reviewer || 'Unknown'}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-600">Reviewed At:</div>
                <div className="font-medium">{details.reviewedAt || 'N/A'}</div>
              </div>
            </div>
            <div className="mt-6 text-right">
              <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-gray-700 hover:bg-gray-200" onClick={() => setDetails(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
