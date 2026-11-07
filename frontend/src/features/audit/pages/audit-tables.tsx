import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TablePager, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import { Dialog } from '../../academics/ui'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type LogRow = {
  id: string
  user_id: string
  username: string
  action: string
  entity_type: string
  status: string
  ip_address: string
  created_at: string
}
type SessionRow = { session_id: string; username: string; ip_address: string; last_activity: string }
type FailedRow = { username: string; reason: string; attempted_at: string }

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const secondaryButton = 'rounded-xl border px-3 py-2 text-xs font-bold'
const logColumns: TableColumnSpec[] = [
  { key: 'created_at', label: 'Timestamp' },
  { key: 'username', label: 'User' },
  { key: 'ip_address', label: 'IP address' },
  { key: 'action', label: 'Action' },
  { key: 'entity_type', label: 'Area' },
  { key: 'status', label: 'Outcome' },
]
const sessionColumns: TableColumnSpec[] = [
  { key: 'username', label: 'User' },
  { key: 'ip_address', label: 'IP address' },
  { key: 'last_activity', label: 'Last activity' },
]
const failedColumns: TableColumnSpec[] = [
  { key: 'username', label: 'User' },
  { key: 'reason', label: 'Reason' },
  { key: 'attempted_at', label: 'When' },
]

function useServerFilters() {
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [appliedSearch, setAppliedSearch] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({})
  const [page, setPage] = useState(1)
  const [sortKey, setSortKey] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const nextSearch = search.trim()
      const nextFilters = Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, value.trim()]))
      setAppliedSearch((current) => (current === nextSearch ? current : nextSearch))
      setAppliedFilters((current) => (JSON.stringify(current) === JSON.stringify(nextFilters) ? current : nextFilters))
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [filters, search])
  const activeCount = (search.trim() ? 1 : 0) + Object.values(filters).filter((value) => value.trim()).length + (sortKey ? 1 : 0)
  function clear() {
    setSearch('')
    setFilters({})
    setSortKey('')
    setSortDir('asc')
  }
  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }
  return { search, setSearch, filters, setFilters, filtersOpen, setFiltersOpen, appliedSearch, appliedFilters, page, setPage, sortKey, sortDir, toggleSort, activeCount, clear }
}

function sortedRows<T extends Record<string, string>>(rows: T[], sortKey: string, sortDir: 'asc' | 'desc') {
  if (!sortKey) return rows
  const direction = sortDir === 'asc' ? 1 : -1
  return [...rows].sort((left, right) => (left[sortKey] || '').localeCompare(right[sortKey] || '', undefined, { numeric: true, sensitivity: 'base' }) * direction)
}

function statusTone(status: string) {
  const value = status.toLowerCase()
  if (value === 'failed' || value === 'error' || value === 'denied') return 'bg-red-50 text-red-700'
  if (value === 'success' || value === 'ok' || value === 'active') return 'bg-emerald-50 text-emerald-700'
  return 'bg-gray-100 text-gray-600'
}

function actionTone(action: string) {
  const value = action.toLowerCase()
  if (value.includes('delete') || value.includes('revoke') || value.includes('fail')) return 'bg-red-50 text-red-700'
  if (value.includes('password')) return 'bg-amber-50 text-amber-700'
  if (value.includes('login')) return 'bg-emerald-50 text-emerald-700'
  return 'bg-indigo-50 text-indigo-700'
}

function logsFrom(value: unknown): LogRow[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((row) => {
    if (!row || typeof row !== 'object') return []
    const record = row as Record<string, unknown>
    const id = String(safeCount(record.id))
    if (id === '0') return []
    return [{
      id,
      user_id: String(safeCount(record.user_id)),
      username: safeText(record.username, 50),
      action: safeText(record.action, 80),
      entity_type: safeText(record.entity_type, 40),
      status: safeText(record.status, 20),
      ip_address: safeText(record.ip_address, 45),
      created_at: safeText(record.created_at, 19),
    }]
  })
}

function putFilter(params: URLSearchParams, filters: Record<string, string>, key: string, name: string) {
  const value = filters[key]
  if (value) params.set(name, value)
}

export function AuditLogsPage() {
  const setPageHeader = useSetPageHeader()
  const table = useServerFilters()
  const [rows, setRows] = useState<LogRow[]>([])
  const [perPage, setPerPage] = useState(25)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [exporting, setExporting] = useState(false)
  const [detail, setDetail] = useState<Record<string, string> | null>(null)
  const [activity, setActivity] = useState<{ username: string; role: string; lines: string[] } | null>(null)
  const shown = useMemo(() => sortedRows(rows, table.sortKey, table.sortDir), [rows, table.sortKey, table.sortDir])

  useEffect(() => { setPageHeader('Audit logs') }, [setPageHeader])

  useEffect(() => {
    const params = new URLSearchParams({ page: String(table.page), per_page: String(perPage) })
    if (table.appliedSearch) params.set('q', table.appliedSearch)
    putFilter(params, table.appliedFilters, 'username', 'username')
    putFilter(params, table.appliedFilters, 'action', 'action')
    putFilter(params, table.appliedFilters, 'ip_address', 'ip')
    putFilter(params, table.appliedFilters, 'entity_type', 'area')
    putFilter(params, table.appliedFilters, 'status', 'status')
    putFilter(params, table.appliedFilters, 'created_at', 'when')
    void apiRequest<Record<string, unknown>>(`/api/audit?${params}`).then((data) => {
      setRows(logsFrom(data.logs))
      setTotal(safeCount(data.total))
      setTotalPages(Math.max(safeCount(data.total_pages), 1))
    }).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [table.appliedFilters, table.appliedSearch, table.page, perPage])

  async function openDetail(id: string) {
    setError('')
    try {
      const data = await apiRequest<{ log?: Record<string, unknown> }>(`/api/audit/${id}`)
      const log = data.log || {}
      const changes = (value: unknown) => {
        if (!value || typeof value !== 'object') return ''
        return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${safeText(key, 40)}: ${safeText(item, 200)}`).join('\n')
      }
      setDetail({
        username: safeText(log.username, 50),
        action: safeText(log.action, 80),
        area: safeText(log.entity_type, 40),
        status: safeText(log.status, 20),
        when: safeText(log.created_at, 19),
        ip: safeText(log.ip_address, 45),
        url: safeText(log.request_url, 180),
        before: changes(log.old_values),
        after: changes(log.new_values),
      })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function openUser(id: string) {
    if (!id || id === '0') return
    setError('')
    try {
      const data = await apiRequest<{ user?: Record<string, unknown>; summary?: Record<string, unknown>[] }>(`/api/audit/users/${id}`)
      const user = data.user || {}
      const lines = (data.summary || []).map((row) => `${safeText(row.action, 80)} · ${safeCount(row.count)} · ${safeText(row.last_activity, 19)}`)
      setActivity({ username: safeText(user.username, 50), role: safeText(user.role, 50), lines })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function exportCsv() {
    setError('')
    setNotice('')
    setExporting(true)
    try {
      await postJson('/api/exports', {
        kind: 'audit',
        q: table.appliedSearch,
        username: table.appliedFilters.username || '',
        action: table.appliedFilters.action || '',
        ip: table.appliedFilters.ip_address || '',
        area: table.appliedFilters.entity_type || '',
        status: table.appliedFilters.status || '',
        when: table.appliedFilters.created_at || '',
      })
      setNotice('Export queued.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setExporting(false)
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Audit logs</h2>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{total} records</p>
        </div>
        <div className="flex gap-2">
          <a href="/admin/audit" className={secondaryButton}>Overview</a>
          <button type="button" disabled={exporting} onClick={() => void exportCsv()} className={primaryButton}>Export</button>
        </div>
      </header>
      {error && <p className="px-5 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="px-5 py-2 text-xs text-emerald-700">{notice} <Link to="/admin/reports" className="font-bold underline">Open Reports</Link> to follow the progress and download the file.</p>}
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={total} source={total} activeCount={table.activeCount} onClear={table.clear} />
      <div className="flex-1 overflow-auto">
        <table className="w-full min-w-[860px] text-left text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead columns={logColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={(key, value) => table.setFilters((current) => ({ ...current, [key]: value }))} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {shown.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No audit records found.</td></tr>
            ) : shown.map((row) => (
              <tr key={row.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 whitespace-nowrap text-gray-600">{row.created_at || '—'}</td>
                <td className="px-4 py-3"><button type="button" className="font-bold text-gray-900 underline decoration-gray-300 underline-offset-2" onClick={() => void openUser(row.user_id)}>{row.username || '—'}</button></td>
                <td className="px-4 py-3 text-gray-500">{row.ip_address || '—'}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${actionTone(row.action)}`}>{row.action || '—'}</span></td>
                <td className="px-4 py-3 text-gray-600">{row.entity_type || '—'}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusTone(row.status)}`}>{row.status || '—'}</span></td>
                <td className="px-4 py-3 text-right"><button type="button" className="rounded-lg border px-2 py-1 text-[10px] font-bold text-gray-700" onClick={() => void openDetail(row.id)}>Details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={totalPages} pageSize={perPage} onPage={table.setPage} onPageSize={(size) => { setPerPage(size); table.setPage(1) }} />
      {detail && (
        <Dialog title="Audit details" onClose={() => setDetail(null)}>
          <dl className="space-y-2 text-sm text-gray-700">
            <div><dt className="text-xs font-semibold text-gray-500">User</dt><dd>{detail.username || '—'}</dd></div>
            <div><dt className="text-xs font-semibold text-gray-500">Action</dt><dd>{detail.action}</dd></div>
            <div><dt className="text-xs font-semibold text-gray-500">Area</dt><dd>{detail.area || '—'}</dd></div>
            <div><dt className="text-xs font-semibold text-gray-500">Status</dt><dd>{detail.status || '—'}</dd></div>
            <div><dt className="text-xs font-semibold text-gray-500">When</dt><dd>{detail.when || '—'}</dd></div>
            <div><dt className="text-xs font-semibold text-gray-500">IP address</dt><dd>{detail.ip || '—'}</dd></div>
            {detail.url && <div><dt className="text-xs font-semibold text-gray-500">Address</dt><dd className="break-all">{detail.url}</dd></div>}
            {detail.before && <div><dt className="text-xs font-semibold text-gray-500">Previous values</dt><dd className="whitespace-pre-wrap">{detail.before}</dd></div>}
            {detail.after && <div><dt className="text-xs font-semibold text-gray-500">New values</dt><dd className="whitespace-pre-wrap">{detail.after}</dd></div>}
          </dl>
        </Dialog>
      )}
      {activity && (
        <Dialog title={`${activity.username} activity`} onClose={() => setActivity(null)}>
          <p className="text-sm text-gray-600">{activity.role}</p>
          {activity.lines.length === 0 ? <p className="mt-3 text-sm text-gray-500">No activity in the last 30 days.</p> : (
            <ul className="mt-3 space-y-1 text-sm text-gray-700">{activity.lines.map((line) => <li key={line}>{line}</li>)}</ul>
          )}
        </Dialog>
      )}
    </section>
  )
}

export function AuditSessionsPage() {
  const setPageHeader = useSetPageHeader()
  const table = useServerFilters()
  const [rows, setRows] = useState<SessionRow[]>([])
  const [perPage, setPerPage] = useState(25)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState('')
  const [saving, setSaving] = useState(false)
  const [tick, setTick] = useState(0)
  const shown = useMemo(() => sortedRows(rows, table.sortKey, table.sortDir), [rows, table.sortKey, table.sortDir])

  useEffect(() => { setPageHeader('Sessions') }, [setPageHeader])

  useEffect(() => {
    const params = new URLSearchParams({ page: String(table.page), per_page: String(perPage) })
    if (table.appliedSearch) params.set('q', table.appliedSearch)
    putFilter(params, table.appliedFilters, 'username', 'username')
    putFilter(params, table.appliedFilters, 'ip_address', 'ip')
    putFilter(params, table.appliedFilters, 'last_activity', 'when')
    void apiRequest<Record<string, unknown>>(`/api/audit/sessions?${params}`).then((data) => {
      setRows((Array.isArray(data.sessions) ? data.sessions : []).flatMap((row) => {
        if (!row || typeof row !== 'object') return []
        const record = row as Record<string, unknown>
        const sessionId = safeText(record.session_id, 128)
        if (!sessionId) return []
        return [{ session_id: sessionId, username: safeText(record.username, 50), ip_address: safeText(record.ip_address, 45), last_activity: safeText(record.last_activity, 19) }]
      }))
      setTotal(safeCount(data.total))
      setTotalPages(Math.max(safeCount(data.total_pages), 1))
    }).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [table.appliedFilters, table.appliedSearch, table.page, perPage, tick])

  async function revoke() {
    if (!pending) return
    setSaving(true)
    setError('')
    try {
      await postJson('/api/audit/sessions/revoke', { session_id: pending })
      setNotice('Session revoked.')
      setPending('')
      if (rows.length === 1 && table.page > 1) table.setPage(table.page - 1)
      else setTick((value) => value + 1)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Active sessions</h2>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{total} open</p>
        </div>
        <a href="/admin/audit" className={secondaryButton}>Overview</a>
      </header>
      {error && <p className="px-5 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="px-5 py-2 text-xs text-emerald-700">{notice}</p>}
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={total} source={total} activeCount={table.activeCount} onClear={table.clear} />
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead columns={sessionColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={(key, value) => table.setFilters((current) => ({ ...current, [key]: value }))} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {shown.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500">No active sessions.</td></tr>
            ) : shown.map((row) => (
              <tr key={row.session_id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-bold text-gray-900">{row.username || 'Unknown'}</td>
                <td className="px-4 py-3 text-gray-500">{row.ip_address || '—'}</td>
                <td className="px-4 py-3 text-gray-600">{row.last_activity || '—'}</td>
                <td className="px-4 py-3 text-right"><button type="button" className="rounded-lg border border-red-200 px-2 py-1 text-[10px] font-bold text-red-600" onClick={() => setPending(row.session_id)}>Revoke</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={totalPages} pageSize={perPage} onPage={table.setPage} onPageSize={(size) => { setPerPage(size); table.setPage(1) }} />
      {pending && (
        <Dialog title="Revoke session?" onClose={() => setPending('')}>
          <p className="text-sm text-gray-600">This signs that browser out.</p>
          <button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void revoke()}>Revoke</button>
        </Dialog>
      )}
    </section>
  )
}

export function AuditFailedPage() {
  const setPageHeader = useSetPageHeader()
  const table = useServerFilters()
  const [rows, setRows] = useState<FailedRow[]>([])
  const [perPage, setPerPage] = useState(25)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const shown = useMemo(() => sortedRows(rows, table.sortKey, table.sortDir), [rows, table.sortKey, table.sortDir])

  useEffect(() => { setPageHeader('Failed logins') }, [setPageHeader])

  useEffect(() => {
    const params = new URLSearchParams({ page: String(table.page), per_page: String(perPage) })
    if (table.appliedSearch) params.set('q', table.appliedSearch)
    putFilter(params, table.appliedFilters, 'username', 'username')
    putFilter(params, table.appliedFilters, 'reason', 'reason')
    putFilter(params, table.appliedFilters, 'attempted_at', 'when')
    void apiRequest<Record<string, unknown>>(`/api/audit/failed-logins?${params}`).then((data) => {
      setRows((Array.isArray(data.failed_logins) ? data.failed_logins : []).flatMap((row) => {
        if (!row || typeof row !== 'object') return []
        const record = row as Record<string, unknown>
        return [{ username: safeText(record.username, 50), reason: safeText(record.reason, 80), attempted_at: safeText(record.attempted_at, 19) }]
      }))
      setTotal(safeCount(data.total))
      setTotalPages(Math.max(safeCount(data.total_pages), 1))
    }).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [table.appliedFilters, table.appliedSearch, table.page, perPage])

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Failed logins</h2>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{total} attempts</p>
        </div>
        <a href="/admin/audit" className={secondaryButton}>Overview</a>
      </header>
      {error && <p className="px-5 py-2 text-xs text-red-700">{error}</p>}
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={total} source={total} activeCount={table.activeCount} onClear={table.clear} />
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead columns={failedColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={(key, value) => table.setFilters((current) => ({ ...current, [key]: value }))} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {shown.length === 0 ? (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-gray-500">No failed logins.</td></tr>
            ) : shown.map((row, index) => (
              <tr key={`${row.username}-${row.attempted_at}-${index}`} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-bold text-gray-900">{row.username || 'Unknown'}</td>
                <td className="px-4 py-3 text-gray-600">{row.reason || 'Failed'}</td>
                <td className="px-4 py-3 text-gray-500">{row.attempted_at || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={totalPages} pageSize={perPage} onPage={table.setPage} onPageSize={(size) => { setPerPage(size); table.setPage(1) }} />
    </section>
  )
}
