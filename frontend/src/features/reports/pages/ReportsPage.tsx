import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Choice = { id: number; name: string }
type ReportType = { id: string; label: string }
type Job = {
  id: number
  label: string
  status: string
  progress: number
  row_count: number
  file_name: string
  created_by: string
  created_at: string
  can_download: boolean
}
type ReportOptions = {
  courses?: { id?: unknown; name?: unknown }[]
  classes?: { id?: unknown; name?: unknown }[]
  divisions?: { id?: unknown; name?: unknown }[]
  faculty?: { id?: unknown; name?: unknown }[]
  rooms?: { id?: unknown; name?: unknown }[]
  users?: { id?: unknown; name?: unknown }[]
}
type ReportList = {
  reports?: Record<string, unknown>[]
  types?: { id?: unknown; label?: unknown }[]
  can_generate?: boolean
  options?: ReportOptions
}

const jobColumns: TableColumnSpec[] = [
  { key: 'created_at', label: 'When' },
  { key: 'label', label: 'Report' },
  { key: 'status', label: 'Status' },
  { key: 'row_count', label: 'Rows' },
  { key: 'created_by', label: 'By' },
  { key: 'file_name', label: 'File', className: 'text-right' },
]

function jobValue(row: Job, key: string) {
  return row[key as keyof Job]
}

const fieldClass = 'w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20'
const labelClass = 'mb-1.5 ml-1 block text-[10px] font-bold tracking-wide text-gray-500 uppercase'

function choices(rows: { id?: unknown; name?: unknown }[] | undefined): Choice[] {
  return (rows || []).map((item) => ({ id: safeCount(item.id), name: safeText(item.name, 100) })).filter((item) => item.id > 0 && item.name)
}

function jobs(rows: Record<string, unknown>[] | undefined): Job[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id),
    label: safeText(row.label || row.report_type, 40),
    status: safeText(row.status, 20),
    progress: Math.min(safeCount(row.progress), 100),
    row_count: safeCount(row.row_count),
    file_name: safeText(row.file_name, 180),
    created_by: safeText(row.created_by, 50),
    created_at: safeText(row.created_at, 19),
    can_download: row.can_download === true,
  })).filter((row) => row.id > 0)
}

function JobProgress({ status, progress }: { status: string; progress: number }) {
  if (status === 'queued' || status === 'running') {
    const width = status === 'queued' ? 8 : Math.max(progress, 8)
    return (
      <div className="min-w-28">
        <div className="mb-1 flex justify-between text-[10px] font-bold tracking-wide text-gray-500 uppercase">
          <span>{status === 'queued' ? 'Queued' : 'Running'}</span>
          <span>{status === 'running' ? `${progress}%` : ''}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
          <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${width}%` }} />
        </div>
      </div>
    )
  }
  if (status === 'failed') return <span className="font-semibold text-red-600">Failed</span>
  if (status === 'completed') return <span className="font-semibold text-emerald-700">Completed</span>
  return <span className="text-gray-600">{status}</span>
}

export function ReportsPage() {
  const setPageHeader = useSetPageHeader()
  const [types, setTypes] = useState<ReportType[]>([])
  const [canGenerate, setCanGenerate] = useState(false)
  const [options, setOptions] = useState<Record<string, Choice[]>>({})
  const [rows, setRows] = useState<Job[]>([])
  const [reportType, setReportType] = useState('attendance')
  const [view, setView] = useState('class')
  const [entityId, setEntityId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [courseId, setCourseId] = useState('')
  const [classId, setClassId] = useState('')
  const [divisionId, setDivisionId] = useState('')
  const [facultyId, setFacultyId] = useState('')
  const [userId, setUserId] = useState('')
  const [status, setStatus] = useState('')
  const [role, setRole] = useState('')
  const [action, setAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const table = useDataTable(rows, jobColumns, jobValue)

  useEffect(() => {
    setPageHeader('Reports')
  }, [setPageHeader])

  function apply(data: ReportList) {
    const nextTypes = (data.types || []).map((item) => ({ id: safeText(item.id, 40), label: safeText(item.label, 40) })).filter((item) => item.id)
    setTypes(nextTypes)
    setCanGenerate(data.can_generate === true && nextTypes.length > 0)
    setReportType((current) => (nextTypes.some((item) => item.id === current) ? current : nextTypes[0]?.id || 'attendance'))
    setOptions({
      courses: choices(data.options?.courses),
      classes: choices(data.options?.classes),
      divisions: choices(data.options?.divisions),
      faculty: choices(data.options?.faculty),
      rooms: choices(data.options?.rooms),
      users: choices(data.options?.users),
    })
    setRows(jobs(data.reports))
  }

  useEffect(() => {
    void apiRequest<ReportList>('/api/reports')
      .then((data) => {
        apply(data)
        setError('')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [])

  const pending = rows.some((row) => row.status === 'queued' || row.status === 'running')
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(() => {
      void apiRequest<ReportList>('/api/reports').then(apply).catch(() => {})
    }, 2000)
    return () => window.clearInterval(timer)
  }, [pending])

  async function generate(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    const payload: Record<string, string | number> = { report_type: reportType }
    if (reportType === 'timetable') {
      payload.view = view
      payload.entity_id = Number(entityId)
    } else {
      if (startDate) payload.start_date = startDate
      if (endDate) payload.end_date = endDate
    }
    if (reportType === 'attendance' || reportType === 'invitations') {
      if (courseId) payload.course_id = Number(courseId)
      if (classId) payload.class_id = Number(classId)
      if (divisionId) payload.division_id = Number(divisionId)
    }
    if (reportType === 'shifts' && facultyId) payload.faculty_id = Number(facultyId)
    if (reportType === 'audit-logs' && userId) payload.user_id = Number(userId)
    if ((reportType === 'shifts' || reportType === 'invitations') && status) payload.status = status
    if (reportType === 'invitations' && role) payload.role = role
    if (reportType === 'audit-logs' && action.trim()) payload.action = action.trim()
    try {
      const result = await postJson<{ label?: unknown }>('/api/reports', payload)
      setNotice(`${safeText(result.label, 40) || 'Report'} queued. The bar updates here, and the download appears when it finishes.`)
      apply(await apiRequest<ReportList>('/api/reports'))
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const entities = view === 'faculty' ? options.faculty : view === 'room' ? options.rooms : options.classes

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <form onSubmit={generate} className="shrink-0 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-2.5 text-indigo-600"><i className="fas fa-chart-pie" /></div>
          <div>
            <h2 className="text-sm font-bold text-gray-800">Generate a report</h2>
            <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">Large files run in the background so the page does not time out</p>
          </div>
        </div>
        {error && <p className="mb-3 rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
        {notice && <p className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{notice}</p>}
        {canGenerate ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label>
              <span className={labelClass}>Report</span>
              <select value={reportType} onChange={(event) => { setReportType(event.target.value); setEntityId(''); setStatus(''); setRole('') }} className={fieldClass}>
                {types.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            {reportType === 'timetable' ? (
              <>
                <label>
                  <span className={labelClass}>View</span>
                  <select value={view} onChange={(event) => { setView(event.target.value); setEntityId('') }} className={fieldClass}>
                    <option value="class">Class</option>
                    <option value="faculty">Faculty</option>
                    <option value="room">Room</option>
                  </select>
                </label>
                <label>
                  <span className={labelClass}>{view === 'faculty' ? 'Faculty' : view === 'room' ? 'Room' : 'Class'}</span>
                  <select required value={entityId} onChange={(event) => setEntityId(event.target.value)} className={fieldClass}>
                    <option value="">Select</option>
                    {(entities || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
              </>
            ) : (
              <>
                <label>
                  <span className={labelClass}>From</span>
                  <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className={fieldClass} />
                </label>
                <label>
                  <span className={labelClass}>To</span>
                  <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className={fieldClass} />
                </label>
              </>
            )}
            {(reportType === 'attendance' || reportType === 'invitations') && (
              <>
                <Select label="Course" value={courseId} onChange={setCourseId} items={options.courses || []} />
                <Select label="Class" value={classId} onChange={setClassId} items={options.classes || []} />
                <Select label="Division" value={divisionId} onChange={setDivisionId} items={options.divisions || []} />
              </>
            )}
            {reportType === 'shifts' && (
              <>
                <Select label="Faculty" value={facultyId} onChange={setFacultyId} items={options.faculty || []} />
                <label>
                  <span className={labelClass}>Status</span>
                  <select value={status} onChange={(event) => setStatus(event.target.value)} className={fieldClass}>
                    <option value="">Any</option>
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                  </select>
                </label>
              </>
            )}
            {reportType === 'invitations' && (
              <>
                <label>
                  <span className={labelClass}>Role</span>
                  <select value={role} onChange={(event) => setRole(event.target.value)} className={fieldClass}>
                    <option value="">Any</option>
                    {['Teacher', 'Student', 'Admin', 'HOD'].map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label>
                  <span className={labelClass}>Status</span>
                  <input value={status} onChange={(event) => setStatus(event.target.value)} className={fieldClass} placeholder="Any" />
                </label>
              </>
            )}
            {reportType === 'audit-logs' && (
              <>
                <Select label="User" value={userId} onChange={setUserId} items={options.users || []} />
                <label>
                  <span className={labelClass}>Action</span>
                  <input value={action} onChange={(event) => setAction(event.target.value)} className={fieldClass} placeholder="Any" />
                </label>
              </>
            )}
            <div className="flex items-end">
              <button type="submit" disabled={saving || (reportType === 'timetable' && !entityId)} className="rounded-xl bg-gray-900 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">
                {saving ? 'Queuing...' : 'Queue report'}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-gray-500">You can review report jobs. Generating a new report needs export permission.</p>
        )}
      </form>

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
        <header className="shrink-0 border-b border-gray-100 px-5 py-3">
          <h3 className="text-sm font-bold text-gray-800">Report jobs</h3>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{rows.length} jobs</p>
        </header>
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <DataTableHead columns={jobColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 && <tr><td colSpan={6} className="px-6 py-16 text-center text-xs font-medium text-gray-400">No jobs yet. Queue a report or an export and it will appear here.</td></tr>}
              {rows.length > 0 && table.rows.length === 0 && <tr><td colSpan={6} className="px-6 py-10 text-center text-xs font-medium text-gray-400">No jobs match these filters.</td></tr>}
              {table.rows.map((row) => (
                <tr key={row.id} className="hover:bg-indigo-50/40">
                  <td className="px-5 py-2 text-gray-600">{row.created_at}</td>
                  <td className="px-5 py-2 font-semibold text-gray-800">{row.label}</td>
                  <td className="px-5 py-2"><JobProgress status={row.status} progress={row.progress} /></td>
                  <td className="px-5 py-2 text-gray-600">{row.status === 'completed' ? row.row_count : '-'}</td>
                  <td className="px-5 py-2 text-gray-600">{row.created_by || '-'}</td>
                  <td className="px-5 py-2 text-right">
                    {row.can_download ? (
                      <a href={`/api/reports/${row.id}/download`} className="font-bold text-indigo-600">Download</a>
                    ) : <span className="text-gray-400">{row.status === 'queued' || row.status === 'running' ? 'Processing' : '-'}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
      </section>
    </div>
  )
}

function Select({ label, value, onChange, items }: { label: string; value: string; onChange: (value: string) => void; items: Choice[] }) {
  return (
    <label>
      <span className={labelClass}>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={fieldClass}>
        <option value="">Any</option>
        {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
  )
}
