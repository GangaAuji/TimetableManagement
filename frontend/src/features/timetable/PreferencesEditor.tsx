import { useEffect, useState } from 'react'
import { ApiError, apiRequest } from '../../shared/api/client'
import { getCsrfToken } from '../../shared/api/endpoints'
import { messageFrom, useCapability } from '../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../shared/components/success-notice'
import { safeCount, safeText } from '../../shared/security/sanitize'

/**
 * Soft day/time preferences a teacher asks the solver to respect (capability `timetable_preferences`).
 * `path` is `/api/portal/preferences` for the signed-in teacher or `/api/faculty/<id>/preferences`
 * for an admin. Renders nothing while the capability is off.
 */

export type PreferenceWindow = { day: string; start_time: string; end_time: string; kind: 'preferred' | 'avoid'; weight: number; note: string }
type Payload = { faculty_name?: unknown; preferences?: Record<string, unknown>[]; can_change?: unknown }

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const field = 'rounded-xl border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-800 outline-none focus:border-gray-400 disabled:bg-gray-50'
const emptyWindow: PreferenceWindow = { day: 'Monday', start_time: '09:00', end_time: '10:00', kind: 'avoid', weight: 3, note: '' }

function readWindows(rows: Record<string, unknown>[] | undefined): PreferenceWindow[] {
  return (rows || []).map((row): PreferenceWindow => ({
    day: days.includes(safeText(row.day, 12)) ? safeText(row.day, 12) : 'Monday',
    start_time: safeText(row.start_time, 5),
    end_time: safeText(row.end_time, 5),
    kind: row.kind === 'preferred' ? 'preferred' : 'avoid',
    weight: Math.min(5, Math.max(1, safeCount(row.weight) || 3)),
    note: safeText(row.note, 120),
  })).slice(0, 60)
}

export function PreferencesEditor({ path, compact = false }: { path: string; compact?: boolean }) {
  const enabled = useCapability('timetable_preferences')
  const [windows, setWindows] = useState<PreferenceWindow[]>([])
  const [canChange, setCanChange] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [hidden, setHidden] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!enabled) return
    setLoaded(false)
    setHidden(false)
    void apiRequest<Payload>(path)
      .then((data) => {
        setWindows(readWindows(data.preferences))
        setCanChange(data.can_change === true)
        setLoaded(true)
      })
      .catch((reason: unknown) => {
        if (reason instanceof ApiError && reason.status === 404) { setHidden(true); return }
        setError(messageFrom(reason))
      })
  }, [path, enabled])

  if (!enabled || hidden) return null

  function update(index: number, patch: Partial<PreferenceWindow>) {
    setWindows((current) => current.map((item, position) => (position === index ? { ...item, ...patch } : item)))
  }

  async function save() {
    setSaving(true)
    setError('')
    setSaved('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const data = await apiRequest<Payload>(path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ preferences: windows.map((item) => ({ ...item, note: item.note || undefined })) }),
      })
      setWindows(readWindows(data.preferences))
      setSaved('Preferences saved. The next generation weighs them.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`rounded-2xl border border-gray-200 bg-white ${compact ? 'p-3' : 'p-4'}`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold text-gray-800">Timetable preferences</h3>
          <p className="text-xs text-gray-500">Windows to avoid or prefer. These are wishes, not blocks: the solver pays a cost to break them (weight 1 mild to 5 strong). Use Availability for hard limits.</p>
        </div>
        {canChange && loaded && (
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border px-3 py-1.5 text-xs font-bold" disabled={windows.length >= 60} onClick={() => setWindows([...windows, { ...emptyWindow }])}>Add window</button>
            <button type="button" className="rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50" disabled={saving} onClick={() => void save()}>{saving ? 'Saving...' : 'Save preferences'}</button>
          </div>
        )}
      </div>
      <FailureNotice message={error} />
      <SuccessNotice message={saved} />
      {loaded && windows.length === 0 && <p className="py-3 text-center text-xs text-gray-400">No preference windows yet.</p>}
      <ul className="space-y-2">
        {windows.map((item, index) => (
          <li key={index} className="grid gap-2 sm:grid-cols-[1.1fr_0.9fr_0.9fr_1fr_0.7fr_2fr_auto]">
            <select aria-label="Day" value={item.day} disabled={!canChange} onChange={(event) => update(index, { day: event.target.value })} className={field}>
              {days.map((day) => <option key={day} value={day}>{day}</option>)}
            </select>
            <input aria-label="From" type="time" value={item.start_time} disabled={!canChange} onChange={(event) => update(index, { start_time: event.target.value })} className={field} />
            <input aria-label="To" type="time" value={item.end_time} disabled={!canChange} onChange={(event) => update(index, { end_time: event.target.value })} className={field} />
            <select aria-label="Kind" value={item.kind} disabled={!canChange} onChange={(event) => update(index, { kind: event.target.value === 'preferred' ? 'preferred' : 'avoid' })} className={field}>
              <option value="avoid">Avoid</option>
              <option value="preferred">Prefer</option>
            </select>
            <select aria-label="Weight" value={item.weight} disabled={!canChange} onChange={(event) => update(index, { weight: Number(event.target.value) })} className={field}>
              {[1, 2, 3, 4, 5].map((weight) => <option key={weight} value={weight}>{weight}</option>)}
            </select>
            <input aria-label="Note" value={item.note} maxLength={120} placeholder="Reason (optional)" disabled={!canChange} onChange={(event) => update(index, { note: event.target.value })} className={field} />
            {canChange && <button type="button" aria-label="Remove window" className="text-xs font-bold text-gray-500" onClick={() => setWindows(windows.filter((_item, position) => position !== index))}><i className="fas fa-times" /></button>}
          </li>
        ))}
      </ul>
    </section>
  )
}
