import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { pageFill } from '../../../shared/layout/page-frame'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Slot = {
  isAvailable: boolean
  shiftId: number | null
  code: string
  display: string
  timeRange: string
  notes: string
  extra: number
}

type FacultyRow = {
  userId: number
  name: string
  departmentId: number | null
  department: string
  days: Record<string, Slot>
}

type Pattern = { id: number; name: string; code: string; start: string; end: string }
type Department = { id: number; name: string }

const week = [
  ['1', 'Mon'],
  ['2', 'Tue'],
  ['3', 'Wed'],
  ['4', 'Thu'],
  ['5', 'Fri'],
  ['6', 'Sat'],
  ['7', 'Sun'],
] as const

const emptySlot: Slot = { isAvailable: false, shiftId: null, code: '', display: '', timeRange: '', notes: '', extra: 0 }
const fieldClass = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 outline-none focus:border-indigo-500'

function readSlot(value: unknown): Slot {
  if (!value || typeof value !== 'object') return emptySlot
  const slot = value as Record<string, unknown>
  const shiftId = safeCount(slot.shift_pattern_id)
  return {
    isAvailable: slot.is_available === true,
    shiftId: shiftId || null,
    code: safeText(slot.shift_code, 20),
    display: safeText(slot.display_text, 40),
    timeRange: safeText(slot.time_range, 40),
    notes: safeText(slot.notes, 300),
    extra: safeCount(slot.extra),
  }
}

function readFaculty(row: Record<string, unknown>): FacultyRow {
  const days: Record<string, Slot> = {}
  const source = row.days
  if (source && typeof source === 'object') {
    for (const [day, slot] of Object.entries(source as Record<string, unknown>)) {
      if (/^[1-7]$/.test(day)) days[day] = readSlot(slot)
    }
  }
  const departmentId = safeCount(row.department_id)
  return {
    userId: safeCount(row.user_id),
    name: safeText(row.name, 100),
    departmentId: departmentId || null,
    department: safeText(row.department, 100),
    days,
  }
}

export function AvailabilityPage() {
  const setPageHeader = useSetPageHeader()
  const [faculty, setFaculty] = useState<FacultyRow[]>([])
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [canChange, setCanChange] = useState(false)
  const [department, setDepartment] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [busyKey, setBusyKey] = useState('')
  const [bulkOpen, setBulkOpen] = useState(false)
  const [selectedFaculty, setSelectedFaculty] = useState<number[]>([])
  const [selectedDays, setSelectedDays] = useState<string[]>([])
  const [bulkShift, setBulkShift] = useState('')
  const [markAvailable, setMarkAvailable] = useState(true)
  const [notes, setNotes] = useState('')
  const [savingBulk, setSavingBulk] = useState(false)
  const [toast, setToast] = useState<{ text: string; tone: 'ok' | 'bad'; id: number } | null>(null)

  useEffect(() => {
    setPageHeader('Faculty Shift Availability')
  }, [setPageHeader])

  useEffect(() => {
    let active = true
    setLoading(true)
    void apiRequest<{ faculty?: Record<string, unknown>[]; patterns?: Record<string, unknown>[]; departments?: Record<string, unknown>[]; can_change?: boolean }>('/api/availability')
      .then((data) => {
        if (!active) return
        setCanChange(data.can_change === true)
        setFaculty((data.faculty || []).map(readFaculty))
        setPatterns((data.patterns || []).map((row) => ({
          id: safeCount(row.id),
          name: safeText(row.name, 80),
          code: safeText(row.code, 20),
          start: safeText(row.start_time, 8),
          end: safeText(row.end_time, 8),
        })))
        setDepartments((data.departments || []).map((row) => ({
          id: safeCount(row.id),
          name: safeText(row.name, 100),
        })))
        setError('')
      })
      .catch((reason: unknown) => {
        if (active) setError(messageFrom(reason))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 3000)
    return () => window.clearTimeout(timer)
  }, [toast])

  function showToast(text: string, tone: 'ok' | 'bad') {
    setToast({ text, tone, id: Date.now() })
  }

  function putSlot(userId: number, day: string, next: Slot | undefined) {
    setFaculty((rows) => rows.map((row) => {
      if (row.userId !== userId) return row
      const days = { ...row.days }
      if (next) days[day] = next
      else delete days[day]
      return { ...row, days }
    }))
  }

  async function changeShift(row: FacultyRow, day: string, value: string) {
    const key = `${row.userId}-${day}`
    if (busyKey) return
    const previous = row.days[day]
    const shiftId = value ? safeCount(value) : 0
    const pattern = patterns.find((item) => item.id === shiftId)
    const next: Slot = {
      ...(previous ?? emptySlot),
      isAvailable: Boolean(shiftId),
      shiftId: shiftId || null,
      code: pattern?.code || '',
      display: pattern?.code || '',
      timeRange: pattern ? `${pattern.start} - ${pattern.end}` : '',
    }
    putSlot(row.userId, day, next)
    setBusyKey(key)
    try {
      await postJson('/api/availability/day', {
        faculty_id: row.userId,
        day_of_week: Number(day),
        shift_pattern_id: shiftId || null,
        is_available: Boolean(shiftId),
      })
      showToast('Availability updated successfully', 'ok')
    } catch (reason) {
      putSlot(row.userId, day, previous)
      showToast(messageFrom(reason), 'bad')
    } finally {
      setBusyKey('')
    }
  }

  async function toggleDay(row: FacultyRow, day: string, checked: boolean) {
    const key = `${row.userId}-${day}`
    if (busyKey) return
    const previous = row.days[day]
    const next: Slot = checked
      ? { ...(previous ?? emptySlot), isAvailable: true }
      : { ...(previous ?? emptySlot), isAvailable: false, shiftId: null, code: '', display: '', timeRange: '' }
    putSlot(row.userId, day, next)
    setBusyKey(key)
    try {
      const payload: { faculty_id: number; day_of_week: number; is_available: boolean; shift_pattern_id?: null } = {
        faculty_id: row.userId,
        day_of_week: Number(day),
        is_available: checked,
      }
      if (!checked) payload.shift_pattern_id = null
      await postJson('/api/availability/day', payload)
      showToast('Availability updated successfully', 'ok')
    } catch (reason) {
      putSlot(row.userId, day, previous)
      showToast(messageFrom(reason), 'bad')
    } finally {
      setBusyKey('')
    }
  }

  function toggleFaculty(userId: number, checked: boolean) {
    setSelectedFaculty((current) => (checked ? [...current, userId] : current.filter((id) => id !== userId)))
  }

  function toggleAllFaculty(checked: boolean) {
    setSelectedFaculty(checked ? faculty.map((row) => row.userId) : [])
  }

  function toggleBulkDay(day: string, checked: boolean) {
    setSelectedDays((current) => (checked ? [...current, day] : current.filter((item) => item !== day)))
  }

  async function saveBulk() {
    if (selectedFaculty.length === 0 || selectedDays.length === 0) {
      showToast('Select at least one faculty member and one day.', 'bad')
      return
    }
    setSavingBulk(true)
    try {
      await postJson('/api/availability/bulk', {
        faculty_ids: selectedFaculty,
        days: selectedDays.map((day) => Number(day)),
        shift_pattern_id: bulkShift ? Number(bulkShift) : null,
        is_available: markAvailable,
        notes,
      })
      setBulkOpen(false)
      setSelectedFaculty([])
      setSelectedDays([])
      setBulkShift('')
      setNotes('')
      setMarkAvailable(true)
      showToast('Bulk availability updated successfully', 'ok')
      setReloadKey((value) => value + 1)
    } catch (reason) {
      showToast(messageFrom(reason), 'bad')
    } finally {
      setSavingBulk(false)
    }
  }

  const visible = faculty.filter((row) => !department || String(row.departmentId || '') === department)

  return (
    <section className={`${pageFill} gap-2`}>
      <div className="shrink-0 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col items-start justify-between gap-3 xl:flex-row xl:items-center">
          <div>
            <h2 className="text-lg font-bold text-gray-800">Faculty Availability</h2>
            <p className="text-xs text-gray-500">Configure weekly work schedules for faculty members</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select value={department} onChange={(event) => setDepartment(event.target.value)} className="rounded-md border border-gray-300 px-3 py-2 text-sm" aria-label="Department">
              <option value="">All Departments</option>
              {departments.map((item) => (
                <option key={item.id} value={String(item.id)}>{item.name}</option>
              ))}
            </select>
            <Link to="/admin/shifts" className="rounded bg-gray-600 px-4 py-2 text-xs whitespace-nowrap text-white shadow hover:bg-gray-700">
              <i className="fas fa-clock mr-2" />
              Manage Shifts
            </Link>
            {canChange && (
              <button type="button" className="rounded bg-indigo-600 px-4 py-2 text-xs whitespace-nowrap text-white shadow hover:bg-indigo-700" onClick={() => setBulkOpen(true)}>
                <i className="fas fa-tasks mr-2" />
                Bulk Update
              </button>
            )}
          </div>
        </div>
      </div>

      {error && <p className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        <div className="flex-1 overflow-auto">
          <table className="w-full min-w-[960px] divide-y divide-gray-200">
            <thead className="sticky top-0 z-10 bg-gray-50">
              <tr>
                <th className="sticky left-0 bg-gray-50 px-4 py-3 text-left text-xs font-bold tracking-wider text-gray-600 uppercase">Faculty</th>
                {week.map(([day, label]) => (
                  <th key={day} className="px-3 py-3 text-center text-xs font-bold tracking-wider text-gray-600 uppercase">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {loading && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-500">Loading availability…</td></tr>
              )}
              {!loading && visible.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    <i className="fas fa-users mb-2 text-4xl opacity-50" />
                    <p>No faculty members found</p>
                  </td>
                </tr>
              )}
              {!loading && visible.map((row) => (
                <tr key={row.userId} className="hover:bg-indigo-50">
                  <td className="sticky left-0 bg-white px-4 py-3">
                    <div className="font-semibold text-gray-900">{row.name}</div>
                    <div className="text-xs text-gray-500">{row.department}</div>
                  </td>
                  {week.map(([day]) => {
                    const slot = row.days[day]
                    const available = Boolean(slot?.isAvailable)
                    const locked = busyKey === `${row.userId}-${day}`
                    return (
                      <td key={day} className="px-2 py-2 text-center">
                        {canChange ? (
                          <div className="flex flex-col items-center gap-1">
                            <select
                              aria-label={`${row.name} ${day}`}
                              disabled={locked}
                              value={slot?.shiftId ? String(slot.shiftId) : ''}
                              title={slot?.timeRange || 'No time set'}
                              onChange={(event) => void changeShift(row, day, event.target.value)}
                              className={`w-full rounded border px-2 py-1 text-xs outline-none ${available ? 'border-green-300 bg-green-50' : 'border-gray-300 bg-gray-50'}`}
                            >
                              <option value="">Not Set</option>
                              {patterns.map((pattern) => (
                                <option key={pattern.id} value={pattern.id}>{pattern.code}</option>
                              ))}
                            </select>
                            {slot?.timeRange && (
                              <div className="text-xs text-gray-500" title={slot.notes}>{slot.timeRange.slice(0, 5)}</div>
                            )}
                            {slot && slot.extra > 0 && (
                              <div className="text-xs text-blue-600" title="Multiple time slots set">+{slot.extra} more</div>
                            )}
                            <label className="flex cursor-pointer items-center">
                              <input
                                type="checkbox"
                                className="h-3 w-3 rounded border-gray-300 text-green-600"
                                checked={available}
                                disabled={locked}
                                onChange={(event) => void toggleDay(row, day, event.target.checked)}
                              />
                              <span className="ml-1 text-xs text-gray-600">Avail</span>
                            </label>
                          </div>
                        ) : (
                          <div className="flex flex-col items-center gap-1">
                            {slot ? (
                              <>
                                <div className={`rounded px-2 py-1 text-xs ${available ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                                  {slot.display || 'Not Set'}
                                </div>
                                {slot.timeRange && <div className="text-xs text-gray-500">{slot.timeRange}</div>}
                                <div className={`text-xs ${available ? 'text-green-600' : 'text-gray-400'}`}>{available ? 'Available' : 'Not Available'}</div>
                              </>
                            ) : (
                              <div className="text-xs text-gray-400">Not Set</div>
                            )}
                          </div>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {bulkOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-600/50" onClick={() => setBulkOpen(false)}>
          <div className="relative top-20 mx-auto w-full max-w-2xl rounded-md border bg-white p-5 shadow-lg" onClick={(event) => event.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Bulk Update Availability</h3>
              <button type="button" className="text-gray-400 hover:text-gray-600" onClick={() => setBulkOpen(false)} aria-label="Close">
                <i className="fas fa-times" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <div className="mb-2 text-sm font-medium text-gray-700">Select Faculty *</div>
                <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border border-gray-300 p-3">
                  <label className="flex items-center">
                    <input type="checkbox" className="h-4 w-4 rounded border-gray-300" checked={faculty.length > 0 && selectedFaculty.length === faculty.length} onChange={(event) => toggleAllFaculty(event.target.checked)} />
                    <span className="ml-2 text-sm font-bold text-gray-900">Select All</span>
                  </label>
                  <hr />
                  {faculty.map((row) => (
                    <label key={row.userId} className="flex items-center">
                      <input type="checkbox" className="h-4 w-4 rounded border-gray-300" checked={selectedFaculty.includes(row.userId)} onChange={(event) => toggleFaculty(row.userId, event.target.checked)} />
                      <span className="ml-2 text-sm text-gray-700">{row.name} ({row.department || 'No Department'})</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-sm font-medium text-gray-700">Select Days *</div>
                <div className="flex flex-wrap gap-2">
                  {week.map(([day, label]) => (
                    <label key={day} className="flex cursor-pointer items-center rounded-md border border-gray-300 px-3 py-2 hover:bg-indigo-50">
                      <input type="checkbox" className="h-4 w-4 rounded border-gray-300" checked={selectedDays.includes(day)} onChange={(event) => toggleBulkDay(day, event.target.checked)} />
                      <span className="ml-2 text-sm text-gray-700">{label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700" htmlFor="bulk-shift">Shift Pattern</label>
                <select id="bulk-shift" value={bulkShift} onChange={(event) => setBulkShift(event.target.value)} className={fieldClass}>
                  <option value="">Not Set</option>
                  {patterns.map((pattern) => (
                    <option key={pattern.id} value={pattern.id}>{pattern.name} ({pattern.start} - {pattern.end})</option>
                  ))}
                </select>
              </div>
              <label className="flex items-center">
                <input type="checkbox" className="h-4 w-4 rounded border-gray-300" checked={markAvailable} onChange={(event) => setMarkAvailable(event.target.checked)} />
                <span className="ml-2 text-sm text-gray-700">Mark as Available</span>
              </label>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700" htmlFor="bulk-notes">Notes (optional)</label>
                <textarea id="bulk-notes" rows={2} maxLength={300} value={notes} onChange={(event) => setNotes(event.target.value)} className={fieldClass} />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-gray-700 hover:bg-gray-200" onClick={() => setBulkOpen(false)}>Cancel</button>
              <button type="button" disabled={savingBulk} className="rounded-md bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-40" onClick={() => void saveBulk()}>Update Availability</button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`fixed right-4 bottom-4 z-50 rounded-lg px-6 py-3 text-white shadow-lg ${toast.tone === 'ok' ? 'bg-green-500' : 'bg-red-500'}`} role="status">
          {toast.text}
        </div>
      )}
    </section>
  )
}
