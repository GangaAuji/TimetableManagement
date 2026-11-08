import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'

const field = 'mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:bg-white'
const card = 'rounded-2xl border border-gray-100 bg-white shadow-sm'
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
      {notice.error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{notice.error}</p> : null}
      {notice.saved ? <p className="rounded-r-lg border-l-4 border-emerald-500 bg-emerald-50 p-3 text-sm text-emerald-700">{notice.saved}</p> : null}
    </>
  )
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
    <div className="flex flex-col gap-2">
      <Banner notice={notice} />
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void save() }}>
        {rows.map((row, index) => (
          <section key={row.day} className={`${card} p-5`}>
            <label className="flex items-center gap-2 text-sm font-bold text-gray-800">
              <input type="checkbox" checked={row.available} onChange={(event) => update(index, { available: event.target.checked })} className="h-4 w-4 accent-indigo-600" />
              {row.day}
            </label>
            {row.available ? (
              <div className="mt-3 space-y-2">
                {row.slots.map((slot, slotIndex) => (
                  <div key={`${row.day}-${slotIndex}`} className="grid gap-2 sm:grid-cols-3">
                    <input type="time" value={slot.start} onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, start: event.target.value } : item) })} className={field} />
                    <input type="time" value={slot.end} onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, end: event.target.value } : item) })} className={field} />
                    <input value={slot.notes} maxLength={200} placeholder="Notes" onChange={(event) => update(index, { slots: row.slots.map((item, itemIndex) => itemIndex === slotIndex ? { ...item, notes: event.target.value } : item) })} className={field} />
                  </div>
                ))}
                <button type="button" className="text-xs font-bold text-indigo-600" onClick={() => update(index, { slots: [...row.slots, { start: '', end: '', notes: '' }] })}>Add slot</button>
              </div>
            ) : <p className="mt-2 text-xs text-gray-500">Not available</p>}
          </section>
        ))}
        <button type="submit" className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-bold text-white">Save availability</button>
      </form>
    </div>
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
    <div className="grid gap-2 lg:grid-cols-5">
      <section className={`${card} overflow-hidden lg:col-span-3`}>
        <header className="border-b border-gray-100 px-6 py-4"><h2 className="text-lg font-bold text-gray-800">My shift schedule</h2></header>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Day</th><th className="px-6 py-3">Shift</th><th className="px-6 py-3">Time</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {schedule.length === 0 ? <tr><td colSpan={3} className="px-6 py-8 text-gray-500">No shift is assigned yet.</td></tr> : schedule.map((row) => (
              <tr key={row.day}><td className="px-6 py-3 font-bold text-gray-800">{row.day}</td><td className="px-6 py-3">{row.shift || 'Not assigned'}</td><td className="px-6 py-3 text-gray-500">{row.start_time && row.end_time ? `${row.start_time} - ${row.end_time}` : '-'}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      <div className="space-y-4 lg:col-span-2">
        <Banner notice={notice} />
        <form className={`${card} space-y-3 p-5`} onSubmit={(event) => void submit(event)}>
          <h2 className="text-lg font-bold text-gray-800">Request a shift change</h2>
          <label className="block text-xs font-semibold text-gray-500 uppercase">Day
            <select value={day} onChange={(event) => setDay(event.target.value)} className={field}>{days.map((name) => <option key={name}>{name}</option>)}</select>
          </label>
          <p className="text-xs text-gray-500">Current: {current?.shift || 'Not assigned'}</p>
          <label className="block text-xs font-semibold text-gray-500 uppercase">Requested shift
            <select value={requested} onChange={(event) => setRequested(event.target.value)} required className={field}>
              <option value="">Choose a shift</option>
              {patterns.map((pattern) => <option key={pattern.name} value={pattern.name}>{pattern.name}</option>)}
            </select>
          </label>
          <label className="block text-xs font-semibold text-gray-500 uppercase">Reason
            <textarea value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} className={field} />
          </label>
          <button type="submit" className="w-full rounded-xl bg-gray-900 py-2 text-sm font-bold text-white">Submit request</button>
        </form>
        <section className={`${card} p-5`}>
          <h2 className="mb-3 text-sm font-bold text-gray-800">Requests</h2>
          {requests.length === 0 ? <p className="text-sm text-gray-500">No requests yet.</p> : requests.map((row) => (
            <div key={`${row.created_at}-${row.requested_shift}`} className="border-t border-gray-100 py-3 text-sm">
              <p className="font-semibold text-gray-800">{row.day}: {row.current_shift || 'Not assigned'} → {row.requested_shift}</p>
              <p className="text-xs text-gray-500">{row.status}{row.response ? ` · ${row.response}` : ''}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}

export function MyProxyPage() {
  const setPageHeader = useSetPageHeader()
  const notice = useNotice()
  const [lectures, setLectures] = useState<{ id: number; day: string; start_time: string; subject: string }[]>([])
  const [proxies, setProxies] = useState<{ id: number; name: string }[]>([])
  const [logs, setLogs] = useState<{ date: string; subject: string; start_time: string; end_time: string; proxy: string; status: string; approval: string }[]>([])
  const [lectureId, setLectureId] = useState('')
  const [proxyId, setProxyId] = useState('')
  const [date, setDate] = useState('')

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
      setDate('')
      notice.setSaved('Proxy request submitted for approval.')
      load()
    } catch (reason) {
      notice.setError(messageFrom(reason))
    }
  }

  return (
    <div className="grid gap-2 lg:grid-cols-5">
      <form className={`${card} space-y-4 p-6 lg:col-span-2`} onSubmit={(event) => void submit(event)}>
        <h2 className="text-lg font-bold text-gray-800">Request a proxy</h2>
        <Banner notice={notice} />
        <label className="block text-xs font-semibold text-gray-500 uppercase">Lecture
          <select required value={lectureId} onChange={(event) => setLectureId(event.target.value)} className={field}>
            <option value="">Choose a scheduled class</option>
            {lectures.map((lecture) => <option key={lecture.id} value={lecture.id}>{lecture.day} · {lecture.start_time} · {lecture.subject}</option>)}
          </select>
        </label>
        <label className="block text-xs font-semibold text-gray-500 uppercase">Date
          <input type="date" required value={date} onChange={(event) => setDate(event.target.value)} className={field} />
        </label>
        <label className="block text-xs font-semibold text-gray-500 uppercase">Proxy faculty
          <select value={proxyId} onChange={(event) => setProxyId(event.target.value)} className={field}>
            <option value="">Any available faculty</option>
            {proxies.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select>
        </label>
        <button type="submit" className="w-full rounded-xl bg-gray-900 py-3 text-sm font-bold text-white">Submit request</button>
      </form>
      <section className={`${card} p-6 lg:col-span-3`}>
        <h2 className="mb-4 text-lg font-bold text-gray-800">My proxy requests</h2>
        {logs.length === 0 ? <p className="text-sm text-gray-500">You have not submitted any proxy requests yet.</p> : logs.map((log) => (
          <article key={`${log.date}-${log.subject}-${log.start_time}`} className="border-t border-gray-100 py-4">
            <p className="font-bold text-gray-800">{log.subject}</p>
            <p className="text-sm text-gray-500">{log.date} · {log.start_time} - {log.end_time}</p>
            <p className="mt-1 text-sm text-gray-700">{log.proxy || 'Not assigned'} · {log.status}{log.approval ? ` · ${log.approval}` : ''}</p>
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
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {classes.length === 0 && !error ? <p className="text-sm text-gray-500">No classes are assigned.</p> : null}
      {classes.map((item) => {
        const key = `${item.class_name}-${item.division_name}-${item.subject}`
        return (
          <section key={key} className={card}>
            <button type="button" className="flex w-full items-center justify-between px-6 py-4 text-left" onClick={() => setOpen(open === key ? '' : key)}>
              <span>
                <span className="block font-bold text-gray-800">{item.subject}</span>
                <span className="text-sm text-gray-500">{item.course_name} · {item.class_name} · Div {item.division_name}</span>
              </span>
              <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">{item.student_count} students</span>
            </button>
            {open === key ? (
              <ul className="divide-y divide-gray-50 border-t border-gray-100">
                {item.students.length === 0 ? <li className="px-6 py-4 text-sm text-gray-500">No students in this class.</li> : item.students.map((student) => (
                  <li key={`${key}-${student.username}-${student.name}`} className="flex justify-between px-6 py-3 text-sm"><span className="font-medium text-gray-800">{student.name}</span><span className="text-gray-500">{student.username}</span></li>
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
  return (
    <div className="flex flex-col gap-2">
      <div className={`${card} flex items-center justify-between px-6 py-4`}>
        <div><h2 className="text-lg font-bold text-gray-800">Today's classes</h2><p className="text-xs text-gray-500">{today}</p></div>
        <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">{marked} marked</span>
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {lectures.length === 0 && !error ? <p className="text-sm text-gray-500">No lectures are assigned.</p> : null}
      {lectures.map((lecture) => (
        <article key={lecture.id} className={`${card} flex flex-wrap items-center justify-between gap-3 px-6 py-4`}>
          <div>
            <p className="font-bold text-gray-800">{lecture.subject}</p>
            <p className="text-sm text-gray-500">{lecture.day} · {lecture.start_time} - {lecture.end_time} · {lecture.class_name} Div {lecture.division_name}</p>
          </div>
          <div className="flex gap-2">
            <Link to={`/my-attendance/mark/${lecture.id}`} className="rounded-xl bg-gray-900 px-3 py-2 text-xs font-bold text-white">{lecture.marked_today ? 'Update attendance' : 'Mark attendance'}</Link>
            <Link to={`/my-attendance/history/${lecture.id}`} className="rounded-xl border border-gray-200 px-3 py-2 text-xs font-bold text-gray-600">History</Link>
          </div>
        </article>
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
  useEffect(() => {
    setPageHeader('Mark attendance')
    void apiRequest<{ date?: string; already_marked?: boolean; cancelled?: boolean; lecture?: { subject: string; class_name: string; division_name: string }; students?: typeof students }>(`/api/portal/attendance/mark/${timetableId}`)
      .then((data) => {
        setDate(data.date || '')
        setAlready(data.already_marked === true)
        setCancelled(data.cancelled === true)
        setHeading(`${data.lecture?.subject || ''} · ${data.lecture?.class_name || ''}${data.lecture?.division_name ? ` Div ${data.lecture.division_name}` : ''}`)
        setStudents(data.students || [])
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

  async function save(event: FormEvent) {
    event.preventDefault()
    notice.clear()
    try {
      await postJson(`/api/portal/attendance/mark/${timetableId}`, {
        attendance_date: date,
        marks: students.filter((student) => student.status).map((student) => ({
          student_id: student.id,
          status: student.status,
          remarks: student.remarks,
        })),
      })
      notice.setSaved('Attendance saved.')
    } catch (reason) {
      notice.setError(messageFrom(reason))
    }
  }

  return (
    <form className="flex flex-col gap-2" onSubmit={(event) => void save(event)}>
      <div className="flex items-center justify-between">
        <div><h2 className="text-lg font-bold text-gray-800">{heading}</h2><p className="text-xs text-gray-500">{date}{already ? ' · Already marked' : ''}{cancelled ? ' · Cancelled' : ''}</p></div>
        <Link to="/my-attendance" className="text-xs font-bold text-indigo-600">Back</Link>
      </div>
      <Banner notice={notice} />
      {cancelled ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <span>This lecture is recorded as cancelled. It is not counted in anyone's attendance.</span>
          <button type="button" onClick={() => void undoCancel()} className="rounded-lg border border-amber-300 px-3 py-1 text-xs font-bold text-amber-800">Undo cancellation</button>
        </div>
      ) : !already ? (
        <div className={`${card} flex flex-wrap items-end gap-2 px-4 py-3`}>
          <label className="flex flex-col text-xs text-gray-600">Lecture did not happen?
            <select value={reason} onChange={(event) => setReason(event.target.value)} className="mt-1 rounded-lg border border-gray-200 px-2 py-1 text-sm">
              <option value="faculty_absent">Faculty absent</option>
              <option value="institution">Institution closed</option>
              <option value="exam">Examination</option>
              <option value="other">Other</option>
            </select>
          </label>
          <input value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} placeholder="Note (optional)" className="min-w-48 flex-1 rounded-lg border border-gray-200 px-2 py-1 text-sm" />
          <button type="button" onClick={() => void cancelLecture()} className="rounded-xl border border-gray-200 px-3 py-2 text-xs font-bold text-gray-600">Cancel lecture</button>
        </div>
      ) : null}
      <div className={`${card} overflow-auto`}>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-4 py-3">Roll</th><th className="px-4 py-3">Student</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Remarks</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {students.map((student) => (
              <tr key={student.id}>
                <td className="px-4 py-3">{student.roll_number}</td>
                <td className="px-4 py-3 font-medium">{student.name}</td>
                <td className="px-4 py-3">
                  <select value={student.status} onChange={(event) => setStatus(student.id, event.target.value)} className="rounded-lg border border-gray-200 px-2 py-1">
                    <option value="">Choose</option>
                    <option>Present</option>
                    <option>Late</option>
                    <option>Absent</option>
                  </select>
                </td>
                <td className="px-4 py-3"><input value={student.remarks} maxLength={200} onChange={(event) => setStudents((current) => current.map((item) => item.id === student.id ? { ...item, remarks: event.target.value } : item))} className="w-full rounded-lg border border-gray-200 px-2 py-1" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="submit" disabled={cancelled} className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50">Save attendance</button>
    </form>
  )
}

type HistoryRow = { date: string; status: string; cancel_reason: string; total: number; present: number; late: number; absent: number }
type RosterFigures = {
  student_id: number; name: string; roll_number: string
  held: number; countable: number; attended: number; present: number; late: number; absent: number
  excused: number; not_marked: number; percentage: number | null
}

const SESSION_LABELS: Record<string, string> = { held: 'Held', cancelled: 'Cancelled', not_marked: 'Not marked' }
const CANCEL_LABELS: Record<string, string> = { faculty_absent: 'teacher absent', institution: 'institution', exam: 'exam', other: 'other' }

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
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [range, setRange] = useState({ from: '', to: '' })
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
    <div className="space-y-6">
      <section className={`${card} overflow-hidden`}>
        <header className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="font-bold text-gray-800">{heading}</h2>
          <Link to="/my-attendance" className="text-xs font-bold text-indigo-600">Back</Link>
        </header>
        {error ? <p className="p-4 text-sm text-red-700">{error}</p> : null}
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Date</th><th className="px-6 py-3">Lecture</th><th className="px-6 py-3">Present</th><th className="px-6 py-3">Late</th><th className="px-6 py-3">Absent</th><th className="px-6 py-3">Marked</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {rows.length === 0 ? <tr><td colSpan={6} className="px-6 py-8 text-gray-500">No lecture has been recorded.</td></tr> : rows.map((row) => (
              <tr key={row.date} className={row.status === 'held' ? '' : 'text-gray-400'}>
                <td className="px-6 py-3">{row.date}</td><td className="px-6 py-3">{sessionLabel(row)}</td>
                <td className="px-6 py-3">{row.present}</td><td className="px-6 py-3">{row.late}</td><td className="px-6 py-3">{row.absent}</td><td className="px-6 py-3">{row.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className={`${card} overflow-hidden`}>
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="font-bold text-gray-800">Students</h2>
            <p className="text-xs text-gray-500">Figures for this subject across every lecture of yours the student is in. A dash means nothing countable yet.</p>
          </div>
          <form onSubmit={applyRange} className="flex items-center gap-2 text-xs">
            <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="rounded-lg border border-gray-200 px-2 py-1" aria-label="From date" />
            <span className="text-gray-400">to</span>
            <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="rounded-lg border border-gray-200 px-2 py-1" aria-label="To date" />
            <button type="submit" className="rounded-lg bg-gray-900 px-3 py-1 font-bold text-white">Apply</button>
          </form>
        </header>
        <table className="w-full text-left text-sm">
          <thead className="text-[10px] font-bold tracking-wider text-gray-400 uppercase"><tr><th className="px-6 py-3">Roll</th><th className="px-6 py-3">Student</th><th className="px-6 py-3">Held</th><th className="px-6 py-3">Attended</th><th className="px-6 py-3">Absent</th><th className="px-6 py-3">Excused</th><th className="px-6 py-3">Not marked</th><th className="px-6 py-3">Percentage</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {students.length === 0 ? <tr><td colSpan={8} className="px-6 py-8 text-gray-500">No student is in this lecture's roster.</td></tr> : students.map((student) => (
              <tr key={student.student_id}>
                <td className="px-6 py-3">{student.roll_number}</td><td className="px-6 py-3 font-semibold text-gray-800">{student.name}</td>
                <td className="px-6 py-3">{student.held}</td><td className="px-6 py-3">{student.attended}</td><td className="px-6 py-3">{student.absent}</td>
                <td className="px-6 py-3">{student.excused}</td><td className="px-6 py-3">{student.not_marked}</td>
                <td className={`px-6 py-3 font-bold ${student.percentage !== null && threshold !== null && student.percentage < threshold ? 'text-red-600' : 'text-gray-800'}`}>{percentLabel(student.percentage)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
