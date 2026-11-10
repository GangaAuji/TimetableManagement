import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom, useCapability } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Status = 'draft' | 'published' | 'archived'
type Cohort = { course_id: number; class_id: number; division_id: number; label: string }
type Score = { quality_score: number | null; rule_cost: number | null; assigned: number; unassigned: number }
type Version = {
  id: number
  label: string
  status: Status
  solver: string
  jobId: number | null
  parentVersionId: number | null
  createdBy: string
  createdAt: string
  publishedBy: string
  publishedAt: string
  slotCount: number
  cohorts: Cohort[]
  score: Score
}
type Slot = { day: string; start_time: string; end_time: string; subject: string; faculty: string; room: string; batch: string }
type Cell = { day: string; start_time: string; end_time: string; room: string }
type ChangeKind = 'added' | 'removed' | 'moved' | 'room_changed'
type Change = { kind: ChangeKind; subject: string; faculty: string; batch: string; before: Cell | null; after: Cell | null }
type DiffCohort = Cohort & { counts: Record<string, number>; changes: Change[]; before: Slot[]; after: Slot[] }
type Diff = {
  version: Version
  other: Version | null
  totals: Record<string, number>
  cohorts: DiffCohort[]
  faculty: { faculty: string; moved: number; added: number; removed: number; room_changed: number }[]
  canPublish: boolean
}
type ListPayload = { versions?: Record<string, unknown>[]; can_publish?: boolean; keep_drafts?: number }

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const statusStyle: Record<Status, string> = {
  published: 'bg-emerald-100 text-emerald-800',
  draft: 'bg-amber-100 text-amber-800',
  archived: 'bg-gray-100 text-gray-600',
}
const kindLabel: Record<string, string> = { unchanged: 'Unchanged', moved: 'Moved', added: 'Added', removed: 'Removed', room_changed: 'Room changed' }
const kindStyle: Record<string, string> = {
  moved: 'bg-amber-100 text-amber-800', added: 'bg-emerald-100 text-emerald-800', removed: 'bg-red-100 text-red-700', room_changed: 'bg-sky-100 text-sky-800', unchanged: 'bg-gray-100 text-gray-600',
}
const cellStyle: Record<string, string> = {
  moved: 'border-amber-300 bg-amber-50', added: 'border-emerald-300 bg-emerald-50', removed: 'border-red-300 bg-red-50', room_changed: 'border-sky-300 bg-sky-50',
}
const secondaryButton = 'rounded-xl border border-gray-300 px-3 py-1.5 text-xs font-bold text-gray-700 disabled:opacity-50'

function readStatus(value: unknown): Status {
  return value === 'published' || value === 'archived' ? value : 'draft'
}

function readCohort(row: Record<string, unknown>): Cohort {
  return {
    course_id: safeCount(row.course_id), class_id: safeCount(row.class_id), division_id: safeCount(row.division_id),
    label: safeText(row.label, 300),
  }
}

function readScore(raw: unknown): Score {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return {
    quality_score: typeof row.quality_score === 'number' ? Math.round(row.quality_score * 100) / 100 : null,
    rule_cost: typeof row.rule_cost === 'number' ? safeCount(row.rule_cost) : null,
    assigned: safeCount(row.assigned),
    unassigned: safeCount(row.unassigned),
  }
}

function readVersion(row: Record<string, unknown>): Version {
  return {
    id: safeCount(row.id),
    label: safeText(row.label, 120),
    status: readStatus(row.status),
    solver: safeText(row.solver, 20),
    jobId: safeCount(row.job_id) || null,
    parentVersionId: safeCount(row.parent_version_id) || null,
    createdBy: safeText(row.created_by, 100),
    createdAt: safeText(row.created_at, 20),
    publishedBy: safeText(row.published_by, 100),
    publishedAt: safeText(row.published_at, 20),
    slotCount: safeCount(row.slot_count),
    cohorts: Array.isArray(row.cohorts) ? (row.cohorts as Record<string, unknown>[]).slice(0, 200).map(readCohort) : [],
    score: readScore(row.score),
  }
}

function readSlot(row: Record<string, unknown>): Slot {
  return {
    day: safeText(row.day, 12), start_time: safeText(row.start_time, 5), end_time: safeText(row.end_time, 5),
    subject: safeText(row.subject, 100), faculty: safeText(row.faculty, 100), room: safeText(row.room, 20), batch: safeText(row.batch, 60),
  }
}

function readCell(raw: unknown): Cell | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  return { day: safeText(row.day, 12), start_time: safeText(row.start_time, 5), end_time: safeText(row.end_time, 5), room: safeText(row.room, 20) }
}

function readDiff(data: Record<string, unknown>): Diff {
  const totals: Record<string, number> = {}
  for (const [key, value] of Object.entries((data.totals as Record<string, unknown>) || {})) {
    if (key in kindLabel) totals[key] = safeCount(value)
  }
  return {
    version: readVersion((data.version as Record<string, unknown>) || {}),
    other: data.other ? readVersion(data.other as Record<string, unknown>) : null,
    totals,
    cohorts: ((data.cohorts as Record<string, unknown>[]) || []).slice(0, 200).map((row) => {
      const counts: Record<string, number> = {}
      for (const [key, value] of Object.entries((row.counts as Record<string, unknown>) || {})) {
        if (key in kindLabel) counts[key] = safeCount(value)
      }
      return {
        ...readCohort(row),
        counts,
        changes: ((row.changes as Record<string, unknown>[]) || []).slice(0, 400).map((change) => ({
          kind: (['added', 'removed', 'moved', 'room_changed'].includes(String(change.kind)) ? change.kind : 'moved') as ChangeKind,
          subject: safeText(change.subject, 100), faculty: safeText(change.faculty, 100), batch: safeText(change.batch, 60),
          before: readCell(change.before), after: readCell(change.after),
        })),
        before: ((row.before as Record<string, unknown>[]) || []).slice(0, 500).map(readSlot),
        after: ((row.after as Record<string, unknown>[]) || []).slice(0, 500).map(readSlot),
      }
    }),
    faculty: ((data.faculty as Record<string, unknown>[]) || []).slice(0, 100).map((row) => ({
      faculty: safeText(row.faculty, 100), moved: safeCount(row.moved), added: safeCount(row.added), removed: safeCount(row.removed), room_changed: safeCount(row.room_changed),
    })),
    canPublish: data.can_publish === true,
  }
}

function slotKey(slot: { day: string; start_time: string; end_time: string }, subject: string, faculty: string) {
  return `${slot.day}|${slot.start_time}|${slot.end_time}|${subject}|${faculty}`
}

/** Which change kind, if any, a slot in the before/after grid belongs to. */
function highlights(cohort: DiffCohort) {
  const before = new Map<string, ChangeKind>()
  const after = new Map<string, ChangeKind>()
  for (const change of cohort.changes) {
    if (change.before) before.set(slotKey(change.before, change.subject, change.faculty), change.kind)
    if (change.after) after.set(slotKey(change.after, change.subject, change.faculty), change.kind)
  }
  return { before, after }
}

function WeekGrid({ title, slots, marks, emptyText }: { title: string; slots: Slot[]; marks: Map<string, ChangeKind>; emptyText: string }) {
  const shownDays = days.filter((day) => slots.some((slot) => slot.day === day))
  const times = Array.from(new Set(slots.map((slot) => `${slot.start_time}-${slot.end_time}`))).sort()
  if (slots.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 p-4 text-center text-xs text-gray-500">
        <div className="mb-1 font-bold text-gray-700">{title}</div>
        {emptyText}
      </div>
    )
  }
  return (
    <div className="overflow-auto rounded-xl border border-gray-200">
      <div className="border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs font-bold text-gray-700">{title}</div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="bg-gray-50 text-gray-500">
            <th className="px-2 py-1 text-left font-semibold">Time</th>
            {shownDays.map((day) => <th key={day} className="px-2 py-1 text-left font-semibold">{day.slice(0, 3)}</th>)}
          </tr>
        </thead>
        <tbody>
          {times.map((time) => {
            const [start, end] = time.split('-')
            return (
              <tr key={time} className="border-t border-gray-100 align-top">
                <td className="whitespace-nowrap px-2 py-1 font-semibold text-gray-600">{start}–{end}</td>
                {shownDays.map((day) => {
                  const here = slots.filter((slot) => slot.day === day && slot.start_time === start && slot.end_time === end)
                  return (
                    <td key={day} className="px-1 py-1">
                      {here.map((slot, index) => {
                        const kind = marks.get(slotKey(slot, slot.subject, slot.faculty))
                        return (
                          <div key={`${slot.subject}-${slot.faculty}-${index}`} className={`mb-1 rounded-lg border px-2 py-1 ${kind ? cellStyle[kind] : 'border-gray-200 bg-white'}`} title={kind ? kindLabel[kind] : 'Unchanged'}>
                            <div className="font-semibold text-gray-800">{slot.subject}{slot.batch ? ` (${slot.batch})` : ''}</div>
                            <div className="text-gray-500">{slot.faculty}{slot.room ? ` · ${slot.room}` : ''}</div>
                          </div>
                        )
                      })}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function TimetableVersionsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('timetable_versions')
  const [searchParams, setSearchParams] = useSearchParams()
  const [versions, setVersions] = useState<Version[]>([])
  const [canPublish, setCanPublish] = useState(false)
  const [keepDrafts, setKeepDrafts] = useState(10)
  const [selected, setSelected] = useState<number | null>(null)
  const [compareWith, setCompareWith] = useState<string>('live')
  const [diff, setDiff] = useState<Diff | null>(null)
  const [loading, setLoading] = useState(true)
  const [comparing, setComparing] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [renaming, setRenaming] = useState<number | null>(null)
  const [labelDraft, setLabelDraft] = useState('')
  const [confirming, setConfirming] = useState<'publish' | 'discard' | null>(null)

  const load = useCallback(async () => {
    const data = await apiRequest<ListPayload>('/api/timetable/versions')
    const rows = (data.versions || []).slice(0, 100).map(readVersion).filter((item) => item.id > 0)
    setVersions(rows)
    setCanPublish(data.can_publish === true)
    setKeepDrafts(Math.max(1, safeCount(data.keep_drafts) || 10))
    return rows
  }, [])

  useEffect(() => {
    setPageHeader('Timetable versions')
    if (!enabled) {
      setLoading(false)
      return
    }
    void load()
      .then((rows) => {
        const wanted = safeCount(searchParams.get('version'))
        const first = rows.find((row) => row.id === wanted) || rows.find((row) => row.status === 'draft') || rows[0]
        if (first) setSelected(first.id)
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
    // The query parameter is read once, when the page opens; later selections update it.
  }, [enabled, load, setPageHeader])

  const current = useMemo(() => versions.find((item) => item.id === selected) || null, [versions, selected])

  useEffect(() => {
    if (!current) {
      setDiff(null)
      return
    }
    // Compare a draft or archived version with the live timetable by default; the live one with its parent.
    if (current.status === 'published') {
      setCompareWith(current.parentVersionId ? String(current.parentVersionId) : 'live')
    } else {
      setCompareWith('live')
    }
  }, [current])

  useEffect(() => {
    if (!current) return
    let cancelled = false
    setComparing(true)
    setError('')
    const other = compareWith === 'live' ? 'live' : String(safeCount(compareWith) || 'live')
    void apiRequest<Record<string, unknown>>(`/api/timetable/versions/${current.id}/diff/${other}`)
      .then((data) => {
        if (!cancelled) setDiff(readDiff(data))
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(messageFrom(reason))
      })
      .finally(() => {
        if (!cancelled) setComparing(false)
      })
    return () => {
      cancelled = true
    }
  }, [current, compareWith])

  function choose(id: number) {
    setSelected(id)
    setConfirming(null)
    setSearchParams(id ? { version: String(id) } : {}, { replace: true })
  }

  async function act(method: 'POST' | 'DELETE' | 'PUT', path: string, body: Record<string, unknown> | null, done: string) {
    setBusy(path)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest(path, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: body ? JSON.stringify(body) : undefined,
      })
      setNotice(done)
      return true
    } catch (reason) {
      setError(messageFrom(reason))
      return false
    } finally {
      setBusy('')
    }
  }

  async function publish() {
    if (!current) return
    setConfirming(null)
    const ok = await act('POST', `/api/timetable/versions/${current.id}/publish`, null, `Version #${current.id} is now the live timetable.`)
    if (ok) {
      const rows = await load().catch(() => versions)
      setVersions(rows)
      setCompareWith('live')
    }
  }

  async function discard() {
    if (!current) return
    setConfirming(null)
    const ok = await act('DELETE', `/api/timetable/versions/${current.id}`, null, `Version #${current.id} was discarded.`)
    if (ok) {
      const rows = await load().catch(() => [])
      const next = rows.find((row) => row.status === 'draft') || rows[0]
      choose(next ? next.id : 0)
    }
  }

  async function rename(version: Version) {
    const label = labelDraft.trim()
    if (!label) {
      setRenaming(null)
      return
    }
    const ok = await act('PUT', `/api/timetable/versions/${version.id}`, { label }, 'Version renamed.')
    if (ok) {
      setRenaming(null)
      await load().catch(() => undefined)
    }
  }

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
        Timetable drafts and publishing are switched off for this institution. Generation writes straight to the live timetable, as before.
        Turn the <strong>Timetable drafts and publishing</strong> capability on under Settings → Capabilities to review changes before students see them.
      </section>
    )
  }

  const otherLabel = compareWith === 'live' ? 'the live timetable' : `version #${compareWith}`
  const actionable = current && current.status !== 'published'

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Timetable versions</h2>
            <p className="text-xs text-gray-500">
              Every generation run is saved as a draft. Compare it with what students and teachers see today, then publish it; the previous
              version is kept so you can roll back. The newest {keepDrafts} drafts are kept per institution.
            </p>
          </div>
          <Link to="/admin/timetable/generate" className={secondaryButton}><i className="fas fa-cogs mr-1" /> Generate a new draft</Link>
        </div>
        {error && <div className="mt-3"><FailureNotice message={error} /></div>}
        {notice && <div className="mt-3"><SuccessNotice message={notice} /></div>}
      </section>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-2 lg:grid-cols-[22rem_1fr]">
        <aside className="min-h-0 overflow-auto rounded-2xl border border-gray-200">
          {loading && <p className="p-6 text-center text-xs text-gray-500">Loading versions…</p>}
          {!loading && versions.length === 0 && (
            <p className="p-6 text-center text-xs text-gray-500">No versions yet. Generate a timetable to create the first draft.</p>
          )}
          <ul className="divide-y divide-gray-100">
            {versions.map((version) => (
              <li key={version.id}>
                <button
                  type="button"
                  onClick={() => choose(version.id)}
                  className={`w-full px-4 py-3 text-left hover:bg-indigo-50 ${version.id === selected ? 'bg-indigo-50' : ''}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold text-gray-900">#{version.id} {version.label}</span>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${statusStyle[version.status]}`}>{version.status}</span>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {version.cohorts.length} class{version.cohorts.length === 1 ? '' : 'es'} · {version.slotCount} slots · {version.solver}
                    {version.score.quality_score !== null ? ` · quality ${version.score.quality_score}` : ''}
                  </div>
                  <div className="text-[11px] text-gray-400">
                    {version.status === 'published' && version.publishedAt ? `Published ${version.publishedAt} by ${version.publishedBy}` : `Created ${version.createdAt} by ${version.createdBy}`}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="min-h-0 overflow-auto rounded-2xl border border-gray-200 p-4">
          {!current && !loading && <p className="p-6 text-center text-xs text-gray-500">Select a version to compare it.</p>}
          {current && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  {renaming === current.id ? (
                    <form
                      className="flex items-center gap-2"
                      onSubmit={(event) => {
                        event.preventDefault()
                        void rename(current)
                      }}
                    >
                      <input
                        autoFocus
                        maxLength={120}
                        value={labelDraft}
                        onChange={(event) => setLabelDraft(event.target.value)}
                        className="rounded-xl border border-gray-300 px-3 py-1.5 text-sm"
                        aria-label="Version name"
                      />
                      <button type="submit" className="rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white" disabled={Boolean(busy)}>Save</button>
                      <button type="button" className={secondaryButton} onClick={() => setRenaming(null)}>Cancel</button>
                    </form>
                  ) : (
                    <h3 className="flex items-center gap-2 text-base font-bold text-gray-900">
                      <span className="truncate">#{current.id} {current.label}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${statusStyle[current.status]}`}>{current.status}</span>
                      {canPublish && (
                        <button
                          type="button"
                          className="text-xs font-semibold text-indigo-600"
                          onClick={() => {
                            setLabelDraft(current.label)
                            setRenaming(current.id)
                          }}
                        >
                          Rename
                        </button>
                      )}
                    </h3>
                  )}
                  <p className="mt-1 text-xs text-gray-500">
                    {current.cohorts.map((cohort) => cohort.label).filter(Boolean).join(' · ') || 'No classes'}
                  </p>
                  <p className="text-xs text-gray-500">
                    {current.slotCount} slots
                    {current.score.quality_score !== null ? ` · quality ${current.score.quality_score}` : ''}
                    {current.score.rule_cost !== null ? ` · rule cost ${current.score.rule_cost}` : ''}
                    {current.score.unassigned > 0 ? ` · ${current.score.unassigned} unplaced` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-gray-600">
                    Compare with
                    <select value={compareWith} onChange={(event) => setCompareWith(event.target.value)} className="rounded-xl border border-gray-300 px-2 py-1.5 text-xs">
                      <option value="live">Live timetable</option>
                      {versions.filter((item) => item.id !== current.id).map((item) => (
                        <option key={item.id} value={String(item.id)}>#{item.id} {item.label} ({item.status})</option>
                      ))}
                    </select>
                  </label>
                  {canPublish && actionable && confirming === null && (
                    <>
                      <button type="button" className="rounded-xl bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white disabled:opacity-50" disabled={Boolean(busy)} onClick={() => setConfirming('publish')}>
                        <i className="fas fa-upload mr-1" /> {current.status === 'archived' ? 'Roll back to this' : 'Publish'}
                      </button>
                      <button type="button" className={`${secondaryButton} text-red-700`} disabled={Boolean(busy)} onClick={() => setConfirming('discard')}>
                        Discard
                      </button>
                    </>
                  )}
                </div>
              </div>

              {confirming && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                  <span>
                    {confirming === 'publish'
                      ? `Publish version #${current.id}? It replaces the live timetable for ${current.cohorts.length} class${current.cohorts.length === 1 ? '' : 'es'}; the current one is kept for rollback.`
                      : `Discard version #${current.id} and its ${current.slotCount} slots? This cannot be undone.`}
                  </span>
                  <span className="flex gap-2">
                    <button type="button" className={confirming === 'publish' ? 'rounded-xl bg-emerald-600 px-3 py-1.5 font-bold text-white' : 'rounded-xl bg-red-600 px-3 py-1.5 font-bold text-white'} disabled={Boolean(busy)} onClick={() => void (confirming === 'publish' ? publish() : discard())}>
                      {busy ? 'Working…' : confirming === 'publish' ? 'Yes, publish' : 'Yes, discard'}
                    </button>
                    <button type="button" className={secondaryButton} onClick={() => setConfirming(null)}>Cancel</button>
                  </span>
                </div>
              )}

              {comparing && <p className="text-xs text-gray-500">Comparing with {otherLabel}…</p>}
              {diff && !comparing && (
                <>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-gray-600">Against {otherLabel}:</span>
                    {Object.keys(kindLabel).map((kind) => (
                      <span key={kind} className={`rounded-full px-2 py-0.5 font-bold ${kindStyle[kind]}`}>{diff.totals[kind] || 0} {kindLabel[kind].toLowerCase()}</span>
                    ))}
                    {diff.other && diff.other.score.quality_score !== null && diff.version.score.quality_score !== null && (
                      <span className="text-gray-600">
                        Quality {diff.other.score.quality_score} → <strong>{diff.version.score.quality_score}</strong>
                        {diff.other.score.rule_cost !== null && diff.version.score.rule_cost !== null ? `, rule cost ${diff.other.score.rule_cost} → ${diff.version.score.rule_cost}` : ''}
                      </span>
                    )}
                  </div>

                  {diff.faculty.length > 0 && (
                    <section className="rounded-xl border border-gray-200">
                      <div className="border-b border-gray-100 bg-gray-50 px-3 py-2 text-xs font-bold text-gray-700">Teachers affected</div>
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-left text-gray-500">
                            <th className="px-3 py-1 font-semibold">Teacher</th>
                            <th className="px-3 py-1 font-semibold">Moved</th>
                            <th className="px-3 py-1 font-semibold">Added</th>
                            <th className="px-3 py-1 font-semibold">Removed</th>
                            <th className="px-3 py-1 font-semibold">Room</th>
                          </tr>
                        </thead>
                        <tbody>
                          {diff.faculty.map((row) => (
                            <tr key={row.faculty} className="border-t border-gray-100">
                              <td className="px-3 py-1 font-semibold text-gray-800">{row.faculty || 'Unassigned'}</td>
                              <td className="px-3 py-1">{row.moved}</td>
                              <td className="px-3 py-1">{row.added}</td>
                              <td className="px-3 py-1">{row.removed}</td>
                              <td className="px-3 py-1">{row.room_changed}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </section>
                  )}

                  {diff.cohorts.map((cohort) => {
                    const marks = highlights(cohort)
                    return (
                      <section key={`${cohort.course_id}-${cohort.class_id}-${cohort.division_id}`} className="space-y-3">
                        <h4 className="flex flex-wrap items-center gap-2 text-sm font-bold text-gray-800">
                          {cohort.label || `Class ${cohort.class_id} / division ${cohort.division_id}`}
                          {Object.entries(cohort.counts).filter(([kind]) => kind !== 'unchanged').map(([kind, count]) => (
                            <span key={kind} className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${kindStyle[kind]}`}>{count} {kindLabel[kind].toLowerCase()}</span>
                          ))}
                          {cohort.changes.length === 0 && <span className="text-xs font-normal text-gray-500">No changes</span>}
                        </h4>
                        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                          <WeekGrid title={compareWith === 'live' ? 'Live timetable' : `Version #${compareWith}`} slots={cohort.before} marks={marks.before} emptyText="Nothing timetabled for this class." />
                          <WeekGrid title={`Version #${current.id}`} slots={cohort.after} marks={marks.after} emptyText="This version has no slots for this class; publishing leaves it unchanged." />
                        </div>
                        {cohort.changes.length > 0 && (
                          <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200 text-xs">
                            {cohort.changes.map((change, index) => (
                              <li key={`${change.kind}-${change.subject}-${change.faculty}-${index}`} className="flex flex-wrap items-center gap-2 px-3 py-1.5">
                                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${kindStyle[change.kind]}`}>{kindLabel[change.kind]}</span>
                                <span className="font-semibold text-gray-800">{change.subject}{change.batch ? ` (${change.batch})` : ''}</span>
                                <span className="text-gray-500">{change.faculty}</span>
                                <span className="text-gray-600">
                                  {change.before ? `${change.before.day.slice(0, 3)} ${change.before.start_time}–${change.before.end_time}${change.before.room ? ` · ${change.before.room}` : ''}` : '—'}
                                  {' → '}
                                  {change.after ? `${change.after.day.slice(0, 3)} ${change.after.start_time}–${change.after.end_time}${change.after.room ? ` · ${change.after.room}` : ''}` : '—'}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </section>
                    )
                  })}
                </>
              )}
            </div>
          )}
        </main>
      </div>
    </section>
  )
}
