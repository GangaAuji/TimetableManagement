import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
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

  if (error) return <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>
  if (!summary) return <p className="text-sm text-gray-500">Loading dashboard…</p>
  return <DashboardPage summary={summary} />
}

function DashboardPage({ summary }: { summary: DashboardSummary }) {
  const [sessionType, setSessionType] = useState('')
  const maxLoad = Math.max(1, ...weekDays.map((day) => summary.weekly_load[day] || 0))

  const rows = useMemo(() => summary.today_classes.filter((row) => !sessionType || row.session_type === sessionType), [sessionType, summary.today_classes])

  return (
    <div className={pageStack}>
      <div className={`${pageGrid} sm:grid-cols-2 lg:grid-cols-4`}>
        <StatCard icon="fa-chalkboard-teacher" iconClass="bg-blue-50 text-blue-600" wash="from-blue-50" value={summary.total_faculty} label="Total Faculty Members" badge="Active" />
        <StatCard icon="fa-book-open" iconClass="bg-purple-50 text-purple-600" wash="from-purple-50" value={summary.total_courses} label={`Active Courses in ${summary.total_departments} Depts`} />
        <StatCard icon="fa-door-open" iconClass="bg-orange-50 text-orange-600" wash="from-orange-50" value={summary.total_rooms} label={`${summary.classroom_count} Classrooms, ${summary.laboratory_count} Labs`} />
        <StatCard icon="fa-user-graduate" iconClass="bg-teal-50 text-teal-600" wash="from-teal-50" value={summary.total_students} label={`Students across ${summary.total_batches} Batches`} />
      </div>

      <div className={`${pageGrid} lg:grid-cols-3`}>
        <div className="rounded-3xl border border-gray-100 bg-white p-6 shadow-sm lg:col-span-2">
          <h4 className="text-lg font-bold text-gray-900">Weekly Class Load</h4>
          <p className="text-xs text-gray-500">Distribution of classes throughout the week</p>
          <div className="mt-6 flex h-64 items-end gap-1 overflow-hidden sm:gap-3">
            {weekDays.map((day) => {
              const count = summary.weekly_load[day] || 0
              return (
                <div key={day} className="flex flex-1 flex-col items-center justify-end gap-2">
                  <span className="text-[10px] font-semibold text-gray-700 sm:text-xs">{count}</span>
                  <div className="flex h-48 w-full items-end rounded-xl bg-indigo-50">
                    <div className="w-full rounded-xl bg-indigo-500" style={{ height: `${Math.max(8, (count / maxLoad) * 100)}%` }} />
                  </div>
                  <span className="text-[10px] text-gray-500 sm:text-xs">{day.slice(0, 3)}</span>
                </div>
              )
            })}
          </div>
        </div>

        <div className={pageStack}>
          <div className="rounded-3xl border border-gray-100 bg-white p-6 shadow-sm">
            <h4 className="mb-4 text-lg font-bold text-gray-900">Sessions</h4>
            <SessionDonut types={summary.session_types} />
          </div>

          <div className="rounded-3xl bg-gradient-to-br from-indigo-600 to-purple-700 p-6 text-white shadow-lg">
            <h4 className="mb-4 font-bold text-white">Quick Shortcuts</h4>
            <div className="grid grid-cols-2 gap-3">
              <Shortcut href="/admin/allocations" icon="fa-project-diagram" label="Allocations" />
              <Shortcut href="/admin/rooms" icon="fa-door-open" label="Rooms" />
              <Shortcut href="/admin/subjects" icon="fa-book" label="Subjects" />
            </div>
          </div>
        </div>
      </div>

      <ScheduleTable rows={rows} total={summary.today_classes.length} day={summary.today_day} sessionType={sessionType} onType={setSessionType} />
    </div>
  )
}

function StatCard({ icon, iconClass, wash, value, label, badge }: { icon: string; iconClass: string; wash: string; value: number; label: string; badge?: string }) {
  return (
    <div className="group relative overflow-hidden rounded-3xl border border-gray-100 bg-white p-4 shadow-sm transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-lg sm:p-6">
      <div className={`absolute top-0 right-0 h-full w-1/3 bg-gradient-to-l ${wash} to-transparent opacity-0 transition-opacity group-hover:opacity-100`} />
      <div className="relative z-10">
        <div className="mb-4 flex items-start justify-between">
          <div className={`rounded-2xl p-3 ${iconClass}`}>
            <i className={`fas ${icon} text-xl`} />
          </div>
          {badge ? <span className="rounded-full bg-green-50 px-2 py-1 text-xs font-bold text-green-600">{badge}</span> : null}
        </div>
        <h3 className="text-2xl font-bold text-gray-900 sm:text-3xl">{value}</h3>
        <p className="mt-1 text-sm font-medium text-gray-500">{label}</p>
      </div>
    </div>
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

function Shortcut({ href, icon, label }: { href: string; icon: string; label: string }) {
  return (
    <a href={href} className="flex items-center rounded-xl bg-white/10 p-3 backdrop-blur-sm transition-colors hover:bg-white/20">
      <i className={`fas ${icon} mr-3 text-indigo-200`} />
      <span className="min-w-0 truncate text-sm font-medium">{label}</span>
    </a>
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
    <div className="flex flex-col overflow-hidden rounded-3xl border border-gray-100 bg-white shadow-sm">
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
