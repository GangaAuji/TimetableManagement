import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { todayInput } from '../../../shared/dates'
import { FailureNotice, SuccessNotice, WarningNotice } from '../../../shared/components/success-notice'
import { displayValue, messageFrom, postJson, useCapability } from '../../../shared/components/data-list'
import { PreferencesEditor } from '../../timetable/PreferencesEditor'

const field = 'mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-800 outline-none focus:border-gray-400'
const card = 'rounded-2xl border border-gray-200 bg-white'
const labelClass = 'block text-[11px] font-semibold tracking-wide text-gray-500 uppercase'
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

type Slot = { start: string; end: string; notes: string }
type DayDraft = { day: string; available: boolean; slots: Slot[] }
type Notice = { error: string; saved: string }

function useNotice() {
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  return { error, saved, setError, setSaved, clear() { setError(''); setSaved('') } }
}

function Banner({ notice }: { notice: Notice }) {
  return (
    <>
      <FailureNotice message={notice.error} />
      <SuccessNotice message={notice.saved} />
    </>
  )
}

const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function weekdayFromStamp(value: string) {
  const iso = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  const written = value.match(/^(\d{1,2}) ([A-Za-z]{3}) (\d{4})$/)
  const date = iso
    ? new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]))
    : written && monthNames.includes(written[2])
      ? new Date(Number(written[3]), monthNames.indexOf(written[2]), Number(written[1]))
      : null
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString('en-US', { weekday: 'long' }) : ''
}

function pretty(value: string) {
  const text = value.trim()
  if (!text || text.toUpperCase() === 'PENDING') return 'Pending'
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase()
}

function approvalClass(value: string) {
  const text = value.toUpperCase()
  if (text === 'APPROVED') return 'border-emerald-100 bg-emerald-50 text-emerald-700'
  if (text === 'REJECTED') return 'border-rose-100 bg-rose-50 text-rose-700'
  return 'border-amber-100 bg-amber-50 text-amber-700'
}

function Pill({ children, className }: { children: string; className: string }) {
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase ${className}`}>{children}</span>
}

export function MyAvailabilityPage() {
  const setPageHeader = useSetPageHeader()
  const notice = useNotice()
  const [rows, setRows] = useState<DayDraft[]>([])
  useEffect(() => {
    setPageHeader('Availability')
    void apiRequest<{ days?: { day: string; slots: { available: boolean; start_time: string; end_time: string; notes: string }[] }[] }>('/api/portal/availability/slots')
      .then((data) => {
        const source = new Map((data.days || []).map((day) => [day.day, day.slots || []]))
        setRows(days.map((day) => {
          const slots = (source.get(day) || []).filter((slot) => slot.start_time && slot.end_time).map((slot) => ({
            start: slot.start_time,
            end: slot.end_time,
            notes: slot.notes || '',
          }))
          const available = (source.get(day) || []).some((slot) => slot.available)
          return { day, available, slots: slots.length ? slots : [{ start: '', end: '', notes: '' }] }
        }))
      })
      .catch((reason: unknown) => notice.setError(messageFrom(reason)))
  }, [setPageHeader])

  function update(index: number, patch: Partial<DayDraft>) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)))
  }

  async function save() {
    notice.clear()
    try {
      await postJson('/api/portal/availability/slots', {
        days: rows.map((row) => ({
          day: row.day,
          available: row.available,
          slots: row.slots.filter((slot) => slot.start && slot.end),
        })),
      })
      notice.setSaved('Availability updated.')
    } catch (reason) {
      notice.setError(messageFrom(reason))
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={(event) => { event.preventDefault(); void save() }}>
      <div className="sticky top-0 z-10 flex flex-col gap-2 rounded-2xl border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-600">Tick the days you can teach, then set the times.</p>
        <button type="submit" className="rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white">Save availability</button>
      </div>
      <Banner notice={notice} />
      <section className={`${card} divide-y divide-gray-100`}>
        {rows.map((row, index) => (
          <div key={row.day} className="flex flex-col gap-3 p-4 sm:flex-row">
            <label className="flex min-w-36 items-center gap-2 text-sm font-bold text-gray-800">
              <input type="checkbox" checked={row.available} onChange={(event) => update(index, { available: event.target.checked })} className="h-4 w-4 accent-gray-800" />
              {row.day}
            </label>
            {row.available ? (
              <div className="min-w-0 flex-1 space-y-2">
                {row.slots.map((slot, slotIndex) => (
                  <div key={`${row.day}-${slotIndex}`} className="grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr]">
                    <input aria-label={`${row.day} start`} type="time" value={slot.start} onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, start: event.target.value } : item) })} className={field} />
                    <input aria-label={`${row.day} end`} type="time" value={slot.end} onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, end: event.target.value } : item) })} className={field} />
                    <input aria-label={`${row.day} notes`} value={slot.notes} maxLength={200} placeholder="Notes" onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, notes: event.target.value } : item) })} className={field} />
                  </div>
                ))}
                <button type="button" className="text-xs font-bold text-gray-700" onClick={() => update(index, { slots: [...row.slots, { start: '', end: '', notes: '' }] })}>Add another time</button>
              </div>
            ) : <p className="text-sm text-gray-400 sm:pt-2">Not available</p>}
          </div>
        ))}
      </section>
      <PreferencesEditor path="/api/portal/preferences" />
    </form>
  )
}

type ShiftRow = { day: string; day_num: number; available: boolean; shift: string; start_time: string; end_time: string }
type ShiftRequest = { day: string; current_shift: string; requested_shift: string; reason: string; status: string; response: string; created_at: string }

export function MyShiftsPage() {
  const setPageHeader = useSetPageHeader()
  const notice = useNotice()
  const [schedule, setSchedule] = useState<ShiftRow[]>([])
  const [patterns, setPatterns] = useState<{ name: string }[]>([])
  const [requests, setRequests] = useState<ShiftRequest[]>([])
  const [day, setDay] = useState('Monday')
  const [requested, setRequested] = useState('')
  const [reason, setReason] = useState('')

  function load() {
    void apiRequest<{ schedule?: ShiftRow[]; patterns?: { name: string }[]; requests?: ShiftRequest[] }>('/api/portal/shifts/mine')
      .then((data) => {
        setSchedule(data.schedule || [])
        setPatterns(data.patterns || [])
        setRequests(data.requests || [])
        if (data.schedule?.[0]) setDay(data.schedule[0].day)
      })
      .catch((reasonValue: unknown) => notice.setError(messageFrom(reasonValue)))
  }

  useEffect(() => {
    setPageHeader('Shifts')
    load()
  }, [setPageHeader])

  const current = schedule.find((row) => row.day === day)

  async function submit(event: FormEvent) {
    event.preventDefault()
    notice.clear()
    try {
      await postJson('/api/portal/shifts/mine', {
        day_of_week: day,
        current_shift_name: current?.shift || 'Not Assigned',
        requested_shift_name: requested,
        reason,
      })
      setReason('')
      notice.setSaved('Shift change request submitted. An administrator will review it.')
      load()
    } catch (reasonValue) {
      notice.setError(messageFrom(reasonValue))
    }
  }

  return (
    <div className="grid items-start gap-2 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className={card}>
        <header className="border-b border-gray-100 px-4 py-3"><h2 className="text-sm font-bold text-gray-800">My shift schedule</h2></header>
        {schedule.length === 0 ? <p className="px-4 py-8 text-sm text-gray-500">No shift is assigned yet.</p> : (
          <ul className="divide-y divide-gray-100">
            {schedule.map((row) => (
              <li key={row.day} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="font-semibold text-gray-800">{row.day}</p>
                <p className="text-sm text-gray-600">{row.shift || 'Not assigned'}</p>
                <p className="text-sm text-gray-500">{row.start_time && row.end_time ? `${row.start_time} – ${row.end_time}` : '—'}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="flex flex-col gap-2">
        <Banner notice={notice} />
        <form className={`${card} space-y-3 p-4`} onSubmit={(event) => void submit(event)}>
          <div>
            <h2 className="text-sm font-bold text-gray-800">Request a shift change</h2>
            <p className="mt-1 text-xs text-gray-500">Current shift on {day}: {current?.shift || 'Not assigned'}</p>
          </div>
          <label className={labelClass}>Day
            <select value={day} onChange={(event) => setDay(event.target.value)} className={field}>{days.map((name) => <option key={name}>{name}</option>)}</select>
          </label>
          <label className={labelClass}>Requested shift
            <select value={requested} onChange={(event) => setRequested(event.target.value)} required className={field}>
              <option value="">Choose a shift</option>
              {patterns.map((pattern) => <option key={pattern.name} value={pattern.name}>{pattern.name}</option>)}
            </select>
          </label>
          <label className={labelClass}>Reason
            <textarea value={reason} maxLength={300} rows={3} onChange={(event) => setReason(event.target.value)} className={field} placeholder="Why do you need this change?" />
          </label>
          <button type="submit" className="w-full rounded-xl bg-gray-900 py-2.5 text-sm font-bold text-white">Submit request</button>
        </form>
        <section className={`${card} p-4`}>
          <h2 className="mb-2 text-sm font-bold text-gray-800">Your requests</h2>
          {requests.length === 0 ? <p className="text-sm text-gray-500">No requests yet.</p> : (
            <ul className="flex flex-col gap-2">
              {requests.map((row) => (
                <li key={`${row.created_at}-${row.requested_shift}`} className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                  <p className="text-sm font-semibold text-gray-800">{row.day}</p>
                  <p className="text-xs text-gray-600">{row.current_shift || 'Not assigned'} → {row.requested_shift}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <Pill className={approvalClass(row.status)}>{pretty(row.status)}</Pill>
                    {row.response ? <span className="text-xs text-gray-500">{row.response}</span> : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}

export function MyProxyPage() {
  const setPageHeader = useSetPageHeader()
  const notice = useNotice()
  const [lectures, setLectures] = useState<{ id: number; day: string; start_time: string; end_time: string; subject: string }[]>([])
  const [proxies, setProxies] = useState<{ id: number; name: string }[]>([])
  const [logs, setLogs] = useState<{ date: string; day: string; subject: string; start_time: string; end_time: string; proxy: string; status: string; approval: string }[]>([])
  const [lectureId, setLectureId] = useState('')
  const [proxyId, setProxyId] = useState('')
  const [date, setDate] = useState(todayInput)

  function load() {
    void apiRequest<{ lectures?: typeof lectures; proxies?: typeof proxies; logs?: typeof logs }>('/api/portal/proxy/mine')
      .then((data) => {
        setLectures(data.lectures || [])
        setProxies(data.proxies || [])
        setLogs(data.logs || [])
      })
      .catch((reason: unknown) => notice.setError(messageFrom(reason)))
  }

  useEffect(() => {
    setPageHeader('Proxy Requests')
    load()
  }, [setPageHeader])

  async function submit(event: FormEvent) {
    event.preventDefault()
    notice.clear()
    try {
      await postJson('/api/portal/proxy/mine', {
        timetable_id: Number(lectureId),
        proxy_faculty_id: proxyId ? Number(proxyId) : null,
        absence_date: date,
      })
      setLectureId('')
      setProxyId('')
      setDate(todayInput())
      notice.setSaved('Proxy request submitted for approval.')
      load()
    } catch (reason) {
      notice.setError(messageFrom(reason))
    }
  }

  const pending = logs.filter((log) => !log.approval || log.approval.toUpperCase() === 'PENDING').length
  const approved = logs.filter((log) => (log.approval || '').toUpperCase() === 'APPROVED').length
  const chosen = lectures.find((lecture) => String(lecture.id) === lectureId)

  return (
    <div className="grid items-start gap-2 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
      <form className={`${card} space-y-3 p-4`} onSubmit={(event) => void submit(event)}>
        <div>
          <h2 className="text-sm font-bold text-gray-800">Ask for a substitute</h2>
          <p className="mt-1 text-xs text-gray-500">Pick the class and the day you cannot take it. An administrator assigns or approves the proxy.</p>
        </div>
        <Banner notice={notice} />
        <label className={labelClass}>Class
          <select required value={lectureId} onChange={(event) => setLectureId(event.target.value)} className={field}>
            <option value="">Choose a scheduled class</option>
            {lectures.map((lecture) => <option key={lecture.id} value={lecture.id}>{lecture.day} · {lecture.start_time}{lecture.end_time ? `–${lecture.end_time}` : ''} · {lecture.subject}</option>)}
          </select>
        </label>
        {chosen ? <p className="text-xs text-gray-500">{chosen.day} · {chosen.subject}</p> : null}
        <label className={labelClass}>Date you will be away
          <input type="date" required value={date} onChange={(event) => setDate(event.target.value)} className={field} />
        </label>
        <label className={labelClass}>Preferred substitute
          <select value={proxyId} onChange={(event) => setProxyId(event.target.value)} className={field}>
            <option value="">Any available faculty</option>
            {proxies.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select>
        </label>
        <p className="text-xs text-gray-400">Leave this open if you do not have someone in mind.</p>
        <button type="submit" className="w-full rounded-xl bg-gray-900 py-2.5 text-sm font-bold text-white">Submit request</button>
      </form>
      <section className="flex flex-col gap-2">
        <div className="grid grid-cols-3 gap-2">
          <div className={`${card} px-3 py-2`}><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Requests</p><p className="text-lg font-bold text-gray-800">{logs.length}</p></div>
          <div className={`${card} px-3 py-2`}><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Waiting</p><p className="text-lg font-bold text-amber-700">{pending}</p></div>
          <div className={`${card} px-3 py-2`}><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Approved</p><p className="text-lg font-bold text-emerald-700">{approved}</p></div>
        </div>
        {logs.length === 0 ? (
          <section className={`${card} px-4 py-10 text-center`}>
            <p className="text-sm font-semibold text-gray-800">No proxy requests yet</p>
            <p className="mt-1 text-xs text-gray-500">When you submit one, its status will show here.</p>
          </section>
        ) : logs.map((log, index) => (
          <article key={`${log.date}-${log.subject}-${log.start_time}-${index}`} className={`${card} p-4`}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="font-bold text-gray-800">{log.subject}</p>
                <p className="mt-0.5 text-sm text-gray-500">{log.day ? `${log.day} · ` : ''}{log.date} · {log.start_time}{log.end_time ? ` – ${log.end_time}` : ''}</p>
                <p className="mt-1 text-sm text-gray-700">{log.proxy || 'Substitute not chosen yet'}</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Pill className="border-gray-200 bg-gray-50 text-gray-600">{pretty(log.status)}</Pill>
                <Pill className={approvalClass(log.approval)}>{pretty(log.approval)}</Pill>
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}

export function MyClassesPage() {
  const setPageHeader = useSetPageHeader()
  const [classes, setClasses] = useState<{ class_name: string; division_name: string; course_name: string; subject: string; student_count: number; students: { name: string; username: string }[] }[]>([])
  const [error, setError] = useState('')
  const [open, setOpen] = useState('')
  useEffect(() => {
    setPageHeader('My Classes')
    void apiRequest<{ classes?: typeof classes }>('/api/portal/classes/roster')
      .then((data) => setClasses(data.classes || []))
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  return (
    <div className="flex flex-col gap-2">
      <FailureNotice message={error} />
      {classes.length === 0 && !error ? <p className={`${card} px-4 py-10 text-center text-sm text-gray-500`}>No classes are assigned.</p> : null}
      {classes.map((item) => {
        const key = `${item.class_name}-${item.division_name}-${item.subject}`
        const expanded = open === key
        return (
          <section key={key} className={card}>
            <button type="button" aria-expanded={expanded} className="flex w-full flex-col gap-2 px-4 py-3 text-left sm:flex-row sm:items-center sm:justify-between" onClick={() => setOpen(expanded ? '' : key)}>
              <span className="min-w-0">
                <span className="block font-bold text-gray-800">{item.subject}</span>
                <span className="text-sm text-gray-500">{item.course_name} · {item.class_name} · Div {item.division_name}</span>
              </span>
              <span className="w-fit rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-bold text-gray-700">{item.student_count} students</span>
            </button>
            {expanded ? (
              <ul className="divide-y divide-gray-100 border-t border-gray-100">
                {item.students.length === 0 ? <li className="px-4 py-4 text-sm text-gray-500">No students in this class.</li> : item.students.map((student) => (
                  <li key={`${key}-${student.username}-${student.name}`} className="flex flex-col gap-0.5 px-4 py-3 text-sm sm:flex-row sm:justify-between"><span className="font-medium text-gray-800">{student.name}</span><span className="text-gray-500">{student.username}</span></li>
                ))}
              </ul>
            ) : null}
          </section>
        )
      })}
    </div>
  )
}

export function TeacherAttendancePage() {
  const setPageHeader = useSetPageHeader()
  const [today, setToday] = useState('')
  const [marked, setMarked] = useState(0)
  const [lectures, setLectures] = useState<{ id: number; day: string; start_time: string; end_time: string; subject: string; class_name: string; division_name: string; marked_today: boolean }[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Attendance')
    void apiRequest<{ today?: string; marked_today_count?: number; lectures?: typeof lectures }>('/api/portal/attendance/lectures')
      .then((data) => {
        setToday(data.today || '')
        setMarked(data.marked_today_count || 0)
        setLectures(data.lectures || [])
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])
  const weekday = weekdayFromStamp(today)
  const todays = lectures.filter((lecture) => lecture.day === weekday)
  const later = lectures.filter((lecture) => lecture.day !== weekday)
  const groups = [
    { title: "Today's classes", rows: todays },
    { title: 'Other days', rows: later },
  ].filter((group) => group.rows.length > 0)
  return (
    <div className="flex flex-col gap-2">
      <div className={`${card} flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between`}>
        <div><h2 className="text-sm font-bold text-gray-800">Your lectures</h2><p className="text-xs text-gray-500">{today || 'Mark the class you are teaching'}</p></div>
        <span className="w-fit rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">{marked} marked today</span>
      </div>
      <FailureNotice message={error} />
      {lectures.length === 0 && !error ? <p className={`${card} px-4 py-10 text-center text-sm text-gray-500`}>No lectures are assigned.</p> : null}
      {groups.map((group) => (
        <section key={group.title} className="flex flex-col gap-2">
          <h3 className="text-[11px] font-bold tracking-wide text-gray-400 uppercase">{group.title}</h3>
          {group.rows.map((lecture) => (
            <article key={lecture.id} className={`${card} flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between`}>
              <div className="min-w-0">
                <p className="font-bold text-gray-800">{lecture.subject}</p>
                <p className="text-sm text-gray-500">{lecture.day} · {lecture.start_time} – {lecture.end_time}</p>
                <p className="text-xs text-gray-400">{lecture.class_name}{lecture.division_name ? ` · Div ${lecture.division_name}` : ''}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:flex">
                <Link to={`/my-attendance/mark/${lecture.id}`} className="rounded-xl bg-gray-900 px-3 py-2.5 text-center text-xs font-bold text-white">{lecture.marked_today ? 'Update' : 'Mark'}</Link>
                <Link to={`/my-attendance/history/${lecture.id}`} className="rounded-xl border border-gray-200 px-3 py-2.5 text-center text-xs font-bold text-gray-700">History</Link>
              </div>
            </article>
          ))}
        </section>
      ))}
    </div>
  )
}

export function MarkAttendancePage() {
  const { timetableId = '' } = useParams()
  const setPageHeader = useSetPageHeader()
  const notice = useNotice()
  const [heading, setHeading] = useState('')
  const [date, setDate] = useState('')
  const [already, setAlready] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [reason, setReason] = useState('faculty_absent')
  const [note, setNote] = useState('')
  const [students, setStudents] = useState<{ id: number; name: string; roll_number: string; status: string; remarks: string }[]>([])
  const [reloads, setReloads] = useState(0)
  const [deviceCode, setDeviceCode] = useState<{ code: string; expires: string } | null>(null)
  const syllabusOn = useCapability('syllabus')
  const [units, setUnits] = useState<{ id: number; unit_no: number; title: string }[]>([])
  const [unitId, setUnitId] = useState('')
  const [topic, setTopic] = useState('')
  const [taughtHours, setTaughtHours] = useState('1')
  useEffect(() => {
    setPageHeader('Mark attendance')
    void apiRequest<{ date?: string; already_marked?: boolean; cancelled?: boolean; lecture?: { subject: string; class_name: string; division_name: string }; students?: typeof students; syllabus?: { units?: { id?: number; unit_no?: number; title?: string }[]; lesson?: { unit_id?: number; topic?: string; hours?: number } | null } }>(`/api/portal/attendance/mark/${timetableId}`)
      .then((data) => {
        setDate(data.date || '')
        setAlready(data.already_marked === true)
        setCancelled(data.cancelled === true)
        setHeading(`${data.lecture?.subject || ''} · ${data.lecture?.class_name || ''}${data.lecture?.division_name ? ` Div ${data.lecture.division_name}` : ''}`)
        setStudents(data.students || [])
        const nextUnits = (data.syllabus?.units || []).map((unit) => ({
          id: Number(unit.id) || 0,
          unit_no: Number(unit.unit_no) || 0,
          title: unit.title || '',
        })).filter((unit) => unit.id > 0)
        setUnits(nextUnits)
        const lesson = data.syllabus?.lesson
        setUnitId(lesson?.unit_id ? String(lesson.unit_id) : '')
        setTopic(lesson?.topic || '')
        setTaughtHours(lesson?.hours ? String(lesson.hours) : '1')
      })
      .catch((reason: unknown) => notice.setError(messageFrom(reason)))
  }, [setPageHeader, timetableId, reloads])

  function setStatus(id: number, status: string) {
    setStudents((current) => current.map((student) => (student.id === id ? { ...student, status } : student)))
  }

  async function cancelLecture() {
    notice.clear()
    try {
      await postJson(`/api/portal/attendance/cancel/${timetableId}`, { date, reason, note })
      notice.setSaved('The lecture is recorded as cancelled.')
      setReloads((count) => count + 1)
    } catch (cause) {
      notice.setError(messageFrom(cause))
    }
  }

  async function undoCancel() {
    notice.clear()
    try {
      await postJson(`/api/portal/attendance/uncancel/${timetableId}`, { date })
      notice.setSaved('The cancellation has been undone.')
      setReloads((count) => count + 1)
    } catch (cause) {
      notice.setError(messageFrom(cause))
    }
  }

  async function openForDevice() {
    notice.clear()
    try {
      const data = await postJson<{ session_code?: string; expires_at?: string }>(`/api/portal/attendance/open/${timetableId}`, { date })
      setDeviceCode({ code: displayValue(data.session_code, 16), expires: displayValue(data.expires_at, 19) })
    } catch (cause) {
      notice.setError(messageFrom(cause))
    }
  }

  async function closeForDevice() {
    notice.clear()
    try {
      await postJson(`/api/portal/attendance/close/${timetableId}`, { date })
      setDeviceCode(null)
      notice.setSaved('The attendance device can no longer mark this lecture.')
    } catch (cause) {
      notice.setError(messageFrom(cause))
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    notice.clear()
    try {
      const body: { attendance_date: string; marks: { student_id: number; status: string; remarks: string }[]; lesson?: { unit_id: number; topic: string; hours: number } } = {
        attendance_date: date,
        marks: students.filter((student) => student.status).map((student) => ({
          student_id: student.id,
          status: student.status,
          remarks: student.remarks,
        })),
      }
      if (syllabusOn && (unitId || topic.trim())) {
        if (!unitId || !topic.trim()) {
          notice.setError('Choose a unit and a topic, or leave both empty.')
          return
        }
        body.lesson = { unit_id: Number(unitId), topic: topic.trim(), hours: Number(taughtHours) }
      }
      await postJson(`/api/portal/attendance/mark/${timetableId}`, body)
      notice.setSaved('Attendance saved.')
    } catch (reason) {
      notice.setError(messageFrom(reason))
    }
  }

  function setRemark(id: number, remarks: string) {
    setStudents((current) => current.map((item) => item.id === id ? { ...item, remarks } : item))
  }

  return (
    <form className="flex flex-col gap-2 pb-16" onSubmit={(event) => void save(event)}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0"><h2 className="text-sm font-bold text-gray-800">{heading || 'Mark attendance'}</h2><p className="text-xs text-gray-500">{date}{already ? ' · Already marked' : ''}{cancelled ? ' · Cancelled' : ''}</p></div>
        <Link to="/my-attendance" className="w-fit text-xs font-bold text-gray-700">Back to lectures</Link>
      </div>
      <Banner notice={notice} />
      <WarningNotice message={cancelled ? "This lecture is recorded as cancelled. It is not counted in anyone's attendance." : ''} />
      {cancelled ? (
        <div className="flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 sm:flex-row sm:items-center sm:justify-between">
          <span>This lecture is recorded as cancelled. It is not counted in anyone's attendance.</span>
          <button type="button" onClick={() => void undoCancel()} className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-bold text-amber-800">Undo cancellation</button>
        </div>
      ) : !already ? (
        <div className={`${card} grid gap-2 p-4 sm:grid-cols-[180px_1fr_auto] sm:items-end`}>
          <label className={labelClass}>Did not happen
            <select value={reason} onChange={(event) => setReason(event.target.value)} className={field}>
              <option value="faculty_absent">Faculty absent</option>
              <option value="institution">Institution closed</option>
              <option value="exam">Examination</option>
              <option value="other">Other</option>
            </select>
          </label>
          <input value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} placeholder="Note (optional)" className={field} />
          <button type="button" onClick={() => void cancelLecture()} className="rounded-xl border border-gray-200 px-3 py-2.5 text-xs font-bold text-gray-700">Cancel lecture</button>
        </div>
      ) : null}
      {!cancelled ? (
        <div className={`${card} flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between`}>
          {deviceCode ? (
            <p className="text-sm text-gray-700">Device code <span className="rounded bg-gray-900 px-2 py-0.5 font-mono text-base font-bold tracking-widest text-white">{deviceCode.code}</span> <span className="block text-xs text-gray-500 sm:inline">valid until {deviceCode.expires} UTC</span></p>
          ) : (
            <p className="text-xs text-gray-600">Open this lecture if a face-attendance device should mark only this class.</p>
          )}
          {deviceCode ? (
            <button type="button" onClick={() => void closeForDevice()} className="rounded-xl border border-gray-200 px-3 py-2 text-xs font-bold text-gray-700">Close for device</button>
          ) : (
            <button type="button" onClick={() => void openForDevice()} className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-bold text-gray-800">Open for device</button>
          )}
        </div>
      ) : null}
      {syllabusOn && !cancelled ? (
        <div className={`${card} grid gap-2 p-4 sm:grid-cols-3`}>
          <label className={labelClass}>Unit
            <select value={unitId} onChange={(event) => setUnitId(event.target.value)} className={field}>
              <option value="">{units.length ? 'Not recording a topic' : 'No units for this subject'}</option>
              {units.map((unit) => <option key={unit.id} value={unit.id}>{unit.unit_no}. {unit.title}</option>)}
            </select>
          </label>
          <label className={labelClass}>Topic
            <input value={topic} maxLength={200} onChange={(event) => setTopic(event.target.value)} placeholder="What was taught" className={field} />
          </label>
          <label className={labelClass}>Hours
            <select value={taughtHours} onChange={(event) => setTaughtHours(event.target.value)} className={field}>
              {['0.5', '1', '1.5', '2', '2.5', '3'].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      ) : null}
      <div className="flex flex-col gap-2 md:hidden">
        {students.map((student) => (
          <article key={student.id} className={`${card} p-3`}>
            <p className="font-semibold text-gray-800">{student.name}</p>
            <p className="text-xs text-gray-500">{student.roll_number || 'No roll number'}</p>
            <StatusChoice value={student.status} disabled={cancelled} onChange={(status) => setStatus(student.id, status)} />
            <input aria-label={`Remarks for ${student.name}`} value={student.remarks} maxLength={200} disabled={cancelled} onChange={(event) => setRemark(student.id, event.target.value)} placeholder="Remarks" className={`${field} mt-2`} />
          </article>
        ))}
      </div>
      <div className={`${card} hidden overflow-auto md:block`}>
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-4 py-3">Roll</th><th className="px-4 py-3">Student</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Remarks</th></tr></thead>
          <tbody className="divide-y divide-gray-100">
            {students.map((student) => (
              <tr key={student.id}>
                <td className="px-4 py-3">{student.roll_number}</td>
                <td className="px-4 py-3 font-medium">{student.name}</td>
                <td className="px-4 py-3"><StatusChoice value={student.status} disabled={cancelled} onChange={(status) => setStatus(student.id, status)} /></td>
                <td className="px-4 py-3"><input aria-label={`Remarks for ${student.name}`} value={student.remarks} maxLength={200} disabled={cancelled} onChange={(event) => setRemark(student.id, event.target.value)} className="w-full rounded-lg border border-gray-200 px-2 py-1.5" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="submit" disabled={cancelled} className="sticky bottom-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50">Save attendance</button>
    </form>
  )
}

function StatusChoice({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (value: string) => void }) {
  const options = [
    { name: 'Present', active: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
    { name: 'Late', active: 'border-amber-200 bg-amber-50 text-amber-700' },
    { name: 'Absent', active: 'border-rose-200 bg-rose-50 text-rose-700' },
  ]
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {options.map((option) => (
        <button key={option.name} type="button" disabled={disabled} onClick={() => onChange(value === option.name ? '' : option.name)} className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold disabled:opacity-50 ${value === option.name ? option.active : 'border-gray-200 text-gray-500'}`}>{option.name}</button>
      ))}
    </div>
  )
}

type HistoryRow = { date: string; status: string; cancel_reason: string; total: number; present: number; late: number; absent: number }
type RosterFigures = {
  student_id: number; name: string; roll_number: string
  held: number; countable: number; attended: number; present: number; late: number; absent: number
  excused: number; not_marked: number; percentage: number | null
}

const SESSION_LABELS: Record<string, string> = { held: 'Held', cancelled: 'Cancelled', not_marked: 'Not marked' }
const CANCEL_LABELS: Record<string, string> = { faculty_absent: 'teacher absent', institution: 'institution', exam: 'exam', other: 'other', calendar: 'academic calendar' }

function percentLabel(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : `${value.toFixed(2)}%`
}

function sessionLabel(row: HistoryRow) {
  const label = SESSION_LABELS[row.status] || row.status
  return row.status === 'cancelled' && row.cancel_reason ? `${label} (${CANCEL_LABELS[row.cancel_reason] || row.cancel_reason})` : label
}

export function AttendanceHistoryPage() {
  const { timetableId = '' } = useParams()
  const setPageHeader = useSetPageHeader()
  const [heading, setHeading] = useState('')
  const [rows, setRows] = useState<HistoryRow[]>([])
  const [students, setStudents] = useState<RosterFigures[]>([])
  const [threshold, setThreshold] = useState<number | null>(null)
  const [from, setFrom] = useState(todayInput)
  const [to, setTo] = useState(todayInput)
  const [range, setRange] = useState(() => ({ from: todayInput(), to: todayInput() }))
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Attendance history')
    const query = new URLSearchParams()
    if (range.from) query.set('from', range.from)
    if (range.to) query.set('to', range.to)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    void apiRequest<{ subject?: string; class_name?: string; division_name?: string; history?: HistoryRow[]; students?: RosterFigures[]; threshold?: number | null }>(`/api/portal/attendance/history/${timetableId}${suffix}`)
      .then((data) => {
        setHeading(`${data.subject || ''} · ${data.class_name || ''}${data.division_name ? ` Div ${data.division_name}` : ''}`)
        setRows(data.history || [])
        setStudents(data.students || [])
        setThreshold(data.threshold ?? null)
        setError('')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader, timetableId, range])
  const applyRange = (event: FormEvent) => {
    event.preventDefault()
    setRange({ from, to })
  }
  return (
    <div className="flex flex-col gap-2">
      <section className={card}>
        <header className="flex flex-col gap-2 border-b border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-bold text-gray-800">{heading || 'Lecture history'}</h2>
          <Link to="/my-attendance" className="w-fit text-xs font-bold text-gray-700">Back to lectures</Link>
        </header>
        <FailureNotice message={error} />
        {rows.length === 0 ? <p className="px-4 py-8 text-sm text-gray-500">No lecture has been recorded.</p> : (
          <>
            <ul className="divide-y divide-gray-100 md:hidden">
              {rows.map((row) => (
                <li key={row.date} className={`px-4 py-3 ${row.status === 'held' ? '' : 'text-gray-400'}`}>
                  <p className="font-semibold">{row.date}</p>
                  <p className="text-sm">{sessionLabel(row)}</p>
                  <p className="mt-1 text-xs">Present {row.present} · Late {row.late} · Absent {row.absent} · Marked {row.total}</p>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-auto md:block">
              <table className="w-full text-left text-sm">
                <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-4 py-3">Date</th><th className="px-4 py-3">Lecture</th><th className="px-4 py-3">Present</th><th className="px-4 py-3">Late</th><th className="px-4 py-3">Absent</th><th className="px-4 py-3">Marked</th></tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((row) => (
                    <tr key={row.date} className={row.status === 'held' ? '' : 'text-gray-400'}>
                      <td className="px-4 py-3">{row.date}</td><td className="px-4 py-3">{sessionLabel(row)}</td>
                      <td className="px-4 py-3">{row.present}</td><td className="px-4 py-3">{row.late}</td><td className="px-4 py-3">{row.absent}</td><td className="px-4 py-3">{row.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      <section className={card}>
        <header className="flex flex-col gap-3 border-b border-gray-100 px-4 py-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Students</h2>
            <p className="text-xs text-gray-500">Figures for the dates above, across every lecture of yours the student is in. A dash means nothing countable yet.</p>
          </div>
          <form onSubmit={applyRange} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <label className={labelClass}>From
              <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className={field} />
            </label>
            <label className={labelClass}>To
              <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className={field} />
            </label>
            <button type="submit" className="rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white">Apply</button>
          </form>
        </header>
        {students.length === 0 ? <p className="px-4 py-8 text-sm text-gray-500">No student is in this lecture's roster.</p> : (
          <>
            <ul className="divide-y divide-gray-100 md:hidden">
              {students.map((student) => (
                <li key={student.student_id} className="px-4 py-3">
                  <p className="font-semibold text-gray-800">{student.name}</p>
                  <p className="text-xs text-gray-500">{student.roll_number || 'No roll number'}</p>
                  <p className="mt-1 text-xs text-gray-600">Held {student.held} · Attended {student.attended} · Absent {student.absent} · Excused {student.excused} · Not marked {student.not_marked}</p>
                  <p className={`mt-1 text-sm font-bold ${student.percentage !== null && threshold !== null && student.percentage < threshold ? 'text-red-600' : 'text-gray-800'}`}>{percentLabel(student.percentage)}</p>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-auto md:block">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-4 py-3">Roll</th><th className="px-4 py-3">Student</th><th className="px-4 py-3">Held</th><th className="px-4 py-3">Attended</th><th className="px-4 py-3">Absent</th><th className="px-4 py-3">Excused</th><th className="px-4 py-3">Not marked</th><th className="px-4 py-3">Percentage</th></tr></thead>
                <tbody className="divide-y divide-gray-100">
                  {students.map((student) => (
                    <tr key={student.student_id}>
                      <td className="px-4 py-3">{student.roll_number}</td><td className="px-4 py-3 font-semibold text-gray-800">{student.name}</td>
                      <td className="px-4 py-3">{student.held}</td><td className="px-4 py-3">{student.attended}</td><td className="px-4 py-3">{student.absent}</td>
                      <td className="px-4 py-3">{student.excused}</td><td className="px-4 py-3">{student.not_marked}</td>
                      <td className={`px-4 py-3 font-bold ${student.percentage !== null && threshold !== null && student.percentage < threshold ? 'text-red-600' : 'text-gray-800'}`}>{percentLabel(student.percentage)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
