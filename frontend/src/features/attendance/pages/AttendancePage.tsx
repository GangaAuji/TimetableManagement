import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { ListScreen, ListTable, Stat, displayValue, messageFrom, useSessionRole, type DataRow } from '../../../shared/components/data-list'
import { safeCount } from '../../../shared/security/sanitize'
import { TeacherAttendancePage } from '../../teacher/pages/FacultyPortal'

const recordColumns = [
  { key: 'date', label: 'Date' },
  { key: 'student', label: 'Student' },
  { key: 'course', label: 'Course' },
  { key: 'status', label: 'Status' },
]
const facultyColumns = [
  { key: 'date', label: 'Date' },
  { key: 'faculty', label: 'Faculty' },
  { key: 'status', label: 'Status' },
]
const mobileColumns = [
  { key: 'date', label: 'Date' },
  { key: 'student', label: 'Student' },
  { key: 'status', label: 'Status' },
  { key: 'processing', label: 'Processing' },
]
export function AttendancePage() {
  const setPageHeader = useSetPageHeader()
  const [summary, setSummary] = useState({ students: 0, records: 0, present: 0, late: 0, absent: 0 })
  const [rows, setRows] = useState<DataRow[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setPageHeader('Attendance')
    void apiRequest<Record<string, unknown>>('/api/attendance/overview')
      .then((data) => {
        setSummary({
          students: safeCount(data.total_students),
          records: safeCount(data.total_records),
          present: safeCount(data.total_present),
          late: safeCount(data.total_late),
          absent: safeCount(data.total_absent),
        })
        const source = Array.isArray(data.defaulters) ? data.defaulters : []
        setRows(source.map((item) => ({
          name: displayValue((item as Record<string, unknown>).name),
          course_name: displayValue((item as Record<string, unknown>).course_name),
          percentage: displayValue((item as Record<string, unknown>).percentage),
        })))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  return (
    <section className="flex flex-col gap-2">
      <div className="grid gap-2 sm:grid-cols-5">
        <Stat label="Students" value={summary.students} />
        <Stat label="Records" value={summary.records} />
        <Stat label="Present" value={summary.present} />
        <Stat label="Late" value={summary.late} />
        <Stat label="Absent" value={summary.absent} />
      </div>
      {error && <p className="text-xs text-red-700">{error}</p>}
      <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Below 75%</h3>
      <ListTable columns={[{ key: 'name', label: 'Student' }, { key: 'course_name', label: 'Course' }, { key: 'percentage', label: 'Attendance %' }]} rows={rows} />
    </section>
  )
}

export function AttendanceRecordsPage() {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-gray-500">These are the attendance marks saved by faculty.</p>
      <ListScreen title="Attendance records" path="/api/attendance/manage" rowsKey="records" columns={recordColumns} />
    </div>
  )
}
export const FacultyAttendancePage = () => <ListScreen title="Faculty attendance" path="/api/attendance/faculty" rowsKey="records" columns={facultyColumns} />
export const MobileLogsPage = () => <ListScreen title="Mobile attendance" path="/api/attendance/mobile" rowsKey="logs" columns={mobileColumns} />

export function MyAttendancePage() {
  const role = useSessionRole()
  if (role === 'Teacher') return <TeacherAttendancePage />
  return <StudentAttendancePage />
}

function StudentAttendancePage() {
  const setPageHeader = useSetPageHeader()
  const [stats, setStats] = useState({ percentage: 0, scheduled: 0, attended: 0, present: 0, late: 0, absent: 0 })
  const [subjects, setSubjects] = useState<{ id: number; subject: string; scheduled: number; attended: number; percentage: number }[]>([])
  const [recent, setRecent] = useState<{ date: string; subject: string; status: string; marked_by: string }[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('My Attendance')
    void apiRequest<{ percentage?: number; scheduled?: number; attended?: number; present?: number; late?: number; absent?: number; subjects?: typeof subjects; recent?: typeof recent }>('/api/portal/student/attendance')
      .then((data) => {
        setStats({
          percentage: Number(data.percentage) || 0,
          scheduled: Number(data.scheduled) || 0,
          attended: Number(data.attended) || 0,
          present: Number(data.present) || 0,
          late: Number(data.late) || 0,
          absent: Number(data.absent) || 0,
        })
        setSubjects(data.subjects || [])
        setRecent(data.recent || [])
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  const tone = stats.percentage >= 75 ? 'text-green-600' : stats.percentage >= 65 ? 'text-yellow-600' : 'text-red-600'
  return (
    <div className="flex flex-col gap-2">
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <div className="grid gap-2 sm:grid-cols-4">
        <Stat label="Attendance %" value={stats.percentage} />
        <Stat label="Scheduled" value={stats.scheduled} />
        <Stat label="Attended" value={stats.attended} />
        <Stat label="Absent" value={stats.absent} />
      </div>
      <p className={`text-xs font-medium ${tone}`}>Present {stats.present} · Late {stats.late} · Absent {stats.absent}</p>
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        <h2 className="border-b border-gray-100 px-6 py-4 text-lg font-bold text-gray-800">Subject attendance</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Subject</th><th className="px-6 py-3">Scheduled</th><th className="px-6 py-3">Attended</th><th className="px-6 py-3">%</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {subjects.length === 0 ? <tr><td colSpan={4} className="px-6 py-8 text-gray-500">No subject attendance yet.</td></tr> : subjects.map((row) => (
              <tr key={row.id}><td className="px-6 py-3 font-medium"><Link className="text-indigo-700" to={`/my-attendance/${row.id}`}>{row.subject}</Link></td><td className="px-6 py-3">{row.scheduled}</td><td className="px-6 py-3">{row.attended}</td><td className="px-6 py-3">{row.percentage}%</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
        <h2 className="border-b border-gray-100 px-6 py-4 text-lg font-bold text-gray-800">Recent records</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Date</th><th className="px-6 py-3">Subject</th><th className="px-6 py-3">Status</th><th className="px-6 py-3">Marked by</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {recent.length === 0 ? <tr><td colSpan={4} className="px-6 py-8 text-gray-500">No recent attendance.</td></tr> : recent.map((row) => (
              <tr key={`${row.date}-${row.subject}`}><td className="px-6 py-3">{row.date}</td><td className="px-6 py-3">{row.subject}</td><td className="px-6 py-3">{row.status}</td><td className="px-6 py-3">{row.marked_by}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export function SubjectAttendancePage() {
  const { subjectId = '' } = useParams()
  const setPageHeader = useSetPageHeader()
  const [subject, setSubject] = useState('')
  const [percentage, setPercentage] = useState(0)
  const [records, setRecords] = useState<{ date: string; status: string; start_time: string; end_time: string; remarks: string }[]>([])
  const [months, setMonths] = useState<{ month: string; total: number; present: number; absent: number; percentage: number }[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Subject attendance')
    void apiRequest<{ subject?: string; percentage?: number; records?: typeof records; months?: typeof months }>(`/api/portal/student/attendance/${subjectId}`)
      .then((data) => {
        setSubject(data.subject || '')
        setPercentage(Number(data.percentage) || 0)
        setRecords(data.records || [])
        setMonths(data.months || [])
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader, subjectId])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between"><h2 className="text-lg font-bold text-gray-800">{subject} · {percentage}%</h2><Link to="/my-attendance" className="text-xs font-bold text-indigo-600">Back</Link></div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white">
        <h3 className="border-b px-6 py-3 text-sm font-bold text-gray-700">Last six months</h3>
        <table className="w-full text-left text-sm"><tbody className="divide-y">{months.map((row) => <tr key={row.month}><td className="px-6 py-3">{row.month}</td><td className="px-6 py-3">{row.present} present</td><td className="px-6 py-3">{row.absent} absent</td><td className="px-6 py-3">{row.percentage}%</td></tr>)}</tbody></table>
      </section>
      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white">
        <h3 className="border-b px-6 py-3 text-sm font-bold text-gray-700">Records</h3>
        <table className="w-full text-left text-sm"><tbody className="divide-y">{records.map((row) => <tr key={`${row.date}-${row.start_time}`}><td className="px-6 py-3">{row.date}</td><td className="px-6 py-3">{row.start_time} - {row.end_time}</td><td className="px-6 py-3">{row.status}</td><td className="px-6 py-3 text-gray-500">{row.remarks}</td></tr>)}</tbody></table>
      </section>
    </div>
  )
}
