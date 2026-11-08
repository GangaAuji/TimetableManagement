import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import type { SessionInfo } from '../../../shared/api/endpoints'
import { displayValue, messageFrom, useSessionRole, type DataRow } from '../../../shared/components/data-list'

const weekColumns = [
  { key: 'day', label: 'Day' },
  { key: 'start_time', label: 'Start' },
  { key: 'end_time', label: 'End' },
  { key: 'subject', label: 'Subject' },
  { key: 'class_name', label: 'Class / Faculty' },
  { key: 'room', label: 'Room / Division' },
]

type SessionRow = { day: string; start: string; end: string; subject: string; faculty: string; room: string; className: string; division: string; today: boolean }

function todayLabel() {
  return new Date().toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long' })
}

export function StudentDashboard() {
  const setPageHeader = useSetPageHeader()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  const [rows, setRows] = useState<SessionRow[]>([])
  const [className, setClassName] = useState('')
  const [division, setDivision] = useState('')
  const [present, setPresent] = useState(0)
  const [percentage, setPercentage] = useState<number | null>(null)
  const [threshold, setThreshold] = useState(75)
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Overview')
    void apiRequest<Record<string, unknown>>('/api/portal/student')
      .then((data) => {
        setClassName(displayValue(data.class_name))
        setDivision(displayValue(data.division_name))
        const attendance = data.attendance as Record<string, unknown> | undefined
        setPresent(Number(attendance?.total_present) || 0)
        const figure = attendance?.percentage
        setPercentage(figure === null || figure === undefined || !Number.isFinite(Number(figure)) ? null : Number(figure))
        setThreshold(Number(attendance?.threshold) || 75)
        const source = Array.isArray(data.sessions) ? data.sessions : []
        setRows(source.map((item) => {
          const row = item as Record<string, unknown>
          return {
            day: displayValue(row.day),
            start: displayValue(row.start_time),
            end: displayValue(row.end_time),
            subject: displayValue(row.subject),
            faculty: displayValue(row.faculty),
            room: displayValue(row.room),
            className: '',
            division: '',
            today: row.today === true,
          }
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  const todayRows = rows.filter((row) => row.today)
  const tone = percentage === null ? 'text-gray-500' : percentage >= threshold ? 'text-green-600' : percentage >= threshold - 10 ? 'text-yellow-600' : 'text-red-600'
  const percentageLabel = percentage === null ? '—' : `${percentage.toFixed(2)}%`
  return (
    <div className="flex flex-col gap-2">
      <Welcome name={session.username} detail={`You have ${todayRows.length} classes scheduled for today. Keep up the great work!`} badge="Semester Active" asideLabel="Class" asideValue={`${className || '-'} ${division}`.trim()} />
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon="fa-book-open" iconClass="bg-blue-50 text-blue-600" chip="Today" value={String(todayRows.length)} label="Classes Today" />
        <Stat icon="fa-calendar-alt" iconClass="bg-purple-50 text-purple-600" chip="Weekly" value={String(rows.length)} label="Total Classes" />
        <Stat icon="fa-chart-pie" iconClass="bg-green-50 text-green-600" chip="Overall" value={percentageLabel} label="Attendance" valueClass={tone} />
        <Stat icon="fa-clipboard-check" iconClass="bg-amber-50 text-amber-600" value={String(present)} label="Classes Attended" />
      </div>
      <div className="grid items-start gap-2 xl:grid-cols-3">
        <section className="overflow-hidden rounded-[2rem] border border-gray-100 bg-white shadow-sm xl:col-span-2">
          <header className="flex items-center justify-between border-b border-gray-100 px-8 py-6">
            <div>
              <h3 className="text-lg font-bold text-gray-800">Today's Schedule</h3>
              <p className="mt-1 text-xs text-gray-500">{todayLabel()}</p>
            </div>
            <Link to="/my-timetable" className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-2 text-xs font-bold tracking-wide text-gray-600 uppercase">Full Schedule</Link>
          </header>
          <div className="space-y-4 p-6">
            {todayRows.length === 0 ? <Empty icon="fa-mug-hot" title="No Classes Today" text="Enjoy your day off!" /> : todayRows.map((row) => (
              <div key={`${row.start}-${row.subject}`} className="flex items-center gap-4 rounded-xl bg-gray-50/50 p-4 hover:bg-indigo-50/50">
                <div className="w-16 text-center">
                  <p className="text-xs font-medium text-gray-400 uppercase">Start</p>
                  <p className="text-lg font-bold text-gray-800">{row.start}</p>
                </div>
                <div className="h-12 w-px bg-gray-200" />
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold text-gray-800">{row.subject}</h4>
                  <p className="truncate text-sm text-gray-500"><i className="fas fa-user mr-1 text-gray-400" />{row.faculty || 'Faculty'}{row.room ? <span> <span className="mx-2 text-gray-300">|</span><i className="fas fa-door-open mr-1 text-gray-400" />{row.room}</span> : null}</p>
                </div>
                <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-medium text-indigo-600">{row.start} - {row.end}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-[2rem] border border-gray-100 bg-white p-6 shadow-sm">
          <h3 className="mb-4 text-lg font-bold text-gray-800">Quick Actions</h3>
          <div className="space-y-3">
            <Action href="/my-timetable" icon="fa-calendar-alt" tint="bg-indigo-50 text-indigo-600" title="View Timetable" text="Weekly class schedule" />
            <Action href="/my-attendance" icon="fa-clipboard-check" tint="bg-green-50 text-green-600" title="My Attendance" text="Track your attendance" />
          </div>
        </section>
      </div>
    </div>
  )
}

export function TeacherDashboard() {
  const setPageHeader = useSetPageHeader()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  const [rows, setRows] = useState<SessionRow[]>([])
  const [pending, setPending] = useState(0)
  const [leaves, setLeaves] = useState(0)
  const [todayName, setTodayName] = useState('')
  const [facultyName, setFacultyName] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Overview')
    void apiRequest<Record<string, unknown>>('/api/portal/teacher')
      .then((data) => {
        const absences = Array.isArray(data.absences) ? data.absences : []
        setTodayName(displayValue(data.today))
        setFacultyName(displayValue(data.name))
        setLeaves(absences.length)
        setPending(absences.filter((item) => String((item as Record<string, unknown>).status || '').toLowerCase() === 'pending').length)
        const source = Array.isArray(data.sessions) ? data.sessions : []
        setRows(source.map((item) => {
          const row = item as Record<string, unknown>
          return {
            day: displayValue(row.day),
            start: displayValue(row.start_time),
            end: displayValue(row.end_time),
            subject: displayValue(row.subject),
            faculty: '',
            room: '',
            className: displayValue(row.class_name),
            division: displayValue(row.division_name),
            today: row.today === true,
          }
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  const todayCount = rows.filter((row) => row.today).length
  return (
    <div className="flex flex-col gap-2">
      <Welcome name={facultyName || session.username} detail={`You have ${todayCount} classes scheduled for today. Ready to inspire some minds?`} badge="System Active" asideLabel="Today" asideValue={todayName || todayLabel()} />
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon="fa-book-open" iconClass="bg-blue-50 text-blue-600" chip="Today" value={String(todayCount)} label="Classes Scheduled" />
        <Stat icon="fa-chart-pie" iconClass="bg-purple-50 text-purple-600" chip="Weekly" value={String(rows.length)} label="Total Load" />
        <Stat icon="fa-hourglass-half" iconClass="bg-amber-50 text-amber-600" value={String(pending)} label="Pending Requests" />
        <Stat icon="fa-user-clock" iconClass="bg-red-50 text-red-600" value={String(leaves)} label="Total Leaves" />
      </div>
      <section className="overflow-hidden rounded-[2rem] border border-gray-100 bg-white shadow-sm">
        <header className="border-b border-gray-100 px-8 py-6">
          <h3 className="text-lg font-bold text-gray-800">Weekly Schedule</h3>
          <p className="mt-1 text-xs text-gray-500">Your teaching timeline</p>
        </header>
        <div className="overflow-auto">
          <table className="w-full text-left">
            <thead className="bg-white text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-6 py-4">Day</th>
                <th className="px-6 py-4">Timing</th>
                <th className="px-6 py-4">Subject</th>
                <th className="px-6 py-4">Location</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 text-sm">
              {rows.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-16 text-center text-gray-500">No schedule found</td></tr>
              ) : rows.map((row) => (
                <tr key={`${row.day}-${row.start}-${row.subject}`} className="hover:bg-gray-50/80">
                  <td className="px-6 py-4"><span className="rounded-lg border border-gray-100 bg-gray-100/50 px-3 py-1 text-sm font-bold text-gray-700">{row.day.slice(0, 3)}</span></td>
                  <td className="px-6 py-4 text-gray-600"><i className="far fa-clock mr-2 text-gray-300" />{row.start} - {row.end}</td>
                  <td className="px-6 py-4 font-bold text-gray-800">{row.subject}</td>
                  <td className="px-6 py-4"><span className="rounded-md border border-indigo-100 bg-indigo-50 px-2.5 py-1 text-xs font-bold text-indigo-600">{row.className}</span> <span className="text-xs text-gray-400">Div {row.division}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function Welcome({ name, detail, badge, asideLabel, asideValue }: { name: string; detail: string; badge: string; asideLabel: string; asideValue: string }) {
  return (
    <div className="relative flex flex-col items-center justify-between gap-6 overflow-hidden rounded-[2rem] border border-gray-100 bg-white p-8 shadow-sm md:flex-row">
      <div>
        <div className="mb-2 flex items-center gap-3">
          <span className="rounded-full border border-green-100 bg-green-50 px-3 py-1 text-[10px] font-bold tracking-wider text-green-600 uppercase">{badge}</span>
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-gray-800 md:text-4xl">Hello, <span className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">{name}</span>!</h1>
        <p className="mt-2 max-w-lg text-sm text-gray-500">{detail}</p>
      </div>
      <div className="flex items-center gap-4">
        <div className="hidden text-right md:block">
          <p className="text-xs font-bold tracking-wider text-gray-400 uppercase">{asideLabel}</p>
          <p className="text-lg font-bold text-gray-700">{asideValue}</p>
        </div>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg"><i className="fas fa-graduation-cap text-xl" /></div>
      </div>
    </div>
  )
}

function Stat({ icon, iconClass, chip, value, label, valueClass = 'text-gray-800' }: { icon: string; iconClass: string; chip?: string; value: string; label: string; valueClass?: string }) {
  return (
    <div className="rounded-[1.5rem] border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl text-lg ${iconClass}`}><i className={`fas ${icon}`} /></div>
        {chip ? <span className="rounded-lg bg-gray-50 px-2 py-1 text-xs font-bold text-gray-400">{chip}</span> : null}
      </div>
      <h3 className={`text-3xl font-bold ${valueClass}`}>{value}</h3>
      <p className="mt-1 text-xs font-medium tracking-wide text-gray-500 uppercase">{label}</p>
    </div>
  )
}

function Action({ href, icon, tint, title, text }: { href: string; icon: string; tint: string; title: string; text: string }) {
  return (
    <Link to={href} className={`flex items-center gap-3 rounded-xl p-3 ${tint.split(' ')[0]}`}>
      <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${tint}`}><i className={`fas ${icon}`} /></span>
      <span>
        <p className="font-medium text-gray-800">{title}</p>
        <p className="text-xs text-gray-500">{text}</p>
      </span>
    </Link>
  )
}

function Empty({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="py-12 text-center">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gray-100"><i className={`fas ${icon} text-2xl text-gray-400`} /></div>
      <h4 className="text-lg font-medium text-gray-800">{title}</h4>
      <p className="mt-1 text-sm text-gray-500">{text}</p>
    </div>
  )
}

export function TeacherHome() {
  return <TeacherDashboard />
}

export { MyClassesPage } from './FacultyPortal'

export function WeekSchedule({ title, path }: { title: string; path: string }) {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader(title)
    void apiRequest<Record<string, unknown>>(path)
      .then((data) => {
        const attendance = data.attendance as Record<string, unknown> | undefined
        if (attendance) {
          const figure = attendance.percentage
          const label = figure === null || figure === undefined || !Number.isFinite(Number(figure)) ? '—' : `${Number(figure).toFixed(2)}%`
          setNote(`Attendance ${label} · Attended ${displayValue(attendance.total_present)} · Absent ${displayValue(attendance.total_absent)}`)
        }
        else if (data.today) setNote(`Today is ${displayValue(data.today)}`)
        const source = Array.isArray(data.sessions) ? data.sessions : []
        setRows(source.map((item) => {
          const row = item as Record<string, unknown>
          return {
            day: displayValue(row.day),
            start_time: displayValue(row.start_time),
            end_time: displayValue(row.end_time),
            subject: displayValue(row.subject),
            class_name: displayValue(row.class_name || row.faculty),
            room: displayValue(row.room || row.division_name),
          }
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [path, setPageHeader, title])
  return (
    <section className="overflow-hidden rounded-[2rem] border border-gray-100 bg-white shadow-sm">
      <header className="border-b border-gray-100 px-8 py-6">
        <h3 className="text-lg font-bold text-gray-800">{title}</h3>
        {note ? <p className="mt-1 text-xs text-gray-500">{note}</p> : null}
        {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
      </header>
      <div className="overflow-auto">
        <table className="w-full text-left">
          <thead className="bg-white text-[10px] font-bold tracking-wider text-gray-400 uppercase">
            <tr>
              {weekColumns.map((column) => <th key={column.key} className="px-6 py-4">{column.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 text-sm">
            {rows.length === 0 ? (
              <tr><td colSpan={weekColumns.length} className="px-6 py-16 text-center text-gray-500">No classes scheduled</td></tr>
            ) : rows.map((row, index) => (
              <tr key={`${row.day}-${row.start_time}-${index}`} className="hover:bg-gray-50/80">
                {weekColumns.map((column) => <td key={column.key} className="px-6 py-4 text-gray-700">{displayValue(row[column.key])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function MyWeekPage() {
  const role = useSessionRole()
  if (role === 'Student') return <WeekSchedule title="My Timetable" path="/api/portal/student" />
  return <WeekSchedule title="Timetable" path="/api/portal/teacher" />
}
