import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom, useCapability } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Bounds = { min: number | null; max: number | null }
type Norms = { default: Bounds; by_designation: Record<string, Bounds> }
type Teacher = {
  facultyId: number
  name: string
  designation: string
  department: string
  hours: number
  min: number | null
  max: number | null
  status: 'over' | 'under' | 'ok' | 'no_norm'
}
type Payload = {
  norms?: Record<string, unknown>
  stored?: boolean
  enforce?: string
  designations?: unknown[]
  teachers?: Record<string, unknown>[]
  max_hours?: number
  can_change?: boolean
}

const statusLabel: Record<Teacher['status'], string> = { over: 'Over', under: 'Under', ok: 'Within norm', no_norm: 'No norm' }
const statusClass: Record<Teacher['status'], string> = {
  over: 'bg-red-100 text-red-700',
  under: 'bg-amber-100 text-amber-700',
  ok: 'bg-emerald-100 text-emerald-700',
  no_norm: 'bg-gray-100 text-gray-500',
}
const secondaryButton = 'rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-bold text-gray-700 disabled:opacity-50'
const field = 'w-20 rounded border border-gray-300 px-2 py-1 text-xs disabled:bg-gray-50'

function readHours(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 && number <= 60 ? Math.round(number * 10) / 10 : null
}

function readBounds(raw: unknown): Bounds {
  const given = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return { min: readHours(given.min), max: readHours(given.max) }
}

function readNorms(raw: Record<string, unknown> | undefined): Norms {
  const byDesignation: Record<string, Bounds> = {}
  const given = raw?.by_designation && typeof raw.by_designation === 'object' ? (raw.by_designation as Record<string, unknown>) : {}
  for (const [name, bounds] of Object.entries(given).slice(0, 40)) {
    const label = safeText(name, 50)
    if (label) byDesignation[label] = readBounds(bounds)
  }
  return { default: readBounds(raw?.default), by_designation: byDesignation }
}

function readTeachers(rows: Record<string, unknown>[] | undefined): Teacher[] {
  return (rows || []).slice(0, 500).map((row) => {
    const status = row.status === 'over' || row.status === 'under' || row.status === 'ok' ? row.status : 'no_norm'
    return {
      facultyId: safeCount(row.faculty_id),
      name: safeText(row.name, 100),
      designation: safeText(row.designation, 50),
      department: safeText(row.department_name, 100),
      hours: readHours(row.hours) ?? 0,
      min: readHours(row.min),
      max: readHours(row.max),
      status,
    }
  })
}

function hoursText(value: number | null) {
  return value === null ? '—' : `${value} h`
}

export function WorkloadNormsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('workload_norms')
  const [saved, setSaved] = useState<Norms>({ default: { min: null, max: null }, by_designation: {} })
  const [draft, setDraft] = useState<Norms>({ default: { min: null, max: null }, by_designation: {} })
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [designations, setDesignations] = useState<string[]>([])
  const [enforce, setEnforce] = useState('soft')
  const [stored, setStored] = useState(false)
  const [canChange, setCanChange] = useState(false)
  const [newDesignation, setNewDesignation] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function apply(data: Payload) {
    const norms = readNorms(data.norms)
    setSaved(norms)
    setDraft(norms)
    setTeachers(readTeachers(data.teachers))
    setDesignations((data.designations || []).slice(0, 100).map((item) => safeText(item, 50)).filter(Boolean))
    setEnforce(data.enforce === 'hard' ? 'hard' : 'soft')
    setStored(data.stored === true)
    setCanChange(data.can_change === true)
  }

  useEffect(() => {
    setPageHeader('Workload norms')
    if (!enabled) {
      setLoading(false)
      return
    }
    void apiRequest<Payload>('/api/timetable/workload-norms')
      .then(apply)
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [enabled, setPageHeader])

  function updateBounds(designation: string | null, key: keyof Bounds, raw: string) {
    const value = raw === '' ? null : Number(raw)
    setDraft((current) => {
      if (designation === null) return { ...current, default: { ...current.default, [key]: value } }
      const bounds = current.by_designation[designation] || { min: null, max: null }
      return { ...current, by_designation: { ...current.by_designation, [designation]: { ...bounds, [key]: value } } }
    })
  }

  function addDesignation() {
    const name = safeText(newDesignation.trim(), 50)
    if (!name || draft.by_designation[name]) return
    setDraft((current) => ({ ...current, by_designation: { ...current.by_designation, [name]: { min: null, max: null } } }))
    setNewDesignation('')
  }

  function removeDesignation(name: string) {
    setDraft((current) => {
      const next = { ...current.by_designation }
      delete next[name]
      return { ...current, by_designation: next }
    })
  }

  function invalid(): string {
    const check = (label: string, bounds: Bounds) => {
      for (const key of ['min', 'max'] as const) {
        const value = bounds[key]
        if (value !== null && (!Number.isFinite(value) || value < 0 || value > 60)) return `${label}: hours must be 0 to 60.`
      }
      if (bounds.min !== null && bounds.max !== null && bounds.min > bounds.max) return `${label}: the minimum cannot exceed the maximum.`
      return ''
    }
    const problem = check('Default', draft.default)
    if (problem) return problem
    for (const [name, bounds] of Object.entries(draft.by_designation)) {
      const issue = check(name, bounds)
      if (issue) return issue
    }
    return ''
  }

  async function save() {
    if (!canChange) return
    const problem = invalid()
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const data = await apiRequest<Payload>('/api/timetable/workload-norms', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ norms: draft }),
      })
      apply(data)
      setNotice('Norms saved. The next generation run uses them.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)
  const unlisted = designations.filter((name) => !draft.by_designation[name])
  const flagged = teachers.filter((teacher) => teacher.status === 'over' || teacher.status === 'under').length

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
        Workload norms are an optional capability, switched off for this institution. Turn it on under Settings → Capabilities.
      </section>
    )
  }

  const boundsEditor = (label: string, designation: string | null, bounds: Bounds) => (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col text-xs text-gray-600">
        <span className="mb-1 font-semibold">Min h/week</span>
        <input
          type="number"
          min={0}
          max={60}
          step={0.5}
          value={bounds.min ?? ''}
          disabled={!canChange || busy}
          aria-label={`${label} minimum hours`}
          onChange={(event) => updateBounds(designation, 'min', event.target.value)}
          className={field}
        />
      </label>
      <label className="flex flex-col text-xs text-gray-600">
        <span className="mb-1 font-semibold">Max h/week</span>
        <input
          type="number"
          min={0}
          max={60}
          step={0.5}
          value={bounds.max ?? ''}
          disabled={!canChange || busy}
          aria-label={`${label} maximum hours`}
          onChange={(event) => updateBounds(designation, 'max', event.target.value)}
          className={field}
        />
      </label>
      {designation !== null && canChange && (
        <button type="button" className={secondaryButton} disabled={busy} onClick={() => removeDesignation(designation)}>
          Remove
        </button>
      )}
    </div>
  )

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Workload norms</h2>
            <p className="text-xs text-gray-500">
              Weekly teaching hours each designation should carry. The generator{' '}
              {enforce === 'hard' ? (
                <strong>never schedules a teacher beyond their maximum</strong>
              ) : (
                <>treats hours beyond the maximum as a cost (the <strong>Weekly workload</strong> rule)</>
              )}
              ; the workload report and each teacher's dashboard flag anyone under or over. Switch between soft and hard under Settings → Capabilities.
            </p>
            {!stored && !loading && <p className="mt-1 text-xs text-gray-500">Nothing saved yet: no teacher has a norm.</p>}
            {!canChange && !loading && <p className="mt-1 text-xs text-gray-500">You can view the norms. Changing them needs the timetable generation permission.</p>}
          </div>
          {canChange && (
            <div className="flex gap-2">
              <button type="button" className={secondaryButton} disabled={busy || !dirty} onClick={() => setDraft(saved)}>
                Discard
              </button>
              <button type="button" className="rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-bold text-white disabled:opacity-50" disabled={busy || !dirty} onClick={() => void save()}>
                {busy ? 'Saving…' : 'Save norms'}
              </button>
            </div>
          )}
        </div>
        {error && <div className="mt-3"><FailureNotice message={error} /></div>}
        {notice && <div className="mt-3"><SuccessNotice message={notice} /></div>}
      </section>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {loading && <p className="p-6 text-center text-sm text-gray-500">Loading norms…</p>}
        {!loading && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <section className="rounded-2xl border border-gray-200">
              <ul className="divide-y divide-gray-100">
                <li className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
                  <div className="min-w-[10rem]">
                    <span className="text-sm font-semibold text-gray-900">Default</span>
                    <p className="mt-1 text-xs text-gray-500">Applies to every designation without its own norm. Leave both empty for no norm.</p>
                  </div>
                  {boundsEditor('Default', null, draft.default)}
                </li>
                {Object.entries(draft.by_designation).map(([name, bounds]) => (
                  <li key={name} className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
                    <div className="min-w-[10rem]">
                      <span className="text-sm font-semibold text-gray-900">{name}</span>
                      {!designations.includes(name) && <p className="mt-1 text-xs text-gray-400">No teacher has this designation today.</p>}
                    </div>
                    {boundsEditor(name, name, bounds)}
                  </li>
                ))}
              </ul>
              {canChange && (
                <div className="flex flex-wrap items-end gap-2 border-t border-gray-100 px-5 py-4">
                  <label className="flex flex-col text-xs text-gray-600">
                    <span className="mb-1 font-semibold">Designation</span>
                    <input
                      list="workload-designations"
                      value={newDesignation}
                      maxLength={50}
                      disabled={busy}
                      aria-label="New designation"
                      placeholder="e.g. Professor"
                      onChange={(event) => setNewDesignation(event.target.value)}
                      className="w-56 rounded border border-gray-300 px-2 py-1 text-xs"
                    />
                    <datalist id="workload-designations">
                      {unlisted.map((name) => <option key={name} value={name} />)}
                    </datalist>
                  </label>
                  <button type="button" className={secondaryButton} disabled={busy || !newDesignation.trim()} onClick={addDesignation}>
                    Add norm
                  </button>
                </div>
              )}
            </section>
            <section className="rounded-2xl border border-gray-200">
              <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                <h3 className="text-sm font-semibold text-gray-900">Teachers this week</h3>
                <span className="text-xs text-gray-500">{flagged ? `${flagged} outside their norm` : 'Everyone within norm'}</span>
              </div>
              {teachers.length === 0 ? (
                <p className="p-6 text-center text-sm text-gray-500">No active teachers.</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-left text-[11px] font-semibold tracking-wide text-gray-500 uppercase">
                    <tr>
                      <th className="px-4 py-2">Teacher</th>
                      <th className="px-4 py-2">Designation</th>
                      <th className="px-4 py-2 text-right">Hours</th>
                      <th className="px-4 py-2 text-right">Norm</th>
                      <th className="px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {teachers.map((teacher) => (
                      <tr key={teacher.facultyId}>
                        <td className="px-4 py-2">
                          <div className="font-semibold text-gray-900">{teacher.name}</div>
                          {teacher.department && <div className="text-[11px] text-gray-500">{teacher.department}</div>}
                        </td>
                        <td className="px-4 py-2 text-gray-700">{teacher.designation || '—'}</td>
                        <td className="px-4 py-2 text-right font-semibold text-gray-900">{teacher.hours} h</td>
                        <td className="px-4 py-2 text-right text-gray-700">
                          {teacher.min === null && teacher.max === null ? '—' : `${hoursText(teacher.min)} – ${hoursText(teacher.max)}`}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase ${statusClass[teacher.status]}`}>
                            {statusLabel[teacher.status]}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        )}
      </div>
    </section>
  )
}
