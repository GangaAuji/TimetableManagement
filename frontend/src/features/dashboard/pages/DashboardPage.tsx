import { FailureNotice } from '../../../shared/components/success-notice'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { hasPermission } from '../../../app/page-access'
import type { SessionInfo } from '../../../shared/api/endpoints'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError } from '../../../shared/api/client'
import { getDashboardSummary, type DashboardSummary, type TodayClass } from '../../../shared/api/endpoints'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { pageGrid, pageStack } from '../../../shared/layout/page-frame'

const weekDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function typeBadge(sessionType: string) {
  if (sessionType === 'Theory') return 'border border-blue-100 bg-blue-50 text-blue-700'
  if (sessionType === 'Practical') return 'border border-purple-100 bg-purple-50 text-purple-700'
  return 'border border-green-100 bg-green-50 text-green-700'
}

export function DashboardHeader({ canGenerate }: { canGenerate: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h2 className="truncate text-lg font-bold tracking-tight text-gray-900 sm:text-xl">Dashboard Overview</h2>
        <p className="hidden truncate text-sm font-normal text-gray-500 sm:block">Welcome back, here's what's happening today.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {canGenerate ? (
          <a
            href="/admin/timetable/generate"
            className="flex items-center rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-md transition-all hover:bg-indigo-700 sm:text-sm"
          >
            <i className="fas fa-magic mr-2" /> Generate
          </a>
        ) : null}
      </div>
    </div>
  )
}

export function DashboardRoute() {
  const setPageHeader = useSetPageHeader()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  const canGenerate = hasPermission(session, 'timetable_generate')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void getDashboardSummary()
      .then(setSummary)
      .catch((reason: unknown) => setError(reason instanceof ApiError ? reason.message : 'The dashboard could not be loaded.'))
  }, [])

  useEffect(() => {
    setPageHeader(summary ? <DashboardHeader canGenerate={canGenerate} /> : 'Dashboard')
  }, [canGenerate, setPageHeader, summary])

  if (error) return (<><FailureNotice message={error} /><p className="text-sm text-gray-500">The dashboard could not be loaded.</p></>)
  if (!summary) return <p className="text-sm text-gray-500">Loading dashboard…</p>
  return <DashboardPage summary={summary} />
}

function DashboardPage({ summary }: { summary: DashboardSummary }) {
  const [sessionType, setSessionType] = useState('')
  const maxLoad = Math.max(1, ...weekDays.map((day) => summary.weekly_load[day] || 0))

  const rows = useMemo(() => summary.today_classes.filter((row) => !sessionType || row.session_type === sessionType), [sessionType, summary.today_classes])

  const attendance = summary.attendance
  const mix = [
    { label: 'Present', value: attendance.present, bar: 'bg-emerald-600' },
    { label: 'Late', value: attendance.late, bar: 'bg-amber-500' },
    { label: 'Absent', value: attendance.absent, bar: 'bg-rose-500' },
    { label: 'Excused', value: attendance.excused, bar: 'bg-sky-500' },
    { label: 'Not marked', value: attendance.not_marked, bar: 'bg-gray-400' },
  ]
  const mixTotal = mix.reduce((sum, item) => sum + item.value, 0)
  const hasTrend = attendance.trend.some((item) => item.percentage !== null)
  const trendMax = Math.max(1, ...attendance.trend.map((item) => item.percentage ?? 0))
  const departmentMax = Math.max(1, ...summary.departments.map((item) => item.students))
  const workloadMax = Math.max(1, ...summary.workload.map((item) => item.classes))

  return (
    <div className={pageStack}>
      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Directory</h3>
      <div className={`${pageGrid} sm:grid-cols-2 lg:grid-cols-4`}>
        <StatCard to="/admin/faculty" label="Faculty" value={summary.total_faculty} note="Active members" />
        <StatCard to="/admin/courses" label="Courses" value={summary.total_courses} note={`${summary.total_departments} departments`} />
        <StatCard to="/admin/rooms" label="Rooms" value={summary.total_rooms} note={`${summary.classroom_count} classrooms · ${summary.laboratory_count} labs`} />
        <StatCard to="/admin/students" label="Students" value={summary.total_students} note={`${summary.total_batches} batches`} />
      </div>

      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Last 30 days</h3>
      <div className={`${pageGrid} sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8`}>
        <StatCard to="/admin/attendance" label="Attendance" value={percentText(attendance.percentage)} note={`${attendance.students} students · ${attendance.lectures} lectures`} />
        <StatCard to="/admin/attendance" label="Present" value={attendance.present} note={`${attendance.countable} countable`} />
        <StatCard to="/admin/attendance" label="Absent" value={attendance.absent} note={`${attendance.late} late · ${attendance.excused} excused`} />
        <StatCard to="/admin/attendance" label={`Below ${attendance.threshold}%`} value={attendance.defaulters} note="Overall, held lectures" />
        <StatCard to="/admin/attendance" label="Not marked" value={attendance.unmarked_lectures} note="Lectures still open" />
        <StatCard to="/admin/shifts/requests" label="Shift requests" value={summary.pending_shifts} note="Waiting for review" />
        <StatCard to="/admin/proxy" label="Proxy" value={summary.unassigned_proxy} note={`${summary.pending_proxy} pending approval`} />
        <StatCard to="/admin/invitations" label="Invitations" value={summary.pending_invitations} note="Still open" />
      </div>

      <div className={`${pageGrid} items-start lg:grid-cols-3`}>
        <div className={`${pageStack} lg:col-span-2`}>
          <Panel title="Weekly class load" note="Scheduled classes by day">
            <div className="flex items-end gap-2">
              {weekDays.map((day) => {
                const count = summary.weekly_load[day] || 0
                return (
                  <div key={day} className="flex flex-1 flex-col items-center justify-end gap-1">
                    <span className="text-[10px] font-semibold text-gray-600">{count}</span>
                    <div className="flex h-40 w-full items-end rounded-md bg-gray-100">
                      <div className="w-full rounded-md bg-indigo-600" style={{ height: `${Math.max(count ? 8 : 0, (count / maxLoad) * 100)}%` }} />
                    </div>
                    <span className="text-[10px] text-gray-500">{day.slice(0, 3)}</span>
                  </div>
                )
              })}
            </div>
          </Panel>
          <Panel title="Attendance mix" note="Marks in the last 30 days">
            <div className="flex h-3 overflow-hidden rounded-full bg-gray-100">
              {mix.filter((item) => item.value > 0).map((item) => (
                <div key={item.label} className={item.bar} style={{ width: `${(item.value / mixTotal) * 100}%` }} title={`${item.label} ${item.value}`} />
              ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-5">
              {mix.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-2 text-xs">
                  <span className="flex min-w-0 items-center gap-1.5 text-gray-600"><span className={`h-2 w-2 shrink-0 rounded-full ${item.bar}`} />{item.label}</span>
                  <span className="font-semibold text-gray-800">{item.value}</span>
                </div>
              ))}
            </div>
            {hasTrend ? (
              <div className="mt-4 flex h-28 items-end gap-1 border-t border-gray-100 pt-3">
                {attendance.trend.map((item) => (
                  <div key={item.date} className="flex flex-1 flex-col items-center justify-end gap-1" title={`${item.date} ${percentText(item.percentage)}`}>
                    <div className="flex h-16 w-full items-end rounded-sm bg-gray-100">
                      <div className="w-full rounded-sm bg-indigo-600" style={{ height: `${item.percentage === null ? 0 : Math.max(6, (item.percentage / trendMax) * 100)}%` }} />
                    </div>
                    <span className="text-[9px] text-gray-400">{item.date.slice(8)}</span>
                  </div>
                ))}
              </div>
            ) : <p className="mt-3 text-xs text-gray-500">No countable lectures in this period.</p>}
          </Panel>
        </div>
        <div className={pageStack}>
          <Panel title="Session mix">
            <SessionDonut types={summary.session_types} />
          </Panel>
          <div className="rounded-2xl border border-gray-200 bg-white p-4">
            <h4 className="text-sm font-bold text-gray-800">Quick shortcuts</h4>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Shortcut to="/admin/attendance" icon="fa-user-check" label="Attendance" />
              <Shortcut to="/admin/reports" icon="fa-chart-bar" label="Reports" />
              <Shortcut to="/admin/timetable" icon="fa-calendar-alt" label="Timetable" />
              <Shortcut to="/admin/shifts" icon="fa-clock" label="Shifts" />
              <Shortcut to="/admin/proxy" icon="fa-user-clock" label="Proxy log" />
              <Shortcut to="/admin/allocations" icon="fa-tasks" label="Allocations" />
            </div>
          </div>
        </div>
      </div>

      <div className={`${pageGrid} lg:grid-cols-3`}>
        <Panel title="Students by department">
          {summary.departments.length === 0 ? <p className="text-sm text-gray-500">No departments yet.</p> : summary.departments.map((item) => (
            <div key={item.name} className="mb-2">
              <div className="mb-1 flex justify-between text-xs text-gray-600"><span className="truncate">{item.name}</span><span className="font-semibold text-gray-800">{item.students}</span></div>
              <div className="h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-indigo-600" style={{ width: `${(item.students / departmentMax) * 100}%` }} /></div>
            </div>
          ))}
        </Panel>
        <Panel title="Busiest faculty" note="Weekly classes">
          {summary.workload.length === 0 ? <p className="text-sm text-gray-500">No teaching load yet.</p> : summary.workload.map((item) => (
            <div key={item.name} className="mb-2">
              <div className="mb-1 flex justify-between text-xs text-gray-600"><span className="truncate">{item.name}</span><span>{item.classes} · {item.hours}h</span></div>
              <div className="h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-gray-700" style={{ width: `${(item.classes / workloadMax) * 100}%` }} /></div>
            </div>
          ))}
        </Panel>
        <Panel title="Upcoming holidays">
          {summary.holidays.length === 0 ? <p className="text-sm text-gray-500">No holidays ahead.</p> : (
            <ul className="flex flex-col gap-2">
              {summary.holidays.map((item) => (
                <li key={`${item.date}-${item.name}`} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-gray-800">{item.name}</span>
                  <span className="shrink-0 text-xs text-gray-500">{item.date}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <ScheduleTable rows={rows} total={summary.today_classes.length} day={summary.today_day} sessionType={sessionType} onType={setSessionType} />
    </div>
  )
}

function percentText(value: number | null) {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${Math.min(Math.max(value, 0), 100).toFixed(2)}%`
}

function StatCard({ to, label, value, note }: { to: string; label: string; value: number | string; note: string }) {
  return (
    <Link to={to} className="rounded-2xl border border-gray-200 bg-white p-4 hover:border-gray-300">
      <p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">{label}</p>
      <p className="mt-1 text-xl font-bold text-gray-800">{value}</p>
      <p className="mt-1 text-xs text-gray-500">{note}</p>
    </Link>
  )
}

function Panel({ title, note, className = '', children }: { title: string; note?: string; className?: string; children: ReactNode }) {
  return (
    <section className={`rounded-2xl border border-gray-200 bg-white p-4 ${className}`}>
      <h4 className="text-sm font-bold text-gray-800">{title}</h4>
      {note ? <p className="mb-3 text-xs text-gray-500">{note}</p> : <div className="mb-3" />}
      {children}
    </section>
  )
}

function sessionColor(type: string) {
  if (type === 'Theory') return '#3b82f6'
  if (type === 'Practical') return '#a855f7'
  return '#22c55e'
}

function SessionDonut({ types }: { types: Record<string, number> }) {
  const entries = Object.entries(types)
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  let cursor = 0
  const stops = entries
    .map(([type, count]) => {
      const start = (cursor / (total || 1)) * 100
      cursor += count
      const end = (cursor / (total || 1)) * 100
      return `${sessionColor(type)} ${start}% ${end}%`
    })
    .join(', ')

  return (
    <div>
      <div className="relative mx-auto h-40 w-40">
        <div
          className="h-full w-full rounded-full"
          style={{ background: total ? `conic-gradient(${stops})` : '#e5e7eb' }}
        />
        <div className="absolute inset-6 rounded-full bg-white" />
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-2">
        {entries.length === 0 ? <p className="text-sm text-gray-500">No sessions scheduled.</p> : null}
        {entries.map(([type]) => (
          <div key={type} className="flex items-center text-xs">
            <span className="mr-2 h-2 w-2 rounded-full" style={{ backgroundColor: sessionColor(type) }} />
            <span className="font-medium text-gray-600">{type}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Shortcut({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300 hover:bg-white">
      <i className={`fas ${icon} w-4 text-center text-gray-500`} />
      <span className="min-w-0 truncate">{label}</span>
    </Link>
  )
}

const scheduleColumns: TableColumnSpec[] = [
  { key: 'time', label: 'Time' },
  { key: 'subject', label: 'Subject & class' },
  { key: 'faculty_name', label: 'Faculty' },
  { key: 'room_number', label: 'Location' },
  { key: 'session_type', label: 'Type', className: 'text-right' },
]

function scheduleValue(row: TodayClass, key: string) {
  if (key === 'time') return `${row.start_time} ${row.end_time}`
  if (key === 'subject') return `${row.subject_name} ${row.class_name} ${row.division_name}`
  if (key === 'room_number') return row.room_number || 'TBA'
  return row[key as keyof TodayClass]
}

function ScheduleTable({
  rows,
  total,
  day,
  sessionType,
  onType,
}: {
  rows: TodayClass[]
  total: number
  day: string
  sessionType: string
  onType: (value: string) => void
}) {
  const table = useDataTable(rows, scheduleColumns, scheduleValue)
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="border-b border-gray-100 bg-gray-50/50 p-6">
        <div className="mb-4 flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h4 className="text-xl font-bold text-gray-900">Today's Schedule</h4>
            <p className="text-sm text-gray-500">Comprehensive view of all classes for {day}</p>
          </div>
          <span className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">{total} Classes</span>
        </div>
        <div className="flex flex-col gap-3 md:flex-row">
          <select
            value={sessionType}
            onChange={(event) => onType(event.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 focus:ring-2 focus:ring-indigo-500 md:w-48"
          >
            <option value="">All Types</option>
            <option value="Theory">Theory</option>
            <option value="Practical">Practical</option>
          </select>
        </div>
      </div>
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
      <div className="max-h-[600px] overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-gray-50 shadow-sm">
            <DataTableHead columns={scheduleColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white text-sm">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center">
                  <div className="flex flex-col items-center justify-center">
                    <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-gray-50">
                      <i className="fas fa-mug-hot text-2xl text-gray-300" />
                    </div>
                    <p className="font-medium text-gray-900">No classes scheduled</p>
                    <p className="mt-1 text-sm text-gray-500">Enjoy your day off!</p>
                  </div>
                </td>
              </tr>
            ) : table.rows.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">No classes match these filters.</td></tr>
            ) : (
              table.rows.map((row) => (
                <tr key={`${row.start_time}-${row.subject_name}-${row.faculty_name}`} className="transition-colors hover:bg-indigo-50/30">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center font-semibold text-gray-900">
                      <div className="mr-2.5 h-1.5 w-1.5 rounded-full bg-indigo-500" />
                      {row.start_time}
                    </div>
                    <div className="mt-0.5 pl-4 text-xs text-gray-400">To {row.end_time}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="font-bold text-gray-900">{row.subject_name}</div>
                    <div className="mt-0.5 text-xs text-gray-500">
                      {row.class_name} {row.division_name ? <span className="text-gray-300">|</span> : null} {row.division_name}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center">
                      <div className="mr-3 flex h-8 w-8 items-center justify-center rounded-full border border-gray-200 bg-gradient-to-br from-gray-100 to-gray-200 text-xs font-bold text-gray-600">
                        {(row.faculty_name || '?').slice(0, 1).toUpperCase()}
                      </div>
                      <p className="text-sm font-medium text-gray-900">{row.faculty_name}</p>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center text-gray-600">
                      <i className="fas fa-map-marker-alt mr-2 text-gray-400" />
                      {row.room_number || 'TBA'}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold ${typeBadge(row.session_type)}`}>{row.session_type}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
    </div>
  )
}
