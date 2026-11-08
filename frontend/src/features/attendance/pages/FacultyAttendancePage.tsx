import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { Stat, messageFrom } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Activity = {
  facultyId: number
  faculty: string
  employeeId: string
  department: string
  date: string
  status: string
  shift: string
  start: string
  end: string
  markedBy: string
  markedAt: string
}

type Summary = {
  facultyId: number
  faculty: string
  employeeId: string
  department: string
  shifts: number
  present: number
  late: number
  absent: number
  percentage: number
}

type TodayShift = { shift: string; marked: number; present: number; late: number; absent: number }

const fieldClass = 'mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800'

function percentText(value: number) {
  if (!Number.isFinite(value)) return '—'
  return `${Math.min(Math.max(value, 0), 100).toFixed(2)}%`
}

function statusClass(status: string) {
  if (status === 'Present') return 'bg-green-50 text-green-700'
  if (status === 'Late') return 'bg-amber-50 text-amber-700'
  if (status === 'Absent') return 'bg-red-50 text-red-700'
  return 'bg-gray-100 text-gray-500'
}

export function FacultyAttendancePage() {
  const setPageHeader = useSetPageHeader()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [perPage, setPerPage] = useState('20')
  const [page, setPage] = useState(1)
  const [applied, setApplied] = useState({ q: '', status: '', dateFrom: '', dateTo: '', perPage: '20' })
  const [stats, setStats] = useState({ faculty: 0, records: 0, present: 0, late: 0, absent: 0, percentage: 0 })
  const [today, setToday] = useState<TodayShift[]>([])
  const [rows, setRows] = useState<Activity[]>([])
  const [summary, setSummary] = useState<Summary[]>([])
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [available, setAvailable] = useState(true)
  const [error, setError] = useState('')

  function load(nextPage: number, filters = applied) {
    const search = new URLSearchParams({ page: String(nextPage), per_page: filters.perPage })
    if (filters.q) search.set('q', filters.q)
    if (filters.status) search.set('status', filters.status)
    if (filters.dateFrom) search.set('date_from', filters.dateFrom)
    if (filters.dateTo) search.set('date_to', filters.dateTo)
    return apiRequest<Record<string, unknown>>(`/api/attendance/faculty?${search.toString()}`).then((data) => {
      const figures = (data.stats || {}) as Record<string, unknown>
      const activity = Array.isArray(data.records) ? data.records : []
      const people = Array.isArray(data.summary) ? data.summary : []
      const shifts = Array.isArray(data.today) ? data.today : []
      setAvailable(data.available !== false)
      setStats({
        faculty: safeCount(figures.faculty),
        records: safeCount(figures.records),
        present: safeCount(figures.present),
        late: safeCount(figures.late),
        absent: safeCount(figures.absent),
        percentage: Number(figures.percentage) || 0,
      })
      setToday(shifts.map((item) => {
        const row = item as Record<string, unknown>
        return { shift: safeText(row.shift, 80), marked: safeCount(row.marked), present: safeCount(row.present), late: safeCount(row.late), absent: safeCount(row.absent) }
      }))
      setRows(activity.map((item) => {
        const row = item as Record<string, unknown>
        return {
          facultyId: safeCount(row.faculty_id),
          faculty: safeText(row.faculty, 100),
          employeeId: safeText(row.employee_id, 20),
          department: safeText(row.department, 100),
          date: safeText(row.date, 10),
          status: safeText(row.status, 20),
          shift: safeText(row.shift, 80),
          start: safeText(row.start_time, 8),
          end: safeText(row.end_time, 8),
          markedBy: safeText(row.marked_by, 50),
          markedAt: safeText(row.marked_at, 20),
        }
      }))
      setSummary(people.map((item) => {
        const row = item as Record<string, unknown>
        return {
          facultyId: safeCount(row.faculty_id),
          faculty: safeText(row.faculty, 100),
          employeeId: safeText(row.employee_id, 20),
          department: safeText(row.department, 100),
          shifts: safeCount(row.shifts),
          present: safeCount(row.present),
          late: safeCount(row.late),
          absent: safeCount(row.absent),
          percentage: Number(row.percentage) || 0,
        }
      }))
      setPage(safeCount(data.page) || 1)
      setTotal(safeCount(data.total))
      setTotalPages(safeCount(data.total_pages) || 1)
    })
  }

  useEffect(() => {
    setPageHeader('Faculty attendance')
    void load(1).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function show() {
    const next = { q: query.trim(), status, dateFrom, dateTo, perPage }
    setApplied(next)
    setError('')
    void load(1, next).catch((reason: unknown) => setError(messageFrom(reason)))
  }

  function turn(nextPage: number) {
    setError('')
    void load(nextPage).catch((reason: unknown) => setError(messageFrom(reason)))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Last 30 days</h3>
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Faculty" value={stats.faculty} />
        <Stat label="Records" value={stats.records} />
        <Stat label="Present" value={stats.present} />
        <Stat label="Late" value={stats.late} />
        <Stat label="Absent" value={stats.absent} />
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Attendance</p>
          <p className="mt-1 text-xl font-bold text-gray-800">{percentText(stats.percentage)}</p>
        </div>
      </div>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {!available ? <p className="text-sm text-gray-500">Faculty attendance is not available yet.</p> : null}
      <section className="rounded-2xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-bold text-gray-800">Today’s snapshot</h2>
        {today.length === 0 ? <p className="mt-2 text-sm text-gray-500">No faculty attendance marked today.</p> : (
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {today.map((shift) => (
              <div key={shift.shift} className="rounded-xl border border-gray-100 p-3">
                <p className="font-semibold text-gray-800">{shift.shift}</p>
                <p className="mt-1 text-xs text-gray-500">{shift.marked} marked · {shift.present} present · {shift.late} late · {shift.absent} absent</p>
              </div>
            ))}
          </div>
        )}
      </section>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        <label className="text-sm text-gray-700 lg:col-span-2">Search
          <input className={fieldClass} value={query} maxLength={80} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Status
          <select className={fieldClass} value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option>Present</option>
            <option>Late</option>
            <option>Absent</option>
          </select>
        </label>
        <label className="text-sm text-gray-700">From
          <input className={fieldClass} type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">To
          <input className={fieldClass} type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Rows
          <select className={fieldClass} value={perPage} onChange={(event) => setPerPage(event.target.value)}>
            <option>20</option>
            <option>50</option>
            <option>100</option>
          </select>
        </label>
      </div>
      <div className="flex justify-end">
        <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white" onClick={show}>Show</button>
      </div>
      <div className="min-h-[280px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Faculty</th>
                <th className="px-4 py-3">Shift and time</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Marked by</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-16 text-center text-gray-500">No attendance matches these filters.</td></tr>
              ) : rows.map((row) => (
                <tr key={`${row.facultyId}-${row.date}-${row.shift}-${row.markedAt}`}>
                  <td className="px-4 py-3">
                    <Link className="font-semibold text-indigo-600" to={`/admin/faculty/${row.facultyId}`}>{row.faculty}</Link>
                    <p className="text-xs text-gray-400">{row.employeeId}{row.department ? ` · ${row.department}` : ''} · {row.date}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{row.shift || '—'}{row.start ? ` · ${row.start}–${row.end}` : ''}</td>
                  <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass(row.status)}`}>{row.status || '—'}</span></td>
                  <td className="px-4 py-3 text-gray-700">{row.markedBy || '—'}<div className="text-xs text-gray-400">{row.markedAt}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>{total} records</span>
        <div className="flex gap-2">
          <button type="button" className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40" disabled={page <= 1} onClick={() => turn(page - 1)}>Prev</button>
          <span className="px-2 py-1">{page} / {totalPages}</span>
          <button type="button" className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40" disabled={page >= totalPages} onClick={() => turn(page + 1)}>Next</button>
        </div>
      </div>
      <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <header className="border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-bold text-gray-800">30-day performance</h2>
        </header>
        <div className="overflow-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Faculty</th>
                <th className="px-4 py-3">Shifts</th>
                <th className="px-4 py-3">Present</th>
                <th className="px-4 py-3">Late</th>
                <th className="px-4 py-3">Absent</th>
                <th className="px-4 py-3">Attendance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {summary.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-500">No faculty attendance in the last 30 days.</td></tr>
              ) : summary.map((row) => (
                <tr key={row.facultyId}>
                  <td className="px-4 py-3">
                    <Link className="font-semibold text-indigo-600" to={`/admin/faculty/${row.facultyId}`}>{row.faculty}</Link>
                    <p className="text-xs text-gray-400">{row.employeeId}{row.department ? ` · ${row.department}` : ''}</p>
                  </td>
                  <td className="px-4 py-3">{row.shifts}</td>
                  <td className="px-4 py-3">{row.present}</td>
                  <td className="px-4 py-3">{row.late}</td>
                  <td className="px-4 py-3">{row.absent}</td>
                  <td className="px-4 py-3 font-semibold text-gray-800">{percentText(row.percentage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
