import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError, apiRequest } from '../../../shared/api/client'
import { todayInput } from '../../../shared/dates'
import { messageFrom, useCapability } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { sendJson } from '../../academics/api'

type Room = { id: number; room_number: string; room_type: string; capacity: number | null; institution_id: number | null }
type Booking = {
  id: number
  room_id: number
  room_number: string
  room_type: string
  room_institution: string
  institution: string
  title: string
  kind: string
  booking_date: string | null
  day_of_week: string | null
  repeat_until: string | null
  start_time: string
  end_time: string
  notes: string
  status: string
  booked_by: string
  decided_by: string
  decided_at: string
  decision_note: string
  created_at: string
  can_decide: boolean
  can_cancel: boolean
}
type Payload = {
  bookings?: Record<string, unknown>[]
  rooms?: Record<string, unknown>[]
  kinds?: unknown[]
  days?: unknown[]
  requires_approval?: boolean
  permissions?: { request?: boolean; approve?: boolean }
}
type Draft = {
  room_id: string
  title: string
  kind: string
  when: 'date' | 'weekly'
  booking_date: string
  day_of_week: string
  repeat_until: string
  start_time: string
  end_time: string
  notes: string
}

const STATUSES = ['requested', 'approved', 'rejected', 'cancelled'] as const
const statusTone: Record<string, string> = {
  requested: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-600',
}
const kindLabel: Record<string, string> = { event: 'Event', exam: 'Exam', maintenance: 'Maintenance', external: 'External' }
const emptyDraft: Draft = {
  room_id: '', title: '', kind: 'event', when: 'date', booking_date: todayInput(), day_of_week: 'Monday', repeat_until: '',
  start_time: '10:00', end_time: '11:00', notes: '',
}
const field = 'w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none'
const smallButton = 'rounded-lg border px-2.5 py-1 text-xs font-bold disabled:opacity-50'

function readRoom(row: Record<string, unknown>): Room {
  return {
    id: safeCount(row.id), room_number: safeText(row.room_number, 20), room_type: safeText(row.room_type, 30),
    capacity: safeCount(row.capacity) || null, institution_id: safeCount(row.institution_id) || null,
  }
}

function readBooking(row: Record<string, unknown>): Booking {
  const status = safeText(row.status, 12)
  return {
    id: safeCount(row.id),
    room_id: safeCount(row.room_id),
    room_number: safeText(row.room_number, 20),
    room_type: safeText(row.room_type, 30),
    room_institution: safeText(row.room_institution, 40),
    institution: safeText(row.institution, 40),
    title: safeText(row.title, 120),
    kind: safeText(row.kind, 12),
    booking_date: row.booking_date ? safeText(row.booking_date, 10) : null,
    day_of_week: row.day_of_week ? safeText(row.day_of_week, 10) : null,
    repeat_until: row.repeat_until ? safeText(row.repeat_until, 10) : null,
    start_time: safeText(row.start_time, 5),
    end_time: safeText(row.end_time, 5),
    notes: safeText(row.notes, 500),
    status: (STATUSES as readonly string[]).includes(status) ? status : 'requested',
    booked_by: safeText(row.booked_by, 100),
    decided_by: safeText(row.decided_by, 100),
    decided_at: safeText(row.decided_at, 16),
    decision_note: safeText(row.decision_note, 300),
    created_at: safeText(row.created_at, 16),
    can_decide: row.can_decide === true,
    can_cancel: row.can_cancel === true,
  }
}

function when(booking: Booking) {
  if (booking.booking_date) return booking.booking_date
  return `Every ${booking.day_of_week}${booking.repeat_until ? ` until ${booking.repeat_until}` : ''}`
}

export function BookingsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('bookings')
  const [bookings, setBookings] = useState<Booking[]>([])
  const [rooms, setRooms] = useState<Room[]>([])
  const [kinds, setKinds] = useState<string[]>(Object.keys(kindLabel))
  const [days, setDays] = useState<string[]>(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
  const [requiresApproval, setRequiresApproval] = useState(true)
  const [canApprove, setCanApprove] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [roomFilter, setRoomFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [formError, setFormError] = useState('')
  const [alternatives, setAlternatives] = useState<Room[]>([])
  const [deciding, setDeciding] = useState<{ booking: Booking; approve: boolean; note: string } | null>(null)

  const load = useCallback(async () => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (roomFilter) params.set('room_id', roomFilter)
    const query = params.toString()
    const data = await apiRequest<Payload>(`/api/bookings${query ? `?${query}` : ''}`)
    setBookings((data.bookings || []).slice(0, 300).map(readBooking).filter((row) => row.id > 0))
    setRooms((data.rooms || []).slice(0, 500).map(readRoom).filter((row) => row.id > 0))
    const kindList = (data.kinds || []).map((item) => safeText(item, 12)).filter((item) => item in kindLabel)
    if (kindList.length) setKinds(kindList)
    const dayList = (data.days || []).map((item) => safeText(item, 10)).filter(Boolean)
    if (dayList.length) setDays(dayList)
    setRequiresApproval(data.requires_approval !== false)
    setCanApprove(data.permissions?.approve === true)
  }, [status, roomFilter])

  useEffect(() => {
    setPageHeader('Room bookings')
    if (!enabled) {
      setLoading(false)
      return
    }
    setLoading(true)
    void load()
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [enabled, load, setPageHeader])

  function openForm(room?: Room) {
    setDraft({ ...emptyDraft, room_id: String(room?.id ?? rooms[0]?.id ?? '') })
    setFormError('')
    setAlternatives([])
    setFormOpen(true)
  }

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (!draft.room_id) return setFormError('Choose a room.')
    if (!draft.title.trim()) return setFormError('Give the booking a title.')
    if (draft.start_time >= draft.end_time) return setFormError('The end time must be after the start time.')
    if (draft.when === 'date' && !draft.booking_date) return setFormError('Choose a date.')
    setBusy(true)
    setFormError('')
    setAlternatives([])
    setNotice('')
    try {
      const body: Record<string, unknown> = {
        room_id: Number(draft.room_id), title: draft.title.trim(), kind: draft.kind,
        start_time: draft.start_time, end_time: draft.end_time, notes: draft.notes.trim(),
      }
      if (draft.when === 'date') body.booking_date = draft.booking_date
      else {
        body.day_of_week = draft.day_of_week
        if (draft.repeat_until) body.repeat_until = draft.repeat_until
      }
      const result = await sendJson<{ booking?: Record<string, unknown> }>('POST', '/api/bookings', body)
      const created = result.booking ? readBooking(result.booking) : null
      setFormOpen(false)
      setNotice(created?.status === 'approved' ? `${created.room_number} is booked for ${created.title}.` : 'Booking requested. The room\'s institution will approve or reject it.')
      await load()
    } catch (reason) {
      if (reason instanceof ApiError && (reason.code === 'booking_room_busy' || reason.code === 'booking_room_booked')) {
        const detail = safeText(reason.details.message, 300)
        setFormError(detail || reason.message)
        const offered = Array.isArray(reason.details.alternatives) ? (reason.details.alternatives as Record<string, unknown>[]) : []
        setAlternatives(offered.slice(0, 8).map(readRoom).filter((room) => room.id > 0))
      } else {
        setFormError(messageFrom(reason))
      }
    } finally {
      setBusy(false)
    }
  }

  async function decide() {
    if (!deciding || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const action = deciding.approve ? 'approve' : 'reject'
      await sendJson('POST', `/api/bookings/${deciding.booking.id}/${action}`, deciding.note.trim() ? { note: deciding.note.trim() } : undefined)
      setNotice(`Booking ${deciding.approve ? 'approved' : 'rejected'}.`)
      setDeciding(null)
      await load()
    } catch (reason) {
      if (reason instanceof ApiError && (reason.code === 'booking_room_busy' || reason.code === 'booking_room_booked')) {
        setError(safeText(reason.details.message, 300) || reason.message)
        setDeciding(null)
      } else {
        setError(messageFrom(reason))
      }
    } finally {
      setBusy(false)
    }
  }

  async function cancel(booking: Booking) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await sendJson('POST', `/api/bookings/${booking.id}/cancel`)
      setNotice(`Booking of ${booking.room_number} cancelled.`)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
        Room bookings are switched off for this institution. Turn on the <strong>Room bookings</strong> capability under Settings → Capabilities
        to reserve rooms for events, exams and maintenance on the same clash ledger the timetable uses.
      </section>
    )
  }

  const pending = bookings.filter((row) => row.status === 'requested').length

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 flex-col gap-3 border-b border-gray-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Room bookings</h2>
          <p className="text-xs text-gray-500">
            A booking reserves a room for an event, exam, maintenance or an outside party. Approved bookings block the room for the generator and
            manual slots; a booking that meets a timetabled class is refused with the free rooms of that type.
            {requiresApproval ? ' Requests wait for the room\'s institution to approve them.' : ' Bookings are approved at once.'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700">
            <option value="">All statuses</option>
            {STATUSES.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}{item === 'requested' && pending > 0 && !status ? ` (${pending})` : ''}</option>)}
          </select>
          <select aria-label="Room" value={roomFilter} onChange={(event) => setRoomFilter(event.target.value)} className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700">
            <option value="">All rooms</option>
            {rooms.map((room) => <option key={room.id} value={room.id}>{room.room_number}{room.room_type ? ` · ${room.room_type}` : ''}</option>)}
          </select>
          <button type="button" onClick={() => openForm()} disabled={rooms.length === 0} className="rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50">
            <i className="fas fa-plus mr-2" /> Book a room
          </button>
        </div>
      </header>

      {error && <FailureNotice message={error} />}
      {notice && <SuccessNotice message={notice} />}

      {formOpen && (
        <form onSubmit={(event) => void submit(event)} className="shrink-0 border-b border-gray-100 bg-gray-50 px-5 py-4">
          <div className="grid gap-3 md:grid-cols-4">
            <label className="text-xs font-semibold text-gray-600">Room
              <select value={draft.room_id} onChange={(event) => update('room_id', event.target.value)} className={`${field} mt-1`}>
                {rooms.map((room) => <option key={room.id} value={room.id}>{room.room_number}{room.room_type ? ` · ${room.room_type}` : ''}{room.capacity ? ` · ${room.capacity} seats` : ''}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-gray-600 md:col-span-2">Title
              <input value={draft.title} maxLength={120} onChange={(event) => update('title', event.target.value)} className={`${field} mt-1`} placeholder="Guest lecture, internal exam, projector repair…" />
            </label>
            <label className="text-xs font-semibold text-gray-600">Kind
              <select value={draft.kind} onChange={(event) => update('kind', event.target.value)} className={`${field} mt-1`}>
                {kinds.map((kind) => <option key={kind} value={kind}>{kindLabel[kind] || kind}</option>)}
              </select>
            </label>
            <div className="text-xs font-semibold text-gray-600">When
              <div className="mt-1 flex gap-3 rounded-xl border border-gray-200 bg-white px-3 py-2">
                <label className="flex items-center gap-1"><input type="radio" checked={draft.when === 'date'} onChange={() => update('when', 'date')} /> One date</label>
                <label className="flex items-center gap-1"><input type="radio" checked={draft.when === 'weekly'} onChange={() => update('when', 'weekly')} /> Weekly</label>
              </div>
            </div>
            {draft.when === 'date' ? (
              <label className="text-xs font-semibold text-gray-600">Date
                <input type="date" value={draft.booking_date} onChange={(event) => update('booking_date', event.target.value)} className={`${field} mt-1`} />
              </label>
            ) : (
              <>
                <label className="text-xs font-semibold text-gray-600">Weekday
                  <select value={draft.day_of_week} onChange={(event) => update('day_of_week', event.target.value)} className={`${field} mt-1`}>
                    {days.map((day) => <option key={day} value={day}>{day}</option>)}
                  </select>
                </label>
                <label className="text-xs font-semibold text-gray-600">Until (optional)
                  <input type="date" value={draft.repeat_until} onChange={(event) => update('repeat_until', event.target.value)} className={`${field} mt-1`} />
                </label>
              </>
            )}
            <label className="text-xs font-semibold text-gray-600">From
              <input type="time" value={draft.start_time} onChange={(event) => update('start_time', event.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="text-xs font-semibold text-gray-600">To
              <input type="time" value={draft.end_time} onChange={(event) => update('end_time', event.target.value)} className={`${field} mt-1`} />
            </label>
            <label className="text-xs font-semibold text-gray-600 md:col-span-4">Notes
              <input value={draft.notes} maxLength={500} onChange={(event) => update('notes', event.target.value)} className={`${field} mt-1`} placeholder="Who is it for, what is needed" />
            </label>
          </div>
          {formError && (
            <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <p>{formError}</p>
              {alternatives.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs font-semibold">Free {rooms.find((room) => String(room.id) === draft.room_id)?.room_type || 'rooms'} at that time:</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {alternatives.map((room) => (
                      <button key={room.id} type="button" onClick={() => { update('room_id', String(room.id)); setFormError(''); setAlternatives([]) }} className="rounded-lg border border-red-200 bg-white px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-100">
                        {room.room_number}{room.capacity ? ` (${room.capacity})` : ''}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <button type="submit" disabled={busy} className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
              {busy ? 'Checking…' : requiresApproval && !canApprove ? 'Request booking' : 'Book room'}
            </button>
            <button type="button" onClick={() => setFormOpen(false)} className="rounded-xl border border-gray-300 px-4 py-2 text-sm font-bold text-gray-700">Cancel</button>
          </div>
        </form>
      )}

      <div className="flex-1 overflow-auto">
        {loading ? (
          <p className="px-5 py-10 text-center text-sm text-gray-500">Loading…</p>
        ) : bookings.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <i className="fas fa-calendar-check text-3xl text-gray-300" />
            <h4 className="mt-3 font-bold text-gray-800">No bookings{status ? ` ${status}` : ''}</h4>
            <p className="mt-1 text-sm text-gray-500">Book a room for an event, exam or maintenance and it is kept free on the timetable.</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-gray-50 text-xs font-bold tracking-wider text-gray-500 uppercase">
              <tr>
                <th className="px-5 py-3">Room</th>
                <th className="px-5 py-3">Booking</th>
                <th className="px-5 py-3">When</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {bookings.map((booking) => (
                <tr key={booking.id} className="align-top hover:bg-gray-50">
                  <td className="px-5 py-3">
                    <p className="font-bold text-gray-800">{booking.room_number}</p>
                    <p className="text-xs text-gray-500">{booking.room_type}{booking.room_institution ? ` · ${booking.room_institution}` : ''}</p>
                  </td>
                  <td className="px-5 py-3">
                    <p className="font-semibold text-gray-800">{booking.title}</p>
                    <p className="text-xs text-gray-500">
                      {kindLabel[booking.kind] || booking.kind} · asked by {booking.booked_by || 'unknown'}{booking.institution ? ` (${booking.institution})` : ''}
                    </p>
                    {booking.notes && <p className="mt-1 text-xs text-gray-600">{booking.notes}</p>}
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-gray-700">
                    <p>{when(booking)}</p>
                    <p>{booking.start_time}–{booking.end_time}</p>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${statusTone[booking.status] || statusTone.requested}`}>{booking.status}</span>
                    {booking.decided_by && <p className="mt-1 text-xs text-gray-500">by {booking.decided_by}{booking.decided_at ? ` · ${booking.decided_at}` : ''}</p>}
                    {booking.decision_note && <p className="mt-0.5 text-xs text-gray-600">“{booking.decision_note}”</p>}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      {booking.can_decide && (
                        <>
                          <button type="button" disabled={busy} onClick={() => setDeciding({ booking, approve: true, note: '' })} className={`${smallButton} border-emerald-200 bg-emerald-50 text-emerald-700`}>Approve</button>
                          <button type="button" disabled={busy} onClick={() => setDeciding({ booking, approve: false, note: '' })} className={`${smallButton} border-red-200 bg-red-50 text-red-700`}>Reject</button>
                        </>
                      )}
                      {booking.can_cancel && (
                        <button type="button" disabled={busy} onClick={() => void cancel(booking)} className={`${smallButton} border-gray-300 text-gray-700`}>Cancel</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {deciding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-base font-bold text-gray-800">{deciding.approve ? 'Approve' : 'Reject'} this booking?</h3>
            <p className="mt-1 text-sm text-gray-600">
              <strong>{deciding.booking.title}</strong> in {deciding.booking.room_number}, {when(deciding.booking)} {deciding.booking.start_time}–{deciding.booking.end_time},
              asked by {deciding.booking.booked_by || 'unknown'}.
            </p>
            {deciding.approve && <p className="mt-2 text-xs text-gray-500">The room is checked again against the timetable and other approved bookings before it is reserved.</p>}
            <label className="mt-3 block text-xs font-semibold text-gray-600">Note to the requester (optional)
              <input value={deciding.note} maxLength={300} onChange={(event) => setDeciding({ ...deciding, note: event.target.value })} className={`${field} mt-1`} />
            </label>
            <div className="mt-4 flex gap-2">
              <button type="button" disabled={busy} onClick={() => void decide()} className={`rounded-xl px-4 py-2 text-sm font-bold text-white disabled:opacity-50 ${deciding.approve ? 'bg-emerald-600' : 'bg-red-600'}`}>
                {busy ? 'Saving…' : deciding.approve ? 'Approve' : 'Reject'}
              </button>
              <button type="button" onClick={() => setDeciding(null)} className="rounded-xl border border-gray-300 px-4 py-2 text-sm font-bold text-gray-700">Back</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
