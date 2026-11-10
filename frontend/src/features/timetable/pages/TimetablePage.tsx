import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { todayInput } from '../../../shared/dates'
import { FailureNotice, SuccessNotice, WarningNotice } from '../../../shared/components/success-notice'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { sendJson } from '../../academics/api'

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
  if (key === 'subject') return row.lab_batch ? `${row.subject} ${row.lab_batch}` : row.subject
  return row[key as keyof Session]
}
const fieldClass = 'w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20'
const labelClass = 'mb-1.5 ml-1 block text-[10px] font-bold tracking-wide text-gray-500 uppercase'

type Option = { id: number; name: string }
type Session = {
  id: number
  course_id: number
  class_id: number
  division_id: number
  cohort: string
  day: string
  start_time: string
  end_time: string
  subject_id: number
  subject: string
  faculty_id: number | null
  faculty: string
  room_id: number | null
  room: string
  session_type: string
  is_proxy: boolean
  lab_batch_group_id: number | null
  lab_batch: string
}
type ViewMode = 'class' | 'faculty' | 'room'
/** Answer of POST /api/timetable/check for one drop target. */
type SlotCheck = {
  ok: boolean
  errors: { code: string; message: string }[]
  delta: number | null
  violations: { title: string; cost: number; faculty: string; detail: string }[]
}
type PendingMove = { session: Session; day: string; start_time: string; end_time: string; check: SlotCheck | null; checking: boolean }
type UndoStep = { original: Session; createdId: number; label: string }
type SlotDraft = { subject_id: string; faculty_id: string; lab_batch_group_id: string; room_id: string; day: string; start_time: string; end_time: string }
const emptySlot: SlotDraft = { subject_id: '', faculty_id: '', lab_batch_group_id: '', room_id: '', day: 'Monday', start_time: '09:00', end_time: '10:00' }
type OpenSlot = { day: string; start_time: string; end_time: string; reason: string }
type ProxySuggestion = { day: string; time: string; subject: string; primary_faculty: string; replacement_faculty: string }
type Candidate = { candidate_index: number; quality_score: number; assigned_count: number; unassigned_count: number }
type ScoreBreakdown = { clash_risk: number; faculty_fatigue: number; room_overuse: number; student_load_imbalance: number }
/** One soft-rule violation the solver could not avoid (services/timetable/rules.py). */
type Violation = { rule: string; title: string; scope: string; faculty: string; day: string; start_time: string; end_time: string; cost: number; detail: string }
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
  violations: Violation[]
  rule_cost: number
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
  /** Draft version the job wrote (capability `timetable_versions`); null when it wrote live rows. */
  version_id: number | null
}
type TimetableOptions = {
  courses?: { id?: unknown; name?: unknown }[]
  classes?: { id?: unknown; name?: unknown }[]
  divisions?: { id?: unknown; name?: unknown }[]
  sessions?: Record<string, unknown>[]
  lab_batches?: { id?: unknown; name?: unknown }[]
  subjects?: { id?: unknown; name?: unknown; kind?: unknown }[]
  faculty?: { id?: unknown; name?: unknown }[]
  rooms?: { id?: unknown; name?: unknown; kind?: unknown }[]
  can_generate?: boolean
  can_edit?: boolean
}

function options(value: { id?: unknown; name?: unknown; kind?: unknown }[] | undefined, withKind = false): Option[] {
  return (value || [])
    .map((item) => {
      const kind = withKind ? safeText(item.kind, 20) : ''
      return { id: safeCount(item.id), name: `${safeText(item.name, 100)}${kind ? ` (${kind})` : ''}` }
    })
    .filter((item) => item.id > 0)
}

function sessions(rows: Record<string, unknown>[] | undefined): Session[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id),
    course_id: safeCount(row.course_id),
    class_id: safeCount(row.class_id),
    division_id: safeCount(row.division_id),
    cohort: safeText(row.cohort, 300),
    day: safeText(row.day, 12),
    start_time: safeText(row.start_time, 8),
    end_time: safeText(row.end_time, 8),
    subject_id: safeCount(row.subject_id),
    subject: safeText(row.subject, 100),
    faculty_id: safeCount(row.faculty_id) || null,
    faculty: safeText(row.faculty, 100),
    room_id: safeCount(row.room_id) || null,
    room: safeText(row.room, 20),
    session_type: safeText(row.session_type, 20),
    is_proxy: row.is_proxy === true,
    lab_batch_group_id: safeCount(row.lab_batch_group_id) || null,
    lab_batch: safeText(row.lab_batch, 20),
  }))
}

function slotPayload(session: Session, day: string, start: string, end: string) {
  return {
    course_id: session.course_id,
    class_id: session.class_id,
    division_id: session.division_id,
    subject_id: session.subject_id,
    faculty_id: session.faculty_id,
    lab_batch_group_id: session.lab_batch_group_id,
    room_id: session.room_id,
    day,
    start_time: start.slice(0, 5),
    end_time: end.slice(0, 5),
  }
}

function checkFrom(data: Record<string, unknown>): SlotCheck {
  const cost = data.rule_cost && typeof data.rule_cost === 'object' ? (data.rule_cost as Record<string, unknown>) : null
  return {
    ok: data.ok === true,
    errors: ((data.errors as Record<string, unknown>[]) || []).slice(0, 10).map((item) => ({ code: safeText(item.code, 40), message: safeText(item.message, 200) })),
    delta: cost && typeof cost.delta === 'number' ? Math.round(cost.delta) : null,
    violations: cost ? ((cost.violations as Record<string, unknown>[]) || []).slice(0, 20).map((item) => ({
      title: safeText(item.title, 80), cost: safeCount(item.cost), faculty: safeText(item.faculty, 100), detail: safeText(item.detail, 200),
    })) : [],
  }
}

function cellKey(day: string, start: string, end: string) {
  return `${day}|${start}|${end}`
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
    violations: (data.violations || []).slice(0, 60).map((item) => ({
      rule: safeText(item.rule, 40),
      title: safeText(item.title, 60),
      scope: safeText(item.scope, 10),
      faculty: safeText(item.faculty, 100),
      day: safeText(item.day, 12),
      start_time: safeText(item.start_time, 8),
      end_time: safeText(item.end_time, 8),
      cost: safeCount(item.cost),
      detail: safeText(item.detail, 160),
    })),
    rule_cost: safeCount(data.rule_cost),
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
    version_id: safeCount(data.version_id) || null,
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
    cells: columns.map((column) => rows.filter((row) => row.day === day && row.start_time === column.start && row.end_time === column.end)),
  }))
  return { columns, days }
}

function cellLabel(session: Session) {
  return `${session.subject}${session.lab_batch ? ` [${session.lab_batch}]` : ''}${session.faculty ? ` (${session.faculty})` : ''}${session.room ? ` — Room ${session.room}` : ''}`
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
  const [applied, setApplied] = useState({ course: '', classId: '', division: '' })
  const [canGenerate, setCanGenerate] = useState(false)
  const [canEdit, setCanEdit] = useState(false)
  const [labBatches, setLabBatches] = useState<Option[]>([])
  const [subjects, setSubjects] = useState<Option[]>([])
  const [faculty, setFaculty] = useState<Option[]>([])
  const [rooms, setRooms] = useState<Option[]>([])
  const [slot, setSlot] = useState<SlotDraft | null>(null)
  const [removing, setRemoving] = useState<Session | null>(null)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState<'list' | 'grid'>('list')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [exporting, setExporting] = useState(false)
  const [version, setVersion] = useState(0)
  const [mode, setMode] = useState<ViewMode>('class')
  const [person, setPerson] = useState('')
  const [room, setRoom] = useState('')
  const [appliedFocus, setAppliedFocus] = useState<{ mode: ViewMode; id: string }>({ mode: 'class', id: '' })
  const [dragging, setDragging] = useState<Session | null>(null)
  const [cellChecks, setCellChecks] = useState<Record<string, SlotCheck | 'pending'>>({})
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null)
  const [undoStack, setUndoStack] = useState<UndoStep[]>([])
  const classReady = Boolean(applied.course && applied.classId && applied.division && course === applied.course && classId === applied.classId && division === applied.division)
  const focusReady = mode !== 'class' && appliedFocus.mode === mode && Boolean(appliedFocus.id) && appliedFocus.id === (mode === 'faculty' ? person : room)
  const ready = mode === 'class' ? classReady : focusReady
  const grid = useMemo(() => scheduleGrid(rows), [rows])
  const table = useDataTable(rows, sessionColumns, sessionValue)

  useEffect(() => {
    setPageHeader('View Timetable')
  }, [setPageHeader])

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams()
    if (mode === 'class') {
      if (course) params.set('course', course)
      if (classId) params.set('class', classId)
      if (division) params.set('division', division)
    } else if (appliedFocus.mode === mode && appliedFocus.id) {
      params.set(mode, appliedFocus.id)
    }
    const requestKey = `${course}|${classId}|${division}`
    const appliedKey = `${applied.course}|${applied.classId}|${applied.division}`
    void apiRequest<TimetableOptions>(`/api/timetable?${params.toString()}`)
      .then((data) => {
        if (cancelled) return
        setCourses(options(data.courses))
        setClasses(options(data.classes))
        setDivisions(options(data.divisions))
        const viewingClass = mode === 'class' && requestKey === appliedKey && Boolean(course && classId && division)
        const viewingFocus = mode !== 'class' && appliedFocus.mode === mode && Boolean(appliedFocus.id)
        setRows(viewingClass || viewingFocus ? sessions(data.sessions) : [])
        setLabBatches(viewingClass ? options(data.lab_batches) : [])
        setSubjects(viewingClass ? options(data.subjects, true) : [])
        setFaculty(options(data.faculty))
        setRooms(options(data.rooms, true))
        setCanGenerate(data.can_generate === true)
        setCanEdit(data.can_edit === true)
        setError('')
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(messageFrom(reason))
      })
    return () => { cancelled = true }
  }, [applied.classId, applied.course, applied.division, appliedFocus, classId, course, division, mode, version])

  function refresh() {
    setVersion((current) => current + 1)
  }

  /** Pre-check every empty-for-this-session cell once a drag starts, so the grid can shade targets. */
  function startDrag(session: Session) {
    if (!canEdit) return
    setDragging(session)
    setPendingMove(null)
    const targets: { day: string; start: string; end: string }[] = []
    grid.days.forEach((day) => grid.columns.forEach((column) => {
      if (day.day === session.day && column.start === session.start_time && column.end === session.end_time) return
      targets.push({ day: day.day, start: column.start, end: column.end })
    }))
    const initial: Record<string, SlotCheck | 'pending'> = {}
    targets.slice(0, 60).forEach((target) => { initial[cellKey(target.day, target.start, target.end)] = 'pending' })
    setCellChecks(initial)
    targets.slice(0, 60).forEach((target) => {
      void sendJson<Record<string, unknown>>('POST', '/api/timetable/check', { ...slotPayload(session, target.day, target.start, target.end), exclude_id: session.id })
        .then((data) => setCellChecks((current) => (current[cellKey(target.day, target.start, target.end)] === undefined ? current : { ...current, [cellKey(target.day, target.start, target.end)]: checkFrom(data) })))
        .catch(() => setCellChecks((current) => ({ ...current, [cellKey(target.day, target.start, target.end)]: { ok: false, errors: [{ code: 'check_failed', message: 'Could not check this cell.' }], delta: null, violations: [] } })))
    })
  }

  function endDrag() {
    setDragging(null)
    setCellChecks({})
  }

  async function dropOn(day: string, start: string, end: string) {
    const session = dragging
    endDrag()
    if (!session || (session.day === day && session.start_time === start && session.end_time === end)) return
    const known = cellChecks[cellKey(day, start, end)]
    const move: PendingMove = { session, day, start_time: start, end_time: end, check: known && known !== 'pending' ? known : null, checking: !known || known === 'pending' }
    setPendingMove(move)
    if (move.checking) {
      try {
        const data = await sendJson<Record<string, unknown>>('POST', '/api/timetable/check', { ...slotPayload(session, day, start, end), exclude_id: session.id })
        setPendingMove((current) => (current && current.session.id === session.id ? { ...current, check: checkFrom(data), checking: false } : current))
      } catch (reason) {
        setPendingMove(null)
        setError(messageFrom(reason))
      }
    }
  }

  async function confirmMove() {
    if (!pendingMove || !pendingMove.check?.ok) return
    const { session, day, start_time: start, end_time: end } = pendingMove
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const removed = await sendJson<{ outcome?: unknown }>('DELETE', `/api/timetable/slots/${session.id}`)
      const created = await sendJson<{ id?: unknown }>('POST', '/api/timetable/slots', slotPayload(session, day, start, end))
      const createdId = safeCount(created?.id)
      setUndoStack((current) => [...current, { original: session, createdId, label: `${session.subject} ${session.day.slice(0, 3)} ${session.start_time} → ${day.slice(0, 3)} ${start}` }].slice(-20))
      setPendingMove(null)
      setNotice(`Moved ${session.subject} to ${day} ${start}–${end}.${safeText(removed?.outcome, 10) === 'retired' ? ' The old slot had attendance, so it was retired and its marks are kept.' : ''}`)
      refresh()
    } catch (reason) {
      setError(`${messageFrom(reason)} The grid was reloaded; check the slot is where you expect.`)
      setPendingMove(null)
      refresh()
    } finally {
      setSaving(false)
    }
  }

  async function undoMove() {
    const step = undoStack[undoStack.length - 1]
    if (!step) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (step.createdId > 0) await sendJson('DELETE', `/api/timetable/slots/${step.createdId}`)
      await sendJson('POST', '/api/timetable/slots', slotPayload(step.original, step.original.day, step.original.start_time, step.original.end_time))
      setUndoStack((current) => current.slice(0, -1))
      setNotice(`Undid: ${step.label}.`)
      refresh()
    } catch (reason) {
      setError(messageFrom(reason))
      refresh()
    } finally {
      setSaving(false)
    }
  }

  async function saveSlot(event: FormEvent) {
    event.preventDefault()
    if (!slot) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await sendJson('POST', '/api/timetable/slots', {
        course_id: Number(course),
        class_id: Number(classId),
        division_id: Number(division),
        subject_id: Number(slot.subject_id),
        faculty_id: slot.faculty_id ? Number(slot.faculty_id) : null,
        lab_batch_group_id: slot.lab_batch_group_id ? Number(slot.lab_batch_group_id) : null,
        room_id: slot.room_id ? Number(slot.room_id) : null,
        day: slot.day,
        start_time: slot.start_time.slice(0, 5),
        end_time: slot.end_time.slice(0, 5),
      })
      setSlot(null)
      setVersion((current) => current + 1)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function removeSlot() {
    if (!removing) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const outcome = await sendJson<{ outcome?: unknown }>('DELETE', `/api/timetable/slots/${removing.id}`)
      setRemoving(null)
      setVersion((current) => current + 1)
      if (safeText(outcome?.outcome, 10) === 'retired') setError('That slot already has attendance, so it was retired from the week rather than deleted. The marks are kept.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

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
      <div className="print:hidden">
      <Panel icon="fa-filter" iconClass="bg-indigo-100 text-indigo-600" title="Target group">
        <div className="space-y-4">
          <div className="inline-flex w-full rounded-lg bg-gray-100 p-1">
            {([['class', 'Class'], ['faculty', 'Teacher'], ['room', 'Room']] as [ViewMode, string][]).map(([key, label]) => (
              <button key={key} type="button" onClick={() => { setMode(key); setPendingMove(null) }} className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold ${mode === key ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-500'}`}>
                {label}
              </button>
            ))}
          </div>
          {mode === 'class' && (
            <>
              <SelectField label="Course" value={course} placeholder="Select course" items={courses} onChange={(value) => { setCourse(value); setClassId(''); setDivision('') }} />
              <div className="grid grid-cols-2 gap-3">
                <SelectField label="Class" value={classId} placeholder="Select" items={classes} onChange={(value) => { setClassId(value); setDivision('') }} />
                <SelectField label="Division" value={division} placeholder="Select" items={divisions} onChange={setDivision} />
              </div>
              <button
                type="button"
                disabled={!course || !classId || !division}
                onClick={() => setApplied({ course, classId, division })}
                className="w-full rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40"
              >
                Apply
              </button>
            </>
          )}
          {mode === 'faculty' && (
            <>
              <SelectField label="Teacher" value={person} placeholder="Select teacher" items={faculty} onChange={setPerson} />
              <button type="button" disabled={!person} onClick={() => setAppliedFocus({ mode: 'faculty', id: person })} className="w-full rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">Apply</button>
              <p className="text-xs text-gray-500">Every class this teacher meets in one week. Drag a session to move it; the check uses the same rules as adding a slot.</p>
            </>
          )}
          {mode === 'room' && (
            <>
              <SelectField label="Room" value={room} placeholder="Select room" items={rooms} onChange={setRoom} />
              <button type="button" disabled={!room} onClick={() => setAppliedFocus({ mode: 'room', id: room })} className="w-full rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-40">Apply</button>
              <p className="text-xs text-gray-500">Everything timetabled in this room, across classes.</p>
            </>
          )}
        </div>
      </Panel>
      </div>

      <section className="flex min-h-[520px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm xl:col-span-3 xl:h-full">
        <header className="flex shrink-0 flex-col justify-between gap-3 border-b border-gray-100 px-5 py-4 sm:flex-row sm:items-center print:hidden">
          <div className="flex items-center gap-2">
            <span className="h-6 w-2 rounded-full bg-indigo-500" />
            <h3 className="text-base font-bold text-gray-800">
              {mode === 'class' ? 'Weekly schedule' : mode === 'faculty' ? `Teacher week: ${faculty.find((item) => String(item.id) === appliedFocus.id)?.name || ''}` : `Room week: ${rooms.find((item) => String(item.id) === appliedFocus.id)?.name || ''}`}
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {ready && rows.length > 0 && mode === 'class' && (
              <button
                type="button"
                disabled={exporting}
                onClick={() => void queueTimetable()}
                className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-50"
              >
                <i className="fas fa-file-csv mr-2 text-emerald-600" /> Export CSV
              </button>
            )}
            {ready && rows.length > 0 && (
              <button type="button" onClick={() => { setView('grid'); window.setTimeout(() => window.print(), 50) }} className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700" title="Print the week grid">
                <i className="fas fa-print mr-2 text-gray-500" /> Print
              </button>
            )}
            {canEdit && undoStack.length > 0 && (
              <button type="button" disabled={saving} onClick={() => void undoMove()} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 disabled:opacity-50" title={undoStack[undoStack.length - 1].label}>
                <i className="fas fa-undo mr-2" /> Undo move ({undoStack.length})
              </button>
            )}
            {canEdit && ready && mode === 'class' && (
              <button type="button" onClick={() => setSlot({ ...emptySlot, subject_id: String(subjects[0]?.id ?? '') })} className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">
                <i className="fas fa-plus mr-2" /> Add slot
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
        <FailureNotice message={error} />
        <SuccessNotice message={notice} href="/admin/reports" hrefLabel="Open Reports" note="to follow the progress and download the file." />
        {!ready && (
          <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gray-50 text-gray-300">
              <i className="fas fa-calendar-week text-2xl" />
            </div>
            <h4 className="font-bold text-gray-800">Ready to view</h4>
            <p className="mt-1 max-w-md text-sm text-gray-500">
              {mode === 'class' ? 'Select a course, class, and division, then choose Apply.' : mode === 'faculty' ? 'Select a teacher, then choose Apply.' : 'Select a room, then choose Apply.'}
            </p>
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
                    <td className="px-6 py-4 font-bold text-gray-800">
                      {row.subject}
                      {row.lab_batch && <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-bold text-violet-700">Batch {row.lab_batch}</span>}
                      {mode !== 'class' && row.cohort && <p className="mt-0.5 text-xs font-normal text-gray-500">{row.cohort}</p>}
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-[10px] text-gray-500"><i className="fas fa-user" /></span>
                      {row.faculty || 'Unassigned'}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-between gap-2">
                        {row.room
                          ? <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"><i className="fas fa-door-open mr-1.5" />{row.room}</span>
                          : <span className="inline-flex items-center rounded-full border border-red-100 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-600"><i className="fas fa-exclamation-circle mr-1.5" />No room</span>}
                        {canEdit && row.id > 0 && <button type="button" title="Remove slot" className="rounded p-1.5 text-red-600 hover:bg-red-50" onClick={() => setRemoving(row)}><i className="fas fa-trash-alt" /></button>}
                      </div>
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
              <p className="py-16 text-center text-sm text-gray-500">{mode === 'class' ? 'No sessions are scheduled for this class.' : 'Nothing is timetabled here this week.'}</p>
            ) : (
              <>
                {canEdit && (
                  <p className="mb-3 text-xs text-gray-500 print:hidden">
                    <i className="fas fa-arrows-alt mr-1" /> Drag a session to another cell to move it. Cells turn
                    <span className="mx-1 rounded bg-emerald-100 px-1 text-emerald-800">green</span> when the move is clean,
                    <span className="mx-1 rounded bg-amber-100 px-1 text-amber-800">amber</span> when it costs soft-rule points and
                    <span className="mx-1 rounded bg-red-100 px-1 text-red-700">red</span> when a hard rule blocks it.
                  </p>
                )}
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
                        {day.cells.map((cell, index) => {
                          const column = grid.columns[index]
                          const check = dragging ? cellChecks[cellKey(day.day, column.start, column.end)] : undefined
                          const shade = !dragging ? '' : check === 'pending' ? 'bg-gray-50' : check === undefined ? '' : !check.ok ? 'bg-red-50' : (check.delta ?? 0) > 0 ? 'bg-amber-50' : 'bg-emerald-50'
                          const title = !check || check === 'pending' ? '' : !check.ok ? check.errors.map((item) => item.message).join(' ') : (check.delta ?? 0) > 0 ? `Costs ${check.delta} soft-rule points` : 'No rule broken'
                          return (
                            <td
                              key={`${day.day}-${index}`}
                              title={title}
                              className={`h-24 border border-gray-200 p-2 align-top transition-colors hover:bg-gray-50 ${shade}`}
                              onDragOver={(event) => { if (dragging) event.preventDefault() }}
                              onDrop={(event) => { event.preventDefault(); void dropOn(day.day, column.start, column.end) }}
                            >
                              {cell.length > 0 ? (
                                <div className="flex h-full flex-col gap-1">
                                  {cell.map((item, position) => (
                                    <div
                                      key={`${item.id}-${position}`}
                                      draggable={canEdit && item.id > 0}
                                      onDragStart={(event) => { event.dataTransfer.effectAllowed = 'move'; startDrag(item) }}
                                      onDragEnd={endDrag}
                                      className={`flex flex-1 flex-col justify-between rounded-lg bg-gradient-to-br p-2 text-white shadow-sm ${item.lab_batch ? 'from-violet-600 to-violet-700' : 'from-indigo-600 to-indigo-700'} ${canEdit && item.id > 0 ? 'cursor-grab active:cursor-grabbing' : ''} ${dragging?.id === item.id ? 'opacity-50' : ''}`}
                                    >
                                      <span className="text-xs leading-tight font-semibold">{cellLabel(item)}</span>
                                      {mode !== 'class' && item.cohort && <span className="mt-0.5 text-[10px] leading-tight opacity-80">{item.cohort}</span>}
                                      <i className="fas fa-clock mt-1 self-end text-[10px] opacity-75" />
                                    </div>
                                  ))}
                                </div>
                              ) : <span className="block text-center text-2xl font-light text-gray-200">·</span>}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </section>
      {slot && (
        <Modal title="Add a timetable slot" onClose={() => setSlot(null)}>
          <form className="grid grid-cols-2 gap-3" onSubmit={(event) => void saveSlot(event)}>
            <div className="col-span-2"><SelectField label="Subject" value={slot.subject_id} placeholder="Select subject" items={subjects} onChange={(value) => setSlot({ ...slot, subject_id: value })} /></div>
            <SelectField label="Faculty" value={slot.faculty_id} placeholder="Allocated faculty" items={faculty} onChange={(value) => setSlot({ ...slot, faculty_id: value })} />
            <SelectField label="Lab batch" value={slot.lab_batch_group_id} placeholder="Whole division" items={labBatches} onChange={(value) => setSlot({ ...slot, lab_batch_group_id: value })} />
            <SelectField label="Room" value={slot.room_id} placeholder="No room" items={rooms} onChange={(value) => setSlot({ ...slot, room_id: value })} />
            <label className="block">
              <span className={labelClass}>Day</span>
              <select value={slot.day} onChange={(event) => setSlot({ ...slot, day: event.target.value })} className={fieldClass}>
                {weekDays.map((day) => <option key={day} value={day}>{day}</option>)}
              </select>
            </label>
            <label className="block">
              <span className={labelClass}>Starts</span>
              <input required type="time" value={slot.start_time} onChange={(event) => setSlot({ ...slot, start_time: event.target.value })} className={fieldClass} />
            </label>
            <label className="block">
              <span className={labelClass}>Ends</span>
              <input required type="time" value={slot.end_time} onChange={(event) => setSlot({ ...slot, end_time: event.target.value })} className={fieldClass} />
            </label>
            <p className="col-span-2 text-xs text-gray-500">A batch slot only clashes with the same batch or a whole-division slot, so two batches can run practicals at the same time with different teachers and labs.</p>
            <button type="submit" disabled={saving || !slot.subject_id} className="col-span-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Add slot'}</button>
          </form>
        </Modal>
      )}
      {pendingMove && (
        <Modal title="Move this session?" onClose={() => setPendingMove(null)}>
          <p className="text-sm text-gray-700">
            <strong>{pendingMove.session.subject}</strong>{pendingMove.session.lab_batch ? ` (batch ${pendingMove.session.lab_batch})` : ''}
            {pendingMove.session.faculty ? ` with ${pendingMove.session.faculty}` : ''}
            {mode !== 'class' && pendingMove.session.cohort ? ` — ${pendingMove.session.cohort}` : ''}
          </p>
          <p className="mt-1 font-mono text-sm text-gray-600">
            {pendingMove.session.day} {pendingMove.session.start_time}–{pendingMove.session.end_time} → {pendingMove.day} {pendingMove.start_time}–{pendingMove.end_time}
          </p>
          {pendingMove.checking && <p className="mt-4 text-sm text-gray-500">Checking the new time…</p>}
          {pendingMove.check && !pendingMove.check.ok && (
            <ul className="mt-4 space-y-1 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {pendingMove.check.errors.map((item) => <li key={item.code}><i className="fas fa-ban mr-2" />{item.message}</li>)}
            </ul>
          )}
          {pendingMove.check?.ok && (
            <div className={`mt-4 rounded-xl border p-3 text-sm ${(pendingMove.check.delta ?? 0) > 0 ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
              {pendingMove.check.delta === null && 'No hard rule is broken.'}
              {pendingMove.check.delta !== null && (pendingMove.check.delta ?? 0) <= 0 && 'No hard rule is broken and no soft rule gets worse.'}
              {pendingMove.check.delta !== null && (pendingMove.check.delta ?? 0) > 0 && (
                <>
                  <p>No hard rule is broken, but this costs {pendingMove.check.delta} soft-rule point{pendingMove.check.delta === 1 ? '' : 's'}:</p>
                  <ul className="mt-1 list-disc pl-5">
                    {pendingMove.check.violations.map((item, index) => <li key={`${item.title}-${index}`}>{item.title}{item.faculty ? ` (${item.faculty})` : ''}{item.detail ? `: ${item.detail}` : ''}</li>)}
                  </ul>
                </>
              )}
            </div>
          )}
          <p className="mt-3 text-xs text-gray-500">The session is re-created at the new time. If attendance was already marked on it, the old slot is retired and the marks are kept. You can undo the move from the toolbar.</p>
          <div className="mt-4 flex gap-2">
            <button type="button" disabled={saving || pendingMove.checking || !pendingMove.check?.ok} className="rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50" onClick={() => void confirmMove()}>
              {saving ? 'Moving…' : 'Move session'}
            </button>
            <button type="button" className="rounded-xl border border-gray-300 px-4 py-2.5 text-sm font-bold text-gray-700" onClick={() => setPendingMove(null)}>Cancel</button>
          </div>
        </Modal>
      )}
      {removing && (
        <Modal title="Remove this slot?" onClose={() => setRemoving(null)}>
          <p className="text-sm text-gray-600">{removing.day} {removing.start_time}–{removing.end_time}: {removing.subject}{removing.lab_batch ? ` (batch ${removing.lab_batch})` : ''}. If attendance was already marked on it, the slot is retired and the marks are kept.</p>
          <button type="button" disabled={saving} className="mt-4 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50" onClick={() => void removeSlot()}>{saving ? 'Removing…' : 'Remove'}</button>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-gray-900/60" onClick={onClose} />
      <div className="relative m-4 max-h-[90vh] w-full max-w-lg overflow-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h3 className="text-base font-bold text-gray-800">{title}</h3>
          <button type="button" className="text-xl text-gray-500" onClick={onClose}>&times;</button>
        </div>
        <div className="p-6">{children}</div>
      </div>
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
  const [weekStart, setWeekStart] = useState(todayInput)
  const [dayStart, setDayStart] = useState('09:00')
  const [dayEnd, setDayEnd] = useState('15:00')
  const [lectureMinutes, setLectureMinutes] = useState('45')
  const [breakStart, setBreakStart] = useState('')
  const [breakDuration, setBreakDuration] = useState('0')
  const [workingDays, setWorkingDays] = useState<string[]>(weekDays)
  const [scope, setScope] = useState<'one' | 'course' | 'all'>('one')
  const [solver, setSolver] = useState<'greedy' | 'joint'>('greedy')
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
      solver,
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
            <div>
              <span className={labelClass}>Solver</span>
              <div className="grid grid-cols-2 gap-2">
                {([['greedy', 'Class by class'], ['joint', 'Jointly']] as const).map(([value, label]) => (
                  <button key={value} type="button" aria-pressed={solver === value} onClick={() => setSolver(value)} className={`rounded-md border py-2 text-xs font-medium ${solver === value ? 'border-indigo-700 bg-indigo-700 text-white' : 'border-gray-200 bg-white text-gray-600'}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-xs text-gray-500">
              {solver === 'joint'
                ? 'The request returns immediately. All selected classes are solved together, so shared faculty, electives and lab batches are placed in one pass; the quality score ranks the result.'
                : 'The request returns immediately. Classes then run one after another, so faculty and rooms are not double-booked.'}
            </p>
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
        <FailureNotice message={error} />
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
                {job.assigned_count} sessions scheduled. {job.failed_count} classes need attention.{' '}
                {job.version_id ? (
                  <Link to={`/admin/timetable/versions?version=${job.version_id}`} className="font-bold text-indigo-600">Compare and publish the draft</Link>
                ) : (
                  <Link to="/admin/timetable" className="font-bold text-indigo-600">View a class</Link>
                )}
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
              {job?.version_id && (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                  <p className="text-xs text-amber-800">
                    <i className="fas fa-file-signature mr-1" /> Saved as draft version #{job.version_id}. Students and teachers still see the current timetable until it is published.
                  </p>
                  <Link to={`/admin/timetable/versions?version=${job.version_id}`} className="rounded-xl bg-amber-600 px-3 py-1.5 text-xs font-bold text-white">
                    Compare and publish
                  </Link>
                </div>
              )}
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
                  <WarningNotice message={result.warnings.length === 0 ? '' : result.warnings.length === 1 ? result.warnings[0] : `${result.warnings.length} timetable warnings are listed with this result.`} />
                  {result.warnings.length > 0 && (
                    <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <h5 className="mb-1.5 text-[10px] font-bold tracking-wide text-amber-700 uppercase">Top warnings</h5>
                      <ul className="space-y-1">
                        {result.warnings.map((warning) => <li key={warning} className="text-xs text-amber-700"><i className="fas fa-exclamation-triangle mr-1" />{warning}</li>)}
                      </ul>
                    </div>
                  )}
                  {result.violations.length > 0 && (
                    <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <div className="mb-1.5 flex items-center justify-between">
                        <h5 className="text-[10px] font-bold tracking-wide text-gray-600 uppercase">Why these slots</h5>
                        <span className="text-[10px] font-semibold text-gray-500">Rule cost {result.rule_cost}</span>
                      </div>
                      <p className="mb-2 text-[11px] text-gray-500">Soft rules the solver could not satisfy, highest cost first. Adjust weights under Timetable → Rules or ask the teacher about their preference windows.</p>
                      <ul className="max-h-48 space-y-1 overflow-auto">
                        {result.violations.map((item, index) => (
                          <li key={`${item.rule}-${item.day}-${item.start_time}-${index}`} className="flex items-start gap-2 text-xs text-gray-700">
                            <span className="mt-0.5 shrink-0 rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-bold text-gray-600">{item.cost}</span>
                            <span>
                              <span className="font-semibold">{item.title}</span>
                              {item.faculty && <span className="text-gray-500"> · {item.faculty}</span>}
                              {item.day && <span className="text-gray-500"> · {item.day.slice(0, 3)}{item.start_time && ` ${item.start_time}`}{item.end_time && `–${item.end_time}`}</span>}
                              {item.detail && <span className="block text-[11px] text-gray-500">{item.detail}</span>}
                            </span>
                          </li>
                        ))}
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
                          <h5 className="text-sm font-bold text-gray-800">{session.subject}{session.lab_batch && <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-bold text-violet-700">Batch {session.lab_batch}</span>}</h5>
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
