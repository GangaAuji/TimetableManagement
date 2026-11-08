import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Entry = {
  id: number
  date: string
  start: string
  end: string
  status: string
  approval: string
  notes: string
  original: string
  originalId: string
  proxy: string
  proxyId: string
  subject: string
  className: string
  division: string
  approvedBy: string
}

type Summary = { total: number; assigned: number; unassigned: number; pending: number; approved: number; rejected: number }

const emptySummary: Summary = { total: 0, assigned: 0, unassigned: 0, pending: 0, approved: 0, rejected: 0 }
const fieldClass = 'rounded-xl border border-gray-200/80 bg-white px-3 py-2 text-xs font-medium text-gray-600 shadow-sm outline-none'

function readEntry(row: Record<string, unknown>): Entry {
  return {
    id: safeCount(row.id),
    date: safeText(row.date, 12),
    start: safeText(row.start_time, 16),
    end: safeText(row.end_time, 16),
    status: safeText(row.status, 20),
    approval: safeText(row.approval, 20),
    notes: safeText(row.approval_notes, 200),
    original: safeText(row.original_faculty, 100),
    originalId: safeText(row.original_employee_id, 40),
    proxy: safeText(row.proxy_faculty, 100),
    proxyId: safeText(row.proxy_employee_id, 40),
    subject: safeText(row.subject, 100),
    className: safeText(row.class_name, 100),
    division: safeText(row.division_name, 50),
    approvedBy: safeText(row.approved_by, 80),
  }
}

function readSummary(row: Record<string, unknown> | undefined): Summary {
  if (!row) return emptySummary
  return {
    total: safeCount(row.total),
    assigned: safeCount(row.assigned),
    unassigned: safeCount(row.unassigned),
    pending: safeCount(row.pending),
    approved: safeCount(row.approved),
    rejected: safeCount(row.rejected),
  }
}

function initials(name: string) {
  const text = name.trim()
  return text ? text.slice(0, 2).toUpperCase() : 'NA'
}

function statusBadge(status: string) {
  if (status === 'ASSIGNED') return 'border-green-100 bg-green-50 text-green-700'
  if (status === 'UNASSIGNED') return 'border-red-100 bg-red-50 text-red-700'
  return 'border-yellow-100 bg-yellow-50 text-yellow-700'
}

function statusLabel(status: string) {
  if (status === 'ASSIGNED') return 'Assigned'
  if (status === 'UNASSIGNED') return 'Unassigned'
  if (!status) return ''
  return status.charAt(0) + status.slice(1).toLowerCase()
}

function pageWindow(page: number, total: number) {
  const start = Math.max(1, page - 2)
  const end = Math.min(total, page + 2)
  const pages: number[] = []
  for (let number = start; number <= end; number += 1) pages.push(number)
  return pages
}

function share(part: number, total: number) {
  if (total <= 0) return 0
  return Math.min(100, Math.round((part / total) * 100))
}

export function ProxyPage() {
  const setPageHeader = useSetPageHeader()
  const [entries, setEntries] = useState<Entry[]>([])
  const [summary, setSummary] = useState<Summary>(emptySummary)
  const [status, setStatus] = useState('')
  const [approval, setApproval] = useState('')
  const [draftFrom, setDraftFrom] = useState('')
  const [draftTo, setDraftTo] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [hasPrev, setHasPrev] = useState(false)
  const [hasNext, setHasNext] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setPageHeader('Faculty Substitution')
  }, [setPageHeader])

  useEffect(() => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (approval) params.set('approval_status', approval)
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    if (page > 1) params.set('page', String(page))
    const query = params.toString()
    const path = query ? `/api/proxy?${query}` : '/api/proxy'
    let active = true
    setLoading(true)
    void apiRequest<{ entries?: Record<string, unknown>[]; summary?: Record<string, unknown>; page?: number; total_pages?: number; has_prev?: boolean; has_next?: boolean }>(path)
      .then((data) => {
        if (!active) return
        setEntries((data.entries || []).map(readEntry))
        setSummary(readSummary(data.summary))
        setTotalPages(safeCount(data.total_pages))
        setHasPrev(data.has_prev === true)
        setHasNext(data.has_next === true)
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
  }, [approval, dateFrom, dateTo, page, status])

  const cards = [
    { label: 'Total', value: summary.total, color: 'text-gray-800', bar: 'bg-blue-600', track: 'bg-blue-100', width: 100 },
    { label: 'Assigned', value: summary.assigned, color: 'text-green-600', bar: 'bg-green-500', track: 'bg-green-100', width: share(summary.assigned, summary.total) },
    { label: 'Unassigned', value: summary.unassigned, color: 'text-red-600', bar: 'bg-red-500', track: 'bg-red-100', width: share(summary.unassigned, summary.total) },
    { label: 'Pending', value: summary.pending, color: 'text-yellow-600', bar: 'bg-yellow-500', track: 'bg-yellow-100', width: 100 },
    { label: 'Approved', value: summary.approved, color: 'text-emerald-600', bar: 'bg-emerald-500', track: 'bg-emerald-100', width: 100 },
    { label: 'Rejected', value: summary.rejected, color: 'text-gray-600', bar: 'bg-gray-500', track: 'bg-gray-100', width: 100 },
  ]

  return (
    <section className="flex flex-1 flex-col gap-2">
      <div className="grid shrink-0 grid-cols-2 gap-2 lg:grid-cols-6">
        {cards.map((card) => (
          <div key={card.label} className="flex flex-col justify-between rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
            <p className="mb-1 text-[10px] font-bold tracking-wider text-gray-400 uppercase">{card.label}</p>
            <div className="flex items-end justify-between">
              <span className={`text-xl font-bold ${card.color}`}>{card.value}</span>
              <div className={`h-1.5 w-12 overflow-hidden rounded-full ${card.track}`}>
                <div className={`h-full ${card.bar}`} style={{ width: `${card.width}%` }} />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex shrink-0 flex-col justify-between gap-3 rounded-t-2xl border border-gray-200/80 bg-white p-3.5 shadow-sm md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <div className="rounded-xl border border-orange-100 bg-orange-50 p-2.5 text-orange-600 shadow-sm">
            <i className="fas fa-user-clock text-lg" />
          </div>
          <div>
            <h2 className="text-sm leading-tight font-bold tracking-tight text-gray-800">Substitution Log</h2>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
              <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">Date: {dateTo || 'Current'}</p>
            </div>
          </div>
        </div>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setPage(1)
            setDateFrom(draftFrom)
            setDateTo(draftTo)
          }}
        >
          <select
            aria-label="Proxy status"
            value={status}
            onChange={(event) => {
              setPage(1)
              setStatus(event.target.value)
            }}
            className={fieldClass}
          >
            <option value="">Proxy Status</option>
            <option value="ASSIGNED">Assigned</option>
            <option value="UNASSIGNED">Unassigned</option>
            <option value="PENDING">Pending</option>
            <option value="REJECTED">Rejected</option>
          </select>
          <select
            aria-label="Approval status"
            value={approval}
            onChange={(event) => {
              setPage(1)
              setApproval(event.target.value)
            }}
            className={fieldClass}
          >
            <option value="">Approval Status</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
          </select>
          <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-2 py-1">
            <input type="date" aria-label="From" value={draftFrom} onChange={(event) => setDraftFrom(event.target.value)} className="w-28 bg-transparent text-xs text-gray-600 outline-none" />
            <span className="text-[10px] text-gray-400">to</span>
            <input type="date" aria-label="To" value={draftTo} onChange={(event) => setDraftTo(event.target.value)} className="w-28 bg-transparent text-xs text-gray-600 outline-none" />
            <button type="submit" className="ml-1 text-orange-600 hover:text-orange-700" aria-label="Apply dates">
              <i className="fas fa-arrow-right text-xs" />
            </button>
          </div>
        </form>
      </div>

      {error && <p className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}

      <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-b-2xl border border-gray-200 bg-white shadow-sm">
        <div className="flex-1 overflow-auto">
          <table className="w-full border-collapse text-left">
            <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
              <tr>
                {['Date & Time', 'Original Faculty', 'Assigned Proxy', 'Class Info', 'Status', 'Approval'].map((label) => (
                  <th key={label} className={`px-5 py-2.5 text-[10px] font-bold tracking-wider text-gray-400 uppercase ${label === 'Status' ? 'text-center' : 'text-left'}`}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white text-xs">
              {loading && (
                <tr><td colSpan={6} className="px-6 py-10 text-center text-gray-400">Loading proxy records…</td></tr>
              )}
              {!loading && entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center text-gray-400">
                      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gray-50">
                        <i className="fas fa-search text-gray-300" />
                      </div>
                      <p className="text-xs font-medium">No proxy records match your filters.</p>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-orange-50/30">
                  <td className="px-5 py-2 whitespace-nowrap">
                    <div className="font-bold text-gray-800">{entry.date}</div>
                    <div className="mt-0.5 flex items-center text-[10px] text-gray-500">
                      <i className="far fa-clock mr-1 text-gray-400" />
                      {entry.start} - {entry.end}
                    </div>
                  </td>
                  <td className="px-5 py-2 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full border border-red-100 bg-red-50 text-[10px] font-bold text-red-600">{initials(entry.original)}</div>
                      <div>
                        <p className="font-medium text-gray-900">{entry.original}</p>
                        <p className="text-[9px] text-gray-400">{entry.originalId}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-2 whitespace-nowrap">
                    {entry.proxy ? (
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full border border-green-100 bg-green-50 text-[10px] font-bold text-green-600">{initials(entry.proxy)}</div>
                        <div>
                          <p className="font-medium text-gray-900">{entry.proxy}</p>
                          <p className="text-[9px] text-gray-400">{entry.proxyId}</p>
                        </div>
                      </div>
                    ) : (
                      <span className="text-[10px] text-gray-400 italic">Not Assigned</span>
                    )}
                  </td>
                  <td className="px-5 py-2 whitespace-nowrap">
                    <span className="font-medium text-gray-800">{entry.subject}</span>
                    <div className="mt-0.5 flex items-center gap-1">
                      <span className="rounded border border-gray-200 bg-gray-100 px-1.5 py-0.5 text-[9px] font-bold text-gray-600">{entry.className}</span>
                      <span className="text-[9px] text-gray-400">{entry.division}</span>
                    </div>
                  </td>
                  <td className="px-5 py-2 text-center">
                    <span className={`inline-flex rounded border px-2 py-0.5 text-[9px] font-bold tracking-wide uppercase ${statusBadge(entry.status)}`}>{statusLabel(entry.status)}</span>
                  </td>
                  <td className="px-5 py-2">
                    {entry.approval === 'APPROVED' && (
                      <div>
                        <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-600"><i className="fas fa-check-circle" /> Approved</span>
                        {entry.approvedBy && <p className="mt-0.5 text-[9px] text-gray-400">by {entry.approvedBy}</p>}
                      </div>
                    )}
                    {entry.approval === 'REJECTED' && (
                      <div>
                        <span className="flex items-center gap-1 text-[10px] font-bold text-rose-600"><i className="fas fa-times-circle" /> Rejected</span>
                        {entry.notes && <p className="mt-0.5 max-w-[100px] truncate text-[9px] text-gray-400 italic" title={entry.notes}>{entry.notes}</p>}
                      </div>
                    )}
                    {entry.approval !== 'APPROVED' && entry.approval !== 'REJECTED' && (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-gray-400"><i className="far fa-clock" /> Pending</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="flex h-12 shrink-0 items-center justify-between border-t border-gray-200 bg-gray-50/80 px-5">
            <span className="text-[10px] font-bold tracking-wider text-gray-500 uppercase">Page <span className="text-gray-800">{page}</span> of {totalPages}</span>
            <div className="flex gap-1.5">
              {hasPrev && (
                <button type="button" className="flex h-7 items-center rounded-lg border border-gray-200 bg-white px-3 text-[10px] font-bold text-gray-600 shadow-sm hover:text-orange-600" onClick={() => setPage((value) => value - 1)}>Prev</button>
              )}
              {pageWindow(page, totalPages).map((number) => (
                <button
                  key={number}
                  type="button"
                  className={`flex h-7 items-center rounded-lg px-3 text-[10px] font-bold shadow-sm ${number === page ? 'bg-orange-600 text-white' : 'border border-gray-200 bg-white text-gray-600 hover:text-orange-600'}`}
                  onClick={() => setPage(number)}
                >
                  {number}
                </button>
              ))}
              {hasNext && (
                <button type="button" className="flex h-7 items-center rounded-lg border border-gray-200 bg-white px-3 text-[10px] font-bold text-gray-600 shadow-sm hover:text-orange-600" onClick={() => setPage((value) => value + 1)}>Next</button>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

export { MyProxyPage } from '../../teacher/pages/FacultyPortal'
