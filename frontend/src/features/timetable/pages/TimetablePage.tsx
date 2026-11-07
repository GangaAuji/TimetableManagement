import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { safeCount, safeText } from '../../../shared/security/sanitize'

const weekDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const sessionColumns: TableColumnSpec[] = [
  { key: 'slot', label: 'Time slot' },
  { key: 'subject', label: 'Details' },
  { key: 'faculty', label: 'Faculty' },
  { key: 'room', label: 'Location' },
]

function sessionValue(row: Session, key: string) {
  if (key === 'slot') return `${row.day} ${row.start_time} ${row.end_time}`
  if (key === 'faculty') return row.faculty || 'Unassigned'
  if (key === 'room') return row.room || 'No room'
  return row[key as keyof Session]
}
const fieldClass = 'w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20'
const labelClass = 'mb-1.5 ml-1 block text-[10px] font-bold tracking-wide text-gray-500 uppercase'

type Option = { id: number; name: string }
type Session = {
  day: string
  start_time: string
  end_time: string
  subject: string
  faculty: string
  room: string
  session_type: string
  is_proxy: boolean
}
type OpenSlot = { day: string; start_time: string; end_time: string; reason: string }
type ProxySuggestion = { day: string; time: string; subject: string; primary_faculty: string; replacement_faculty: string }
type Candidate = { candidate_index: number; quality_score: number; assigned_count: number; unassigned_count: number }
type ScoreBreakdown = { clash_risk: number; faculty_fatigue: number; room_overuse: number; student_load_imbalance: number }
type Generation = {
  status: string
  message: string
  assigned_count: number
  unassigned_count: number
  assigned: Session[]
  unassigned: OpenSlot[]
  proxy_suggestions: ProxySuggestion[]
  warnings: string[]
  top_candidates: Candidate[]
  quality_score?: number
  score_breakdown?: ScoreBreakdown
}
type TimetableJob = {
  id: number
  status: string
  progress: number
  total: number
  done: number
  assigned_count: number
  unassigned_count: number
  failed_count: number
  message: string
  attached: boolean
  result: Generation | null
  failures: { label: string; message: string }[]
}
type TimetableOptions = {
  courses?: { id?: unknown; name?: unknown }[]
  classes?: { id?: unknown; name?: unknown }[]
  divisions?: { id?: unknown; name?: unknown }[]
  sessions?: Record<string, unknown>[]
  can_generate?: boolean
}

function options(value: { id?: unknown; name?: unknown }[] | undefined): Option[] {
  return (value || []).map((item) => ({ id: safeCount(item.id), name: safeText(item.name, 100) })).filter((item) => item.id > 0)
}

function sessions(rows: Record<string, unknown>[] | undefined): Session[] {
  return (rows || []).map((row) => ({
    day: safeText(row.day, 12),
    start_time: safeText(row.start_time, 8),
    end_time: safeText(row.end_time, 8),
    subject: safeText(row.subject, 100),
    faculty: safeText(row.faculty, 100),
    room: safeText(row.room, 20),
    session_type: safeText(row.session_type, 20),
    is_proxy: row.is_proxy === true,
  }))
}

const generationJobKey = 'timetable-generation-job'

function generationFrom(data: Generation): Generation {
  return {
    status: safeText(data.status, 20) || 'error',
    message: safeText(data.message, 300),
    assigned_count: safeCount(data.assigned_count),
    unassigned_count: safeCount(data.unassigned_count),
    assigned: sessions(data.assigned as unknown as Record<string, unknown>[]),
    unassigned: (data.unassigned || []).map((item) => ({
      day: safeText(item.day, 12),
      start_time: safeText(item.start_time, 8),
      end_time: safeText(item.end_time, 8),
      reason: safeText(item.reason, 160),
    })),
    proxy_suggestions: (data.proxy_suggestions || []).map((item) => ({
      day: safeText(item.day, 12),
      time: safeText(item.time, 24),
      subject: safeText(item.subject, 100),
      primary_faculty: safeText(item.primary_faculty, 100),
      replacement_faculty: safeText(item.replacement_faculty, 100),
    })),
    warnings: (data.warnings || []).map((item) => safeText(item, 200)).filter(Boolean),
    top_candidates: (data.top_candidates || []).map((item) => ({
      candidate_index: safeCount(item.candidate_index),
      quality_score: safeCount(item.quality_score),
      assigned_count: safeCount(item.assigned_count),
      unassigned_count: safeCount(item.unassigned_count),
    })),
    quality_score: typeof data.quality_score === 'number' ? data.quality_score : undefined,
    score_breakdown: data.score_breakdown,
  }
}

function jobFrom(data: TimetableJob): TimetableJob {
  return {
    id: safeCount(data.id),
    status: safeText(data.status, 20),
    progress: Math.min(safeCount(data.progress), 100),
    total: safeCount(data.total),
    done: safeCount(data.done),
    assigned_count: safeCount(data.assigned_count),
    unassigned_count: safeCount(data.unassigned_count),
    failed_count: safeCount(data.failed_count),
    message: safeText(data.message, 300),
    attached: data.attached === true,
    result: data.result ? generationFrom(data.result) : null,
    failures: (data.failures || []).map((item) => ({ label: safeText(item.label, 180), message: safeText(item.message, 160) })).filter((item) => item.label || item.message),
  }
}

function minutes(value: string) {
  const [hours, mins] = value.split(':')
  return (Number(hours) || 0) * 60 + (Number(mins) || 0)
}

function scheduleGrid(rows: Session[]) {
  const pairs = new Map<string, { start: string; end: string }>()
  rows.forEach((row) => {
    if (row.start_time && row.end_time) pairs.set(`${row.start_time}|${row.end_time}`, { start: row.start_time, end: row.end_time })
  })
  const columns = [...pairs.values()].sort((left, right) => minutes(left.start) - minutes(right.start) || minutes(left.end) - minutes(right.end))
  const days = weekDays.map((day) => ({
    day,
    cells: columns.map((column) => rows.find((row) => row.day === day && row.start_time === column.start && row.end_time === column.end) || null),
  }))
  return { columns, days }
}

function cellLabel(session: Session) {
  return `${session.subject}${session.faculty ? ` (${session.faculty})` : ''}${session.room ? ` — Room ${session.room}` : ''}`
}

function SelectField({ label, value, onChange, placeholder, items }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; items: Option[] }) {
  return (
    <label className="block">
      <span className={labelClass}>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={fieldClass}>
        <option value="">{placeholder}</option>
        {items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
  )
}

function Panel({ icon, iconClass, title, children }: { icon: string; iconClass: string; title: string; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex items-center border-b border-gray-100 bg-gray-50/70 px-5 py-4">
        <span className={`mr-3 flex h-8 w-8 items-center justify-center rounded-lg text-sm ${iconClass}`}>
          <i className={`fas ${icon}`} />
        </span>
        <h3 className="text-sm font-bold text-gray-800">{title}</h3>
      </header>
      <div className="p-5">{children}</div>
    </section>
  )
}

export function TimetablePage() {
  const setPageHeader = useSetPageHeader()
  const [courses, setCourses] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [divisions, setDivisions] = useState<Option[]>([])
  const [rows, setRows] = useState<Session[]>([])
  const [course, setCourse] = useState('')
  const [classId, setClassId] = useState('')
  const [division, setDivision] = useState('')
  const [canGenerate, setCanGenerate] = useState(false)
  const [view, setView] = useState<'list' | 'grid'>('list')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [exporting, setExporting] = useState(false)
  const ready = Boolean(course && classId && division)
  const grid = useMemo(() => scheduleGrid(rows), [rows])
  const table = useDataTable(rows, sessionColumns, sessionValue)

  useEffect(() => {
    setPageHeader('View Timetable')
  }, [setPageHeader])

  useEffect(() => {
    const params = new URLSearchParams()
    if (course) params.set('course', course)
    if (classId) params.set('class', classId)
    if (division) params.set('division', division)
    void apiRequest<TimetableOptions>(`/api/timetable?${params.toString()}`)
      .then((data) => {
        setCourses(options(data.courses))
        setClasses(options(data.classes))
        setDivisions(options(data.divisions))
        setRows(sessions(data.sessions))
        setCanGenerate(data.can_generate === true)
        setError('')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [classId, course, division])

  async function queueTimetable() {
    setError('')
    setNotice('')
    setExporting(true)
    try {
      await postJson('/api/exports', { kind: 'timetable', course: Number(course), class: Number(classId), division: Number(division) })
      setNotice('Export queued.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 items-start gap-2 overflow-auto xl:grid-cols-4">
      <Panel icon="fa-filter" iconClass="bg-indigo-100 text-indigo-600" title="Target group">
        <div className="space-y-4">
          <SelectField label="Course" value={course} placeholder="Select course" items={courses} onChange={(value) => { setCourse(value); setClassId(''); setDivision('') }} />
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Class" value={classId} placeholder="Select" items={classes} onChange={(value) => { setClassId(value); setDivision('') }} />
            <SelectField label="Division" value={division} placeholder="Select" items={divisions} onChange={setDivision} />
          </div>
        </div>
      </Panel>

      <section className="flex min-h-[520px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm xl:col-span-3 xl:h-full">
        <header className="flex shrink-0 flex-col justify-between gap-3 border-b border-gray-100 px-5 py-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2">
            <span className="h-6 w-2 rounded-full bg-indigo-500" />
            <h3 className="text-base font-bold text-gray-800">Weekly schedule</h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {ready && rows.length > 0 && (
              <button
                type="button"
                disabled={exporting}
                onClick={() => void queueTimetable()}
                className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-50"
              >
                <i className="fas fa-file-csv mr-2 text-emerald-600" /> Export CSV
              </button>
            )}
            {canGenerate && <a href="/admin/timetable/generate" className="rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-bold text-white">Generate</a>}
            <div className="inline-flex rounded-lg bg-gray-100 p-1">
              <button type="button" onClick={() => setView('list')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${view === 'list' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500'}`}>
                <i className="fas fa-list mr-2" /> List
              </button>
              <button type="button" onClick={() => setView('grid')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${view === 'grid' ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500'}`}>
                <i className="fas fa-th mr-2" /> Grid
              </button>
            </div>
          </div>
        </header>
        {error && <p className="border-b border-red-100 bg-red-50 px-5 py-2 text-xs text-red-700">{error}</p>}
        {notice && <p className="border-b border-emerald-100 bg-emerald-50 px-5 py-2 text-xs text-emerald-700">{notice} <Link to="/admin/reports" className="font-bold underline">Open Reports</Link> to follow the progress and download the file.</p>}
        {!ready && (
          <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gray-50 text-gray-300">
              <i className="fas fa-calendar-week text-2xl" />
            </div>
            <h4 className="font-bold text-gray-800">Ready to view</h4>
            <p className="mt-1 max-w-md text-sm text-gray-500">Select a course, class, and division to see the weekly schedule.</p>
          </div>
        )}
        {ready && view === 'list' && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
            <div className="flex-1 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                <DataTableHead columns={sessionColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-16 text-center">
                      <h4 className="font-medium text-gray-800">No sessions scheduled yet</h4>
                      <p className="mt-1 text-sm text-gray-500">Generate a timetable for this class, then come back to this view.</p>
                    </td>
                  </tr>
                )}
                {rows.length > 0 && table.rows.length === 0 && (
                  <tr><td colSpan={4} className="px-6 py-10 text-center text-sm text-gray-500">No sessions match these filters.</td></tr>
                )}
                {table.rows.map((row, index) => (
                  <tr key={`${row.day}-${row.start_time}-${index}`} className="hover:bg-indigo-50/30">
                    <td className="px-6 py-4">
                      <span className="mb-1 inline-flex rounded-md bg-gray-100 px-2.5 py-0.5 text-xs font-bold text-gray-700">{row.day.slice(0, 3)}</span>
                      <p className="font-mono text-sm text-gray-600">{row.start_time} - {row.end_time}</p>
                    </td>
                    <td className="px-6 py-4 font-bold text-gray-800">{row.subject}</td>
                    <td className="px-6 py-4 text-gray-600">
                      <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-[10px] text-gray-500"><i className="fas fa-user" /></span>
                      {row.faculty || 'Unassigned'}
                    </td>
                    <td className="px-6 py-4">
                      {row.room
                        ? <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"><i className="fas fa-door-open mr-1.5" />{row.room}</span>
                        : <span className="inline-flex items-center rounded-full border border-red-100 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-600"><i className="fas fa-exclamation-circle mr-1.5" />No room</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        )}
        {ready && view === 'grid' && (
          <div className="flex-1 overflow-auto p-5">
            {grid.columns.length === 0 ? (
              <p className="py-16 text-center text-sm text-gray-500">No sessions are scheduled for this class.</p>
            ) : (
              <table className="w-full min-w-[800px] border-collapse border border-gray-200 text-left">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 w-24 border border-gray-200 bg-gray-50 p-3 text-xs font-bold tracking-wider text-gray-500 uppercase">Day</th>
                    {grid.columns.map((column) => (
                      <th key={`${column.start}-${column.end}`} className="min-w-[140px] border border-gray-200 bg-gray-50 p-3 text-xs font-bold text-gray-600">{column.start} - {column.end}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.days.map((day) => (
                    <tr key={day.day}>
                      <td className="sticky left-0 z-10 border border-gray-200 bg-gray-50 p-3 text-sm font-bold text-gray-700">{day.day}</td>
                      {day.cells.map((cell, index) => (
                        <td key={`${day.day}-${index}`} className="h-24 border border-gray-200 p-2 align-top hover:bg-gray-50">
                          {cell ? (
                            <div className="flex h-full flex-col justify-between rounded-lg bg-gradient-to-br from-indigo-600 to-indigo-700 p-2 text-white shadow-sm">
                              <span className="text-xs leading-tight font-semibold">{cellLabel(cell)}</span>
                              <i className="fas fa-clock mt-1 self-end text-[10px] opacity-75" />
                            </div>
                          ) : <span className="block text-center text-2xl font-light text-gray-200">·</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </div>
  )
}

const scoreMeters: { key: keyof ScoreBreakdown; label: string; color: string }[] = [
  { key: 'clash_risk', label: 'Clash risk', color: 'bg-emerald-500' },
  { key: 'faculty_fatigue', label: 'Faculty fatigue', color: 'bg-teal-500' },
  { key: 'room_overuse', label: 'Room overuse', color: 'bg-blue-500' },
  { key: 'student_load_imbalance', label: 'Student load balance', color: 'bg-indigo-500' },
]

export function GeneratePage() {
  const setPageHeader = useSetPageHeader()
  const [courses, setCourses] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [divisions, setDivisions] = useState<Option[]>([])
  const [courseId, setCourseId] = useState('')
  const [classId, setClassId] = useState('')
  const [divisionId, setDivisionId] = useState('')
  const [weekStart, setWeekStart] = useState(() => new Date().toISOString().slice(0, 10))
  const [dayStart, setDayStart] = useState('09:00')
  const [dayEnd, setDayEnd] = useState('15:00')
  const [lectureMinutes, setLectureMinutes] = useState('45')
  const [breakStart, setBreakStart] = useState('')
  const [breakDuration, setBreakDuration] = useState('0')
  const [workingDays, setWorkingDays] = useState<string[]>(weekDays)
  const [scope, setScope] = useState<'one' | 'course' | 'all'>('one')
  const [result, setResult] = useState<Generation | null>(null)
  const [job, setJob] = useState<TimetableJob | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const pending = job?.status === 'queued' || job?.status === 'running'

  useEffect(() => {
    setPageHeader('Generate Timetable')
    void apiRequest<TimetableOptions>('/api/timetable')
      .then((data) => {
        setCourses(options(data.courses))
        setClasses(options(data.classes))
        setDivisions(options(data.divisions))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  useEffect(() => {
    const stored = sessionStorage.getItem(generationJobKey)
    if (!stored) return
    void apiRequest<TimetableJob>(`/api/timetable/jobs/${stored}`)
      .then((data) => {
        const next = jobFrom(data)
        setJob(next)
        if (next.status === 'completed' && next.result && next.result.status !== 'error') setResult(next.result)
        if (next.status === 'completed' || next.status === 'failed') sessionStorage.removeItem(generationJobKey)
      })
      .catch(() => sessionStorage.removeItem(generationJobKey))
  }, [])

  useEffect(() => {
    if (!pending || !job) return
    const timer = window.setInterval(() => {
      void apiRequest<TimetableJob>(`/api/timetable/jobs/${job.id}`)
        .then((data) => {
          const next = jobFrom(data)
          setJob(next)
          if (next.status === 'completed' || next.status === 'failed') sessionStorage.removeItem(generationJobKey)
          if (next.status === 'failed') setError(next.message || 'The timetable could not be generated.')
          if (next.status === 'completed' && next.result) {
            if (next.result.status === 'error') setError(next.result.message || 'The timetable could not be generated.')
            else setResult(next.result)
          }
        })
        .catch(() => {})
    }, 2000)
    return () => window.clearInterval(timer)
  }, [pending, job])

  function toggleDay(day: string) {
    setWorkingDays((current) => (current.includes(day) ? current.filter((item) => item !== day) : [...current, day]))
  }

  async function generate(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setResult(null)
    const payload: Record<string, unknown> = {
      scope,
      week_start_date: weekStart,
      day_start: dayStart.slice(0, 5),
      day_end: dayEnd.slice(0, 5),
      lecture_minutes: Number(lectureMinutes) || 45,
      break_start: breakStart.slice(0, 5),
      break_duration: Number(breakDuration) || 0,
      working_days: weekDays.filter((day) => workingDays.includes(day)),
    }
    if (scope !== 'all') payload.course_id = Number(courseId)
    if (scope === 'one') {
      payload.class_id = Number(classId)
      payload.division_id = Number(divisionId)
    }
    try {
      const next = jobFrom(await postJson<TimetableJob>('/api/timetable/generate', payload))
      setJob(next)
      sessionStorage.setItem(generationJobKey, String(next.id))
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={generate} className="grid grid-cols-1 items-start gap-2 xl:grid-cols-12">
      <div className="space-y-4 xl:col-span-4">
        <Panel icon="fa-filter" iconClass="bg-indigo-100 text-indigo-600" title="Target group">
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
              {([['one', 'One class'], ['course', 'One course'], ['all', 'All classes']] as const).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={scope === value} onClick={() => setScope(value)} className={`rounded-md border py-2 text-xs font-medium ${scope === value ? 'border-gray-800 bg-gray-800 text-white' : 'border-gray-200 bg-white text-gray-600'}`}>
                  {label}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500">The request returns immediately. Classes then run one after another, so faculty and rooms are not double-booked.</p>
            {scope !== 'all' && <SelectField label="Course" value={courseId} placeholder="Select course" items={courses} onChange={(value) => { setCourseId(value); setClassId(''); setDivisionId('') }} />}
            {scope === 'one' && (
              <div className="grid grid-cols-2 gap-3">
                <SelectField label="Class" value={classId} placeholder="Select" items={classes} onChange={(value) => { setClassId(value); setDivisionId('') }} />
                <SelectField label="Division" value={divisionId} placeholder="Select" items={divisions} onChange={setDivisionId} />
              </div>
            )}
          </div>
        </Panel>
        <Panel icon="fa-sliders-h" iconClass="bg-teal-100 text-teal-600" title="Configuration">
          <div className="space-y-4">
            <label className="block">
              <span className={labelClass}>Week start date</span>
              <input required type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} className={fieldClass} />
            </label>
            <div className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 p-3">
              <span className="text-sm font-medium text-gray-700">Lecture duration</span>
              <span className="flex items-center gap-2">
                <input required type="number" min={15} max={180} step={5} value={lectureMinutes} onChange={(event) => setLectureMinutes(event.target.value)} className="w-20 rounded border border-gray-300 px-2 py-1 text-center text-sm" aria-label="Lecture minutes" />
                <span className="text-xs text-gray-500">min</span>
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className={labelClass}>Start time</span>
                <input required type="time" value={dayStart} onChange={(event) => setDayStart(event.target.value)} className={fieldClass} />
              </label>
              <label>
                <span className={labelClass}>End time</span>
                <input required type="time" value={dayEnd} onChange={(event) => setDayEnd(event.target.value)} className={fieldClass} />
              </label>
            </div>
            <div className="rounded-lg border border-amber-100 bg-amber-50 p-3">
              <p className="mb-2 text-[10px] font-bold tracking-wide text-amber-700 uppercase"><i className="fas fa-coffee mr-1.5" /> Break settings</p>
              <div className="grid grid-cols-2 gap-3">
                <label>
                  <input type="time" value={breakStart} onChange={(event) => setBreakStart(event.target.value)} className="w-full rounded border border-amber-200 bg-white px-2 py-1.5 text-center text-sm" aria-label="Break start" />
                  <span className="mt-1 block text-center text-[10px] text-amber-700/70">Start time</span>
                </label>
                <label>
                  <input type="number" min={0} step={5} value={breakDuration} onChange={(event) => setBreakDuration(event.target.value)} className="w-full rounded border border-amber-200 bg-white px-2 py-1.5 text-center text-sm" aria-label="Break minutes" />
                  <span className="mt-1 block text-center text-[10px] text-amber-700/70">Minutes</span>
                </label>
              </div>
            </div>
            <div>
              <span className={labelClass}>Working days</span>
              <div className="grid grid-cols-3 gap-2">
                {weekDays.map((day) => {
                  const checked = workingDays.includes(day)
                  return (
                    <button key={day} type="button" aria-pressed={checked} onClick={() => toggleDay(day)} className={`rounded-md border py-2 text-xs font-medium ${checked ? 'border-gray-800 bg-gray-800 text-white' : 'border-gray-200 bg-white text-gray-600'}`}>
                      {day.slice(0, 3)}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-4 xl:col-span-8">
        {error && <p className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-xs text-red-700">{error}</p>}
        <div className="flex flex-col items-center justify-end gap-3 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm sm:flex-row">
          <a href="/admin/timetable" className="w-full rounded-xl border border-gray-200 px-5 py-2.5 text-center text-sm font-semibold text-gray-700 sm:w-auto">
            <i className="fas fa-calendar-week mr-2 text-gray-500" /> View
          </a>
          <button type="submit" disabled={saving || pending || workingDays.length === 0 || (scope !== 'all' && !courseId) || (scope === 'one' && (!classId || !divisionId))} className="w-full rounded-xl bg-gray-900 px-8 py-2.5 text-sm font-bold text-white disabled:opacity-50 sm:w-auto">
            <i className="fas fa-magic mr-2" /> {saving ? 'Queuing...' : pending ? 'Generating...' : 'Generate timetable'}
          </button>
        </div>

        {job && (pending || (job.status === 'completed' && job.total > 1)) && (
          <section className="rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-gray-800">{job.attached && pending ? 'A generation is already running' : 'Generation progress'}</h3>
                <p className="text-xs text-gray-500">{job.message || 'Waiting for the next class.'}</p>
              </div>
              <p className="text-sm font-bold text-indigo-700">{job.done} / {job.total}</p>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${job.status === 'queued' ? 8 : Math.max(job.progress, 8)}%` }} />
            </div>
            {job.status === 'completed' && job.total > 1 && (
              <p className="mt-3 text-xs text-gray-600">
                {job.assigned_count} sessions scheduled. {job.failed_count} classes need attention. <Link to="/admin/timetable" className="font-bold text-indigo-600">View a class</Link>
              </p>
            )}
            {job.failures.length > 0 && (
              <ul className="mt-3 max-h-40 space-y-1 overflow-auto">
                {job.failures.map((item) => (
                  <li key={`${item.label}-${item.message}`} className="text-xs text-red-600">{item.label}: {item.message}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        {result && (
          <div className="space-y-4">
            <section className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-6 shadow-sm">
              <div className="mb-4 flex items-center gap-4">
                <div className="rounded-full bg-emerald-100 p-3 text-emerald-600"><i className="fas fa-clipboard-check text-xl" /></div>
                <div>
                  <h3 className="text-lg font-bold text-gray-800">Generation complete</h3>
                  <p className="text-sm text-gray-600">{result.message}</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Stat value={result.assigned_count} label="Allocated" valueClass="text-emerald-600" borderClass="border-emerald-100" />
                <Stat value={result.unassigned_count} label="Conflicts" valueClass="text-red-500" borderClass="border-red-100" />
                <Stat value={result.proxy_suggestions.length} label="Proxies" valueClass="text-blue-500" borderClass="border-blue-100" />
              </div>
              {typeof result.quality_score === 'number' && result.score_breakdown && (
                <div className="mt-5 rounded-xl border border-emerald-100 bg-white p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-bold text-gray-800">Quality score</h4>
                      <p className="text-xs text-gray-500">Clash risk, fatigue, room pressure, and load balance.</p>
                    </div>
                    <p className="text-right"><span className="text-3xl font-extrabold text-emerald-600">{result.quality_score}</span><span className="text-sm text-gray-500"> / 100</span></p>
                  </div>
                  <div className="space-y-2.5">
                    {scoreMeters.map((meter) => {
                      const healthy = Math.round((1 - (result.score_breakdown?.[meter.key] || 0)) * 100)
                      return (
                        <div key={meter.key}>
                          <div className="mb-1 flex justify-between text-xs"><span className="font-semibold text-gray-600">{meter.label}</span><span className="text-gray-500">{healthy}%</span></div>
                          <div className="h-2 overflow-hidden rounded bg-gray-100"><div className={`h-2 ${meter.color}`} style={{ width: `${healthy}%` }} /></div>
                        </div>
                      )
                    })}
                  </div>
                  {result.warnings.length > 0 && (
                    <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <h5 className="mb-1.5 text-[10px] font-bold tracking-wide text-amber-700 uppercase">Top warnings</h5>
                      <ul className="space-y-1">
                        {result.warnings.map((warning) => <li key={warning} className="text-xs text-amber-700"><i className="fas fa-exclamation-triangle mr-1" />{warning}</li>)}
                      </ul>
                    </div>
                  )}
                  {result.top_candidates.length > 0 && (
                    <div className="mt-4">
                      <h5 className="mb-2 text-[10px] font-bold tracking-wide text-gray-600 uppercase">Top candidates</h5>
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                        {result.top_candidates.map((candidate) => (
                          <div key={candidate.candidate_index} className="rounded-lg border border-gray-200 bg-gray-50 p-2.5">
                            <div className="mb-1 flex justify-between text-xs text-gray-600"><span className="font-semibold">#{candidate.candidate_index}</span><span>Score {candidate.quality_score}</span></div>
                            <p className="text-[11px] text-gray-500">Assigned {candidate.assigned_count}, conflicts {candidate.unassigned_count}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <section className="flex h-[420px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                <header className="border-b border-gray-100 bg-gray-50/80 px-5 py-3 text-sm font-semibold text-gray-700">Scheduled sessions</header>
                <ul className="flex-1 space-y-3 overflow-auto p-4">
                  {result.assigned.slice(0, 50).map((session, index) => (
                    <li key={`${session.day}-${session.start_time}-${index}`} className="flex">
                      <div className="w-20 shrink-0 pt-1">
                        <p className="text-xs font-bold text-gray-800">{session.day.slice(0, 3)}</p>
                        <p className="text-[10px] text-gray-500">{session.start_time}</p>
                      </div>
                      <div className="ml-2 flex-1 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
                        <div className="flex items-start justify-between gap-2">
                          <h5 className="text-sm font-bold text-gray-800">{session.subject}</h5>
                          {session.is_proxy && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">PROXY</span>}
                        </div>
                        <p className="mt-1 text-xs text-gray-600"><i className="fas fa-user-circle mr-1.5 text-gray-400" />{session.faculty || 'Unassigned'}</p>
                        {session.room && <span className="mt-1 inline-block rounded border border-gray-100 bg-gray-50 px-1.5 text-[10px] text-gray-500">Room {session.room}</span>}
                      </div>
                    </li>
                  ))}
                  {result.assigned.length === 0 && <li className="py-8 text-center text-sm text-gray-400">No sessions were scheduled.</li>}
                </ul>
              </section>
              <div className="space-y-4">
                <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                  <header className="flex justify-between border-b border-red-50 bg-red-50/50 px-5 py-3 text-sm font-semibold text-red-700">
                    <span>Unassigned slots</span>
                    {result.unassigned.length === 0 && <span className="text-xs text-emerald-600"><i className="fas fa-check mr-1" />All clear</span>}
                  </header>
                  {result.unassigned.length === 0 ? (
                    <p className="px-5 py-6 text-center text-sm text-gray-400">No unassigned slots.</p>
                  ) : (
                    <ul className="max-h-[220px] divide-y divide-gray-100 overflow-auto">
                      {result.unassigned.map((slot, index) => (
                        <li key={`${slot.day}-${slot.start_time}-${index}`} className="px-4 py-3">
                          <p className="text-xs font-bold text-gray-700">{slot.day} {slot.start_time}{slot.end_time ? ` - ${slot.end_time}` : ''}</p>
                          <p className="mt-1 text-xs text-red-500"><i className="fas fa-exclamation-circle mr-1" />{slot.reason || 'Could not be assigned'}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                {result.proxy_suggestions.length > 0 && (
                  <section className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                    <header className="border-b border-blue-50 bg-blue-50/50 px-5 py-3 text-sm font-semibold text-blue-700">Proxy suggestions</header>
                    <ul className="max-h-[220px] divide-y divide-gray-100 overflow-auto">
                      {result.proxy_suggestions.map((item, index) => (
                        <li key={`${item.day}-${item.time}-${index}`} className="px-4 py-3">
                          <p className="text-xs font-bold text-gray-700">{item.day} @ {item.time}</p>
                          <p className="text-xs text-gray-800">{item.subject}</p>
                          <p className="mt-1.5 rounded border border-gray-100 bg-gray-50 p-1.5 text-[11px]">
                            <span className="mr-2 text-gray-500 line-through">{item.primary_faculty}</span>
                            <i className="fas fa-arrow-right mr-2 text-blue-400" />
                            <span className="font-bold text-blue-600">{item.replacement_faculty}</span>
                          </p>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </form>
  )
}

function Stat({ value, label, valueClass, borderClass }: { value: number; label: string; valueClass: string; borderClass: string }) {
  return (
    <div className={`rounded-lg border bg-white p-3 text-center shadow-sm ${borderClass}`}>
      <span className={`block text-2xl font-bold ${valueClass}`}>{value}</span>
      <span className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{label}</span>
    </div>
  )
}
