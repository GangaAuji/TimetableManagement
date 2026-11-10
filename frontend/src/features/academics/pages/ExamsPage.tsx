import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { useCapability } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, sendJson } from '../api'
import { Banners, Screen, fieldClass, messageFrom } from '../ui'

type Exam = { id: number; name: string; kind: string; term_id: number | null; term_name: string }
type Subject = { id: number; name: string; course_code: string; class_name: string; elective: boolean }
type Room = { id: number; room_number: string; capacity: number }
type Term = { id: number; name: string; start: string; end: string }
type SessionRoom = { room_number: string; faculty_name: string; role: string; seats: number }
type Session = { id: number; subject_name: string; course_code: string; date: string; start: string; end: string; cohorts: string[]; rooms: SessionRoom[] }
type Payload = {
  exams?: Record<string, unknown>[]
  exam?: Record<string, unknown> | null
  sessions?: Record<string, unknown>[]
  subjects?: Record<string, unknown>[]
  rooms?: Record<string, unknown>[]
  terms?: Record<string, unknown>[]
  kinds?: unknown[]
  permissions?: { change?: boolean }
}

function text(value: unknown, limit: number) {
  return safeText(value, limit)
}

function examOf(row: Record<string, unknown>): Exam | null {
  const id = asId(row.id)
  const name = text(row.name, 80)
  if (!id || !name) return null
  return { id, name, kind: text(row.kind, 20), term_id: asId(row.term_id) || null, term_name: text(row.term_name, 80) }
}

export function ExamsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('exams')
  const [exams, setExams] = useState<Exam[]>([])
  const [examId, setExamId] = useState(0)
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [rooms, setRooms] = useState<Room[]>([])
  const [terms, setTerms] = useState<Term[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [kinds, setKinds] = useState<string[]>(['internal', 'university', 'practical'])
  const [canChange, setCanChange] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('internal')
  const [termId, setTermId] = useState(0)
  const [pickedSubjects, setPickedSubjects] = useState<number[]>([])
  const [pickedRooms, setPickedRooms] = useState<number[]>([])
  const [dates, setDates] = useState('')
  const [gap, setGap] = useState(0)
  const [morning, setMorning] = useState(true)
  const [afternoon, setAfternoon] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  function apply(data: Payload, chosen: number) {
    const nextExams = (data.exams || []).map(examOf).filter((row): row is Exam => row !== null)
    const nextSubjects = (data.subjects || []).map((row) => ({
      id: asId(row.id),
      name: text(row.name, 100),
      course_code: text(row.course_code, 20),
      class_name: text(row.class_name, 80),
      elective: row.elective === true,
    })).filter((row) => row.id > 0 && row.name)
    const nextRooms = (data.rooms || []).map((row) => ({
      id: asId(row.id), room_number: text(row.room_number, 20), capacity: safeCount(row.capacity),
    })).filter((row) => row.id > 0)
    const nextTerms = (data.terms || []).map((row) => ({
      id: asId(row.id), name: text(row.name, 80), start: text(row.start, 10), end: text(row.end, 10),
    })).filter((row) => row.id > 0)
    const nextSessions = (data.sessions || []).map((row) => ({
      id: asId(row.id),
      subject_name: text(row.subject_name, 100),
      course_code: text(row.course_code, 20),
      date: text(row.date, 10),
      start: text(row.start, 8),
      end: text(row.end, 8),
      cohorts: Array.isArray(row.cohorts) ? row.cohorts.map((item) => text(item, 120)).filter(Boolean) : [],
      rooms: Array.isArray(row.rooms) ? row.rooms.map((item) => {
        const room = item as Record<string, unknown>
        return {
          room_number: text(room.room_number, 20),
          faculty_name: text(room.faculty_name, 100),
          role: text(room.role, 20),
          seats: safeCount(room.seats),
        }
      }) : [],
    })).filter((row) => row.id > 0)
    setExams(nextExams)
    setSubjects(nextSubjects)
    setRooms(nextRooms)
    setTerms(nextTerms)
    setSessions(nextSessions)
    setKinds((data.kinds || []).map((item) => text(item, 20)).filter(Boolean))
    setCanChange(data.permissions?.change === true)
    setExamId(asId(data.exam?.id) || chosen || nextExams[0]?.id || 0)
  }

  async function load(chosen = examId) {
    const path = chosen ? `/api/exams?exam_id=${chosen}` : '/api/exams'
    const data = await apiRequest<Payload>(path)
    apply(data, chosen)
  }

  useEffect(() => { setPageHeader('Exams') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let cancel = false
    setLoading(true)
    load(0).catch((reason) => { if (!cancel) setError(messageFrom(reason)) }).finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [enabled])

  function toggle(list: number[], id: number, setList: (next: number[]) => void) {
    setList(list.includes(id) ? list.filter((item) => item !== id) : [...list, id])
  }

  async function createExam() {
    setError('')
    setNotice('')
    try {
      const data = await sendJson<Payload>('POST', '/api/exams', { name, kind, term_id: termId || undefined })
      apply(data, 0)
      setName('')
      setNotice('Exam created. Choose the papers and solve the timetable.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function solve() {
    setError('')
    setNotice('')
    const slots = [
      ...(morning ? [{ start: '09:30', end: '12:30' }] : []),
      ...(afternoon ? [{ start: '14:00', end: '17:00' }] : []),
    ]
    const parsedDates = dates.split(',').map((item) => item.trim()).filter(Boolean)
    try {
      const data = await sendJson<Payload>('POST', `/api/exams/${examId}/solve`, {
        subject_ids: pickedSubjects,
        room_ids: pickedRooms.length ? pickedRooms : undefined,
        dates: parsedDates.length ? parsedDates : undefined,
        slots,
        seating_gap: gap,
      })
      apply(data, examId)
      setNotice('Timetable solved. Download the seating plan or the hall tickets.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function remove() {
    setError('')
    setNotice('')
    try {
      const data = await sendJson<Payload>('DELETE', `/api/exams/${examId}`)
      apply(data, 0)
      setSessions([])
      setNotice('Exam deleted.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  return (
    <Screen title="Exam timetable" subtitle={enabled ? 'Papers, rooms and invigilation. Students who share a paper cannot sit two at once.' : 'Turn on Exam timetable under Settings → Capabilities.'}>
      <Banners error={error} notice={notice} />
      {!enabled || loading ? null : (
        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-gray-600">
              Exam
              <select className={fieldClass()} value={examId || ''} onChange={(event) => { const next = asId(event.target.value); setExamId(next); void load(next).catch((reason) => setError(messageFrom(reason))) }}>
                {exams.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </label>
            {examId && sessions.length ? (
              <>
                <a className="text-xs text-indigo-700 underline" href={`/api/exams/${examId}/seating`}>Seating plan</a>
                <a className="text-xs text-indigo-700 underline" href={`/api/exams/${examId}/hall-tickets`}>Hall tickets</a>
              </>
            ) : null}
            {canChange && examId ? <button type="button" className="text-xs text-red-700" onClick={() => void remove()}>Delete exam</button> : null}
          </div>

          {canChange ? (
            <div className="flex flex-wrap items-end gap-3 border-t border-gray-100 pt-3">
              <label className="text-xs text-gray-600">
                New exam
                <input className={fieldClass()} value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="text-xs text-gray-600">
                Kind
                <select className={fieldClass()} value={kind} onChange={(event) => setKind(event.target.value)}>
                  {kinds.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="text-xs text-gray-600">
                Exam term
                <select className={fieldClass()} value={termId || ''} onChange={(event) => setTermId(asId(event.target.value))}>
                  <option value="">Dates entered below</option>
                  {terms.map((row) => <option key={row.id} value={row.id}>{row.name} ({row.start} – {row.end})</option>)}
                </select>
              </label>
              <button type="button" className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void createExam()}>Create</button>
            </div>
          ) : null}

          {canChange && examId ? (
            <div className="grid gap-4 border-t border-gray-100 pt-3 md:grid-cols-2">
              <fieldset>
                <legend className="text-xs font-medium text-gray-700">Papers</legend>
                <div className="mt-1 max-h-48 space-y-1 overflow-auto">
                  {subjects.map((row) => (
                    <label key={row.id} className="flex items-center gap-2 text-xs text-gray-700">
                      <input type="checkbox" checked={pickedSubjects.includes(row.id)} onChange={() => toggle(pickedSubjects, row.id, setPickedSubjects)} />
                      <span>{row.course_code ? `${row.course_code} ` : ''}{row.name}{row.class_name ? ` — ${row.class_name}` : ''}{row.elective ? ' (elective)' : ''}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend className="text-xs font-medium text-gray-700">Rooms</legend>
                <div className="mt-1 max-h-48 space-y-1 overflow-auto">
                  {rooms.map((row) => (
                    <label key={row.id} className="flex items-center gap-2 text-xs text-gray-700">
                      <input type="checkbox" checked={pickedRooms.includes(row.id)} onChange={() => toggle(pickedRooms, row.id, setPickedRooms)} />
                      <span>{row.room_number} ({row.capacity})</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="text-xs text-gray-600">
                Dates (blank uses the exam term)
                <input className={fieldClass()} placeholder="2026-12-01, 2026-12-02" value={dates} onChange={(event) => setDates(event.target.value)} />
              </label>
              <div className="flex flex-wrap items-center gap-3 text-xs text-gray-700">
                <label className="flex items-center gap-1"><input type="checkbox" checked={morning} onChange={(event) => setMorning(event.target.checked)} /> 09:30–12:30</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={afternoon} onChange={(event) => setAfternoon(event.target.checked)} /> 14:00–17:00</label>
                <label className="flex items-center gap-1">
                  Seating gap
                  <input className="w-14 rounded border border-gray-300 px-2 py-1" type="number" min={0} max={3} value={gap} onChange={(event) => setGap(safeCount(event.target.value))} />
                </label>
                <button type="button" className="rounded bg-indigo-600 px-3 py-1.5 text-white" onClick={() => void solve()}>Solve</button>
              </div>
            </div>
          ) : null}

          {sessions.length ? (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="py-1 pr-2">Date</th>
                  <th className="py-1 pr-2">Time</th>
                  <th className="py-1 pr-2">Paper</th>
                  <th className="py-1">Rooms</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((row) => (
                  <tr key={row.id} className="border-t border-gray-100">
                    <td className="py-1 pr-2">{row.date}</td>
                    <td className="py-1 pr-2">{row.start}–{row.end}</td>
                    <td className="py-1 pr-2">{row.course_code ? `${row.course_code} ` : ''}{row.subject_name}{row.cohorts.length ? ` (${row.cohorts.join(', ')})` : ''}</td>
                    <td className="py-1">{row.rooms.map((room) => `${room.room_number}: ${room.faculty_name || room.role} (${room.seats})`).join('; ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      )}
    </Screen>
  )
}
