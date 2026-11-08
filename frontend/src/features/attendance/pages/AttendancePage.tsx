import { useCallback, useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import type { SessionInfo } from '../../../shared/api/endpoints'
import { ListTable, Stat, displayValue, messageFrom, postJson, useSessionRole, type DataRow } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { TeacherAttendancePage } from '../../teacher/pages/FacultyPortal'

/** A percentage with two places, or a dash when there is nothing to measure. */
export function percentLabel(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return `${Math.min(Math.max(number, 0), 100).toFixed(2)}%`
}

function optionalCount(value: unknown) {
  if (value === null || value === undefined) return '—'
  return String(safeCount(value))
}

function percentTone(value: number | null, threshold: number) {
  if (value === null) return 'text-gray-500'
  if (value >= threshold) return 'text-green-600'
  if (value >= threshold - 10) return 'text-yellow-600'
  return 'text-red-600'
}

type Figures = {
  held: number
  countable: number
  attended: number
  present: number
  late: number
  absent: number
  excused: number
  not_marked: number
  unrecorded: number
  percentage: number | null
}

const emptyFigures: Figures = { held: 0, countable: 0, attended: 0, present: 0, late: 0, absent: 0, excused: 0, not_marked: 0, unrecorded: 0, percentage: null }

function readFigures(source: Record<string, unknown> | undefined): Figures {
  const value = source || {}
  const percentage = value.percentage === null || value.percentage === undefined ? null : Number(value.percentage)
  return {
    held: safeCount(value.held),
    countable: safeCount(value.countable),
    attended: safeCount(value.attended),
    present: safeCount(value.present),
    late: safeCount(value.late),
    absent: safeCount(value.absent),
    excused: safeCount(value.excused),
    not_marked: safeCount(value.not_marked),
    unrecorded: safeCount(value.unrecorded),
    percentage: percentage !== null && Number.isFinite(percentage) ? percentage : null,
  }
}

const CANCEL_REASONS = [
  { value: 'faculty_absent', label: 'Faculty absent' },
  { value: 'institution', label: 'Institution closed' },
  { value: 'exam', label: 'Examination' },
  { value: 'other', label: 'Other' },
]

type UnmarkedSession = { id: number; date: string; subject: string; class_name: string; division_name: string; teacher: string; start_time: string; end_time: string }

function NotMarkedLectures({ canManage }: { canManage: boolean }) {
  const [rows, setRows] = useState<UnmarkedSession[]>([])
  const [error, setError] = useState('')
  const [reason, setReason] = useState('faculty_absent')
  const load = useCallback(() => {
    void apiRequest<{ sessions?: Record<string, unknown>[] }>('/api/attendance/sessions?status=not_marked')
      .then((data) => {
        setRows((data.sessions || []).map((item) => ({
          id: safeCount(item.id),
          date: safeText(item.date, 10),
          subject: safeText(item.subject, 100),
          class_name: safeText(item.class_name, 100),
          division_name: safeText(item.division_name, 50),
          teacher: safeText(item.teacher, 100),
          start_time: safeText(item.start_time, 5),
          end_time: safeText(item.end_time, 5),
        })))
      })
      .catch((cause: unknown) => setError(messageFrom(cause)))
  }, [])
  useEffect(() => { load() }, [load])

  async function cancel(id: number) {
    setError('')
    try {
      await postJson(`/api/attendance/sessions/${id}/cancel`, { reason, note: '' })
      load()
    } catch (cause) {
      setError(messageFrom(cause))
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-6 py-4">
        <div>
          <h2 className="text-lg font-bold text-gray-800">Lectures nobody marked</h2>
          <p className="text-xs text-gray-500">Recorded by close-day. They are not counted until marked; cancel the ones that did not happen.</p>
        </div>
        {canManage ? (
          <label className="flex items-center gap-2 text-xs text-gray-600">
            Cancel reason
            <select value={reason} onChange={(event) => setReason(event.target.value)} className="rounded-lg border border-gray-200 px-2 py-1">
              {CANCEL_REASONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
        ) : null}
      </header>
      {error ? <p className="px-6 py-3 text-xs text-red-700">{error}</p> : null}
      <table className="w-full text-left text-sm">
        <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">
          <tr><th className="px-6 py-3">Date</th><th className="px-6 py-3">Time</th><th className="px-6 py-3">Subject</th><th className="px-6 py-3">Class</th><th className="px-6 py-3">Teacher</th>{canManage ? <th className="px-6 py-3" /> : null}</tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {rows.length === 0 ? <tr><td colSpan={canManage ? 6 : 5} className="px-6 py-6 text-gray-500">Every recorded lecture has been marked.</td></tr> : rows.map((row) => (
            <tr key={row.id}>
              <td className="px-6 py-3">{row.date}</td>
              <td className="px-6 py-3">{row.start_time} - {row.end_time}</td>
              <td className="px-6 py-3 font-medium">{row.subject}</td>
              <td className="px-6 py-3">{row.class_name}{row.division_name ? ` ${row.division_name}` : ''}</td>
              <td className="px-6 py-3">{row.teacher}</td>
              {canManage ? <td className="px-6 py-3 text-right"><button type="button" onClick={() => void cancel(row.id)} className="rounded-lg border border-gray-200 px-3 py-1 text-xs font-bold text-gray-600">Cancel lecture</button></td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function AttendancePage() {
  const setPageHeader = useSetPageHeader()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  const canManage = session.unrestricted || session.permissions.includes('attendance_manage')
  const [summary, setSummary] = useState({ students: 0, lectures: 0, records: 0, present: 0, late: 0, absent: 0, excused: 0, defaulters: 0, notMarked: 0 })
  const [periodPercent, setPeriodPercent] = useState<number | null>(null)
  const [periodDays, setPeriodDays] = useState(30)
  const [threshold, setThreshold] = useState(75)
  const [rows, setRows] = useState<DataRow[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setPageHeader('Attendance')
    void apiRequest<Record<string, unknown>>('/api/attendance/overview')
      .then((data) => {
        setSummary({
          students: safeCount(data.total_students),
          lectures: safeCount(data.total_lectures),
          records: safeCount(data.total_records),
          present: safeCount(data.total_present),
          late: safeCount(data.total_late),
          absent: safeCount(data.total_absent),
          excused: safeCount(data.total_excused),
          defaulters: safeCount(data.defaulter_count),
          notMarked: safeCount(data.not_marked_count),
        })
        setPeriodPercent(typeof data.percentage === 'number' ? data.percentage : null)
        setPeriodDays(safeCount(data.period_days) || 30)
        setThreshold(Number(data.threshold) || 75)
        const source = Array.isArray(data.defaulters) ? data.defaulters : []
        setRows(source.map((item) => {
          const row = item as Record<string, unknown>
          return {
            roll_number: displayValue(row.roll_number),
            name: displayValue(row.name),
            class_info: [displayValue(row.course_name), displayValue(row.class_name), displayValue(row.division_name)].filter(Boolean).join(' · '),
            attended: `${safeCount(row.attended)} / ${safeCount(row.countable)}`,
            percentage: percentLabel(row.percentage),
            classes_needed: optionalCount(row.classes_needed),
          }
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Last {periodDays} days</h3>
      <div className="grid gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Stat label="Students" value={summary.students} />
        <Stat label="Lectures" value={summary.lectures} />
        <Stat label="Countable" value={summary.records} />
        <Stat label="Present" value={summary.present} />
        <Stat label="Late" value={summary.late} />
        <Stat label="Absent" value={summary.absent} />
        <Stat label="Excused" value={summary.excused} />
        <div className="rounded-2xl border border-gray-200 bg-white p-4"><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Attendance</p><p className="mt-1 text-xl font-bold text-gray-800">{percentLabel(periodPercent)}</p></div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Stat label={`Below ${threshold}% (overall)`} value={summary.defaulters} />
        <Stat label="Lectures not marked" value={summary.notMarked} />
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Below {threshold}% (held lectures only)</h3>
      <ListTable
        columns={[
          { key: 'roll_number', label: 'Roll' },
          { key: 'name', label: 'Student' },
          { key: 'class_info', label: 'Class' },
          { key: 'attended', label: 'Attended / Countable' },
          { key: 'percentage', label: 'Attendance %' },
          { key: 'classes_needed', label: 'Classes needed' },
        ]}
        rows={rows}
      />
      <NotMarkedLectures canManage={canManage} />
    </section>
  )
}

type Choice = { id: number; name: string }
type AttendanceRecord = { id: number; roll: string; student: string; course: string; className: string; division: string; date: string; status: string; remarks: string }
const markStatuses = ['Present', 'Absent', 'Late']

function todayInput() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export function AttendanceRecordsPage() {
  const setPageHeader = useSetPageHeader()
  const [date, setDate] = useState(todayInput)
  const [courseId, setCourseId] = useState('')
  const [classId, setClassId] = useState('')
  const [divisionId, setDivisionId] = useState('')
  const [courses, setCourses] = useState<Choice[]>([])
  const [classes, setClasses] = useState<Choice[]>([])
  const [divisions, setDivisions] = useState<Choice[]>([])
  const [rows, setRows] = useState<AttendanceRecord[]>([])
  const [drafts, setDrafts] = useState<Record<number, { status: string; remarks: string }>>({})
  const [busyId, setBusyId] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback((nextDate: string, nextCourse: string, nextClass: string, nextDivision: string) => {
    const query = new URLSearchParams({ date: nextDate })
    if (nextCourse) query.set('course_id', nextCourse)
    if (nextClass) query.set('class_id', nextClass)
    if (nextDivision) query.set('division_id', nextDivision)
    return apiRequest<Record<string, unknown>>(`/api/attendance/manage?${query.toString()}`).then((data) => {
      const source = Array.isArray(data.records) ? data.records : []
      const readChoice = (item: unknown): Choice => {
        const row = item as Record<string, unknown>
        return { id: safeCount(row.id), name: safeText(row.name, 100) }
      }
      const records = source.map((item) => {
        const row = item as Record<string, unknown>
        return {
          id: safeCount(row.id),
          roll: safeText(row.roll, 30),
          student: safeText(row.student, 100),
          course: safeText(row.course, 100),
          className: safeText(row.class_name, 100),
          division: safeText(row.division, 50),
          date: safeText(row.date, 10),
          status: safeText(row.status, 20),
          remarks: safeText(row.remarks, 200),
        }
      })
      setRows(records)
      setDrafts(Object.fromEntries(records.map((row) => [row.id, { status: markStatuses.includes(row.status) ? row.status : 'Present', remarks: row.remarks }])))
      setCourses((Array.isArray(data.courses) ? data.courses : []).map(readChoice).filter((item) => item.id && item.name))
      setClasses((Array.isArray(data.classes) ? data.classes : []).map(readChoice).filter((item) => item.id && item.name))
      setDivisions((Array.isArray(data.divisions) ? data.divisions : []).map(readChoice).filter((item) => item.id && item.name))
    })
  }, [])

  useEffect(() => {
    setPageHeader('Attendance records')
    void load(date, courseId, classId, divisionId).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [classId, courseId, date, divisionId, load, setPageHeader])

  function save(id: number) {
    const draft = drafts[id]
    if (!draft || busyId) return
    setBusyId(id)
    setError('')
    void postJson(`/api/attendance/manage/${id}`, draft)
      .then(() => load(date, courseId, classId, divisionId))
      .then(() => setNotice('Attendance updated.'))
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusyId(0))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <p className="text-sm text-gray-500">Marks saved by faculty for the selected day. Correct a status or remark here.</p>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="rounded-r-lg border-l-4 border-green-500 bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="text-sm text-gray-700">Date
          <input className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </label>
        <label className="text-sm text-gray-700">Course
          <select className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
            <option value="">All</option>
            {courses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-700">Class
          <select className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" value={classId} onChange={(event) => setClassId(event.target.value)}>
            <option value="">All</option>
            {classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-700">Division
          <select className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2" value={divisionId} onChange={(event) => setDivisionId(event.target.value)}>
            <option value="">All</option>
            {divisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      </div>
      <div className="min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th className="px-4 py-3">Class</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Remarks</th>
                <th className="px-4 py-3">Save</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-16 text-center text-gray-500">No marks for this day.</td></tr>
              ) : rows.map((row) => {
                const draft = drafts[row.id] || { status: row.status, remarks: row.remarks }
                return (
                  <tr key={row.id}>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-gray-800">{row.student}</p>
                      <p className="text-xs text-gray-400">{row.roll} · {row.course}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{row.className}{row.division ? ` · ${row.division}` : ''}</td>
                    <td className="px-4 py-3">
                      <select className="rounded-md border border-gray-300 px-2 py-1" value={draft.status} onChange={(event) => setDrafts({ ...drafts, [row.id]: { ...draft, status: event.target.value } })}>
                        {markStatuses.map((status) => <option key={status}>{status}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <input className="w-full rounded-md border border-gray-300 px-2 py-1" maxLength={200} value={draft.remarks} onChange={(event) => setDrafts({ ...drafts, [row.id]: { ...draft, remarks: event.target.value } })} />
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" className="text-sm font-semibold text-indigo-600 disabled:opacity-50" disabled={busyId === row.id} onClick={() => save(row.id)}>{busyId === row.id ? 'Saving…' : 'Save'}</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
export { FacultyAttendancePage } from './FacultyAttendancePage'
export { MobileLogsPage } from './MobileLogsPage'

export function MyAttendancePage() {
  const role = useSessionRole()
  if (role === 'Teacher') return <TeacherAttendancePage />
  return <StudentAttendancePage />
}

type SubjectRow = Figures & { id: number; subject: string; components: string[] }
type RecentRow = { date: string; subject: string; status: string; marked_by: string }

function StudentAttendancePage() {
  const setPageHeader = useSetPageHeader()
  const [stats, setStats] = useState<Figures>(emptyFigures)
  const [threshold, setThreshold] = useState(75)
  const [needed, setNeeded] = useState<number | null>(null)
  const [canMiss, setCanMiss] = useState<number | null>(null)
  const [components, setComponents] = useState<{ name: string; figures: Figures }[]>([])
  const [subjects, setSubjects] = useState<SubjectRow[]>([])
  const [recent, setRecent] = useState<RecentRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('My Attendance')
    void apiRequest<Record<string, unknown>>('/api/portal/student/attendance')
      .then((data) => {
        setStats(readFigures(data))
        setThreshold(Number(data.threshold) || 75)
        setNeeded(data.classes_needed === null || data.classes_needed === undefined ? null : safeCount(data.classes_needed))
        setCanMiss(data.classes_that_can_be_missed === null || data.classes_that_can_be_missed === undefined ? null : safeCount(data.classes_that_can_be_missed))
        const parts = (data.components || {}) as Record<string, Record<string, unknown>>
        setComponents(Object.keys(parts).sort().map((name) => ({ name, figures: readFigures(parts[name]) })))
        const rows = Array.isArray(data.subjects) ? (data.subjects as Record<string, unknown>[]) : []
        setSubjects(rows.map((row) => ({
          ...readFigures(row),
          id: safeCount(row.id),
          subject: safeText(row.subject, 100),
          components: Array.isArray(row.components) ? row.components.map((name) => safeText(name, 12)) : [],
        })))
        const latest = Array.isArray(data.recent) ? (data.recent as Record<string, unknown>[]) : []
        setRecent(latest.map((row) => ({
          date: safeText(row.date, 10),
          subject: safeText(row.subject, 100),
          status: safeText(row.status, 20),
          marked_by: safeText(row.marked_by, 100),
        })))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  const tone = percentTone(stats.percentage, threshold)
  const advice = stats.percentage === null
    ? 'No lectures have been recorded for you yet.'
    : needed === null
      ? `The ${threshold}% minimum cannot be reached any more.`
      : needed > 0
        ? `Attend the next ${needed} lecture${needed === 1 ? '' : 's'} to reach ${threshold}%.`
        : `You can miss ${canMiss ?? 0} more lecture${canMiss === 1 ? '' : 's'} and stay at ${threshold}%.`
  return (
    <div className="flex flex-col gap-2">
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm">
          <p className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">Attendance %</p>
          <p className={`text-2xl font-bold ${tone}`}>{percentLabel(stats.percentage)}</p>
        </div>
        <Stat label="Held" value={stats.held} />
        <Stat label="Attended" value={stats.attended} />
        <Stat label="Absent" value={stats.absent} />
        <Stat label="Excused" value={stats.excused} />
        <Stat label="Not marked" value={stats.not_marked} />
      </div>
      <p className={`text-xs font-medium ${tone}`}>Present {stats.present} · Late {stats.late} · Absent {stats.absent} · {advice}</p>
      {components.length > 0 ? (
        <p className="text-xs text-gray-500">
          {components.map((part) => `${part.name} ${percentLabel(part.figures.percentage)} (${part.figures.attended}/${part.figures.countable})`).join(' · ')}
        </p>
      ) : null}
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        <h2 className="border-b border-gray-100 px-6 py-4 text-lg font-bold text-gray-800">Subject attendance</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Subject</th><th className="px-6 py-3">Held</th><th className="px-6 py-3">Attended</th><th className="px-6 py-3">Absent</th><th className="px-6 py-3">Excused</th><th className="px-6 py-3">Not marked</th><th className="px-6 py-3">%</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {subjects.length === 0 ? <tr><td colSpan={7} className="px-6 py-8 text-gray-500">No lectures have been recorded yet.</td></tr> : subjects.map((row) => (
              <tr key={row.id}>
                <td className="px-6 py-3 font-medium"><Link className="text-indigo-700" to={`/my-attendance/${row.id}`}>{row.subject}</Link>{row.components.includes('Practical') ? <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold text-gray-500">{row.components.join(' + ')}</span> : null}</td>
                <td className="px-6 py-3">{row.held}</td>
                <td className="px-6 py-3">{row.attended} / {row.countable}</td>
                <td className="px-6 py-3">{row.absent}</td>
                <td className="px-6 py-3">{row.excused}</td>
                <td className="px-6 py-3">{row.not_marked}</td>
                <td className={`px-6 py-3 font-medium ${percentTone(row.percentage, threshold)}`}>{percentLabel(row.percentage)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        <h2 className="border-b border-gray-100 px-6 py-4 text-lg font-bold text-gray-800">Last 30 days</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Date</th><th className="px-6 py-3">Subject</th><th className="px-6 py-3">Status</th><th className="px-6 py-3">Marked by</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {recent.length === 0 ? <tr><td colSpan={4} className="px-6 py-8 text-gray-500">No lectures in the last 30 days.</td></tr> : recent.map((row) => (
              <tr key={`${row.date}-${row.subject}`}><td className="px-6 py-3">{row.date}</td><td className="px-6 py-3">{row.subject}</td><td className="px-6 py-3">{row.status}</td><td className="px-6 py-3">{row.marked_by || '—'}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

type SubjectRecord = { date: string; status: string; start_time: string; end_time: string; remarks: string }
type MonthRow = { month: string; countable: number; attended: number; present: number; late: number; absent: number; excused: number; not_marked: number; percentage: number | null }

export function SubjectAttendancePage() {
  const { subjectId = '' } = useParams()
  const setPageHeader = useSetPageHeader()
  const [subject, setSubject] = useState('')
  const [figures, setFigures] = useState<Figures>(emptyFigures)
  const [threshold, setThreshold] = useState(75)
  const [records, setRecords] = useState<SubjectRecord[]>([])
  const [months, setMonths] = useState<MonthRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Subject attendance')
    void apiRequest<Record<string, unknown>>(`/api/portal/student/attendance/${subjectId}`)
      .then((data) => {
        setSubject(safeText(data.subject, 100))
        setFigures(readFigures(data))
        setThreshold(Number(data.threshold) || 75)
        const rows = Array.isArray(data.records) ? (data.records as Record<string, unknown>[]) : []
        setRecords(rows.map((row) => ({
          date: safeText(row.date, 10),
          status: safeText(row.status, 20),
          start_time: safeText(row.start_time, 5),
          end_time: safeText(row.end_time, 5),
          remarks: safeText(row.remarks, 200),
        })))
        const periods = Array.isArray(data.months) ? (data.months as Record<string, unknown>[]) : []
        setMonths(periods.map((row) => ({ ...readFigures(row), month: safeText(row.month, 7) })))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader, subjectId])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-800">{subject} · <span className={percentTone(figures.percentage, threshold)}>{percentLabel(figures.percentage)}</span></h2>
        <Link to="/my-attendance" className="text-xs font-bold text-indigo-600">Back</Link>
      </div>
      <p className="text-xs text-gray-500">Held {figures.held} · Attended {figures.attended} of {figures.countable} · Absent {figures.absent} · Excused {figures.excused} · Not marked {figures.not_marked}</p>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white">
        <h3 className="border-b px-6 py-3 text-sm font-bold text-gray-700">Last six months</h3>
        <table className="w-full text-left text-sm"><tbody className="divide-y">{months.map((row) => <tr key={row.month}><td className="px-6 py-3">{row.month}</td><td className="px-6 py-3">{row.attended} of {row.countable} attended</td><td className="px-6 py-3">{row.absent} absent</td><td className="px-6 py-3">{percentLabel(row.percentage)}</td></tr>)}</tbody></table>
      </section>
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white">
        <h3 className="border-b px-6 py-3 text-sm font-bold text-gray-700">Lectures</h3>
        <table className="w-full text-left text-sm"><tbody className="divide-y">{records.length === 0 ? <tr><td className="px-6 py-6 text-gray-500">No lectures have been recorded yet.</td></tr> : records.map((row) => <tr key={`${row.date}-${row.start_time}`}><td className="px-6 py-3">{row.date}</td><td className="px-6 py-3">{row.start_time} - {row.end_time}</td><td className="px-6 py-3">{row.status}</td><td className="px-6 py-3 text-gray-500">{row.remarks}</td></tr>)}</tbody></table>
      </section>
    </div>
  )
}
