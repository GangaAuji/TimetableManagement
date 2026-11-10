import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { useCapability } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Term = {
  id: number
  name: string
  kind: string
  start_date: string
  end_date: string
  academic_year_id: number
  year_name: string
  semester_id: number | null
  semester_name: string
}
type Draft = { name: string; kind: string; start_date: string; end_date: string; academic_year_id: number | ''; semester_id: number | '' }
type Week = { name: string; week_start: string; teaching_days: number }
type Totals = { scheduled: number; conducted: number; attended: number; from: string; to: string }
type Payload = {
  terms?: Partial<Term>[]
  weeks?: Partial<Week>[]
  totals?: Totals | null
  years?: Option[]
  semesters?: { id?: number; name?: string; academic_year_id?: number }[]
  permissions?: Partial<Permissions>
}

const empty: Draft = { name: '', kind: 'teaching', start_date: '', end_date: '', academic_year_id: '', semester_id: '' }
const kindLabel: Record<string, string> = { teaching: 'Teaching', exam: 'Exam', break: 'Break', internship: 'Internship' }

function asTerm(value: Partial<Term> | null | undefined): Term | null {
  const id = asId(value?.id)
  const name = safeText(value?.name, 80)
  if (!id || !name) return null
  return {
    id,
    name,
    kind: kindLabel[safeText(value?.kind, 20)] ? safeText(value?.kind, 20) : 'teaching',
    start_date: safeText(value?.start_date, 10),
    end_date: safeText(value?.end_date, 10),
    academic_year_id: asId(value?.academic_year_id),
    year_name: safeText(value?.year_name, 20),
    semester_id: asId(value?.semester_id) || null,
    semester_name: safeText(value?.semester_name, 50),
  }
}

export function TermsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('academic_terms')
  const [rows, setRows] = useState<Term[]>([])
  const [weeks, setWeeks] = useState<Week[]>([])
  const [totals, setTotals] = useState<Totals | null>(null)
  const [years, setYears] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<{ id: number; name: string; academicYearId: number }[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Term | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<Payload>('/api/academic-terms')
    setRows((data.terms || []).map(asTerm).filter((row): row is Term => row !== null))
    setWeeks((data.weeks || []).slice(0, 8).map((week) => ({
      name: safeText(week.name, 80),
      week_start: safeText(week.week_start, 10),
      teaching_days: safeCount(week.teaching_days),
    })))
    setTotals(data.totals && typeof data.totals === 'object' ? data.totals : null)
    setYears((data.years || []).map((year) => ({ id: asId(year.id), name: safeText(year.name, 20) })).filter((year) => year.id > 0))
    setSemesters((data.semesters || []).map((semester) => ({
      id: asId(semester.id),
      name: safeText(semester.name, 50),
      academicYearId: asId(semester.academic_year_id),
    })).filter((semester) => semester.id > 0))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Academic calendar') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false))
  }, [enabled])

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      const saved = await sendJson<{ cancelled_sessions?: number }>(editor.id ? 'PUT' : 'POST', editor.id ? `/api/academic-terms/${editor.id}` : '/api/academic-terms', {
        name: editor.draft.name,
        kind: editor.draft.kind,
        start_date: editor.draft.start_date,
        end_date: editor.draft.end_date,
        academic_year_id: Number(editor.draft.academic_year_id),
        semester_id: editor.draft.semester_id === '' ? null : Number(editor.draft.semester_id),
      })
      const cancelled = safeCount(saved.cancelled_sessions)
      setNotice(cancelled ? `Term saved. ${cancelled} lecture(s) outside teaching were cancelled.` : 'Term saved.')
      setEditor(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function onDelete() {
    if (!pending) return
    setSaving(true)
    setError('')
    try {
      await sendJson('DELETE', `/api/academic-terms/${pending.id}`)
      setNotice('Term deleted. Lectures already cancelled stay cancelled.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
        The academic calendar is an optional capability, switched off for this institution. Turn it on under Settings → Capabilities.
      </section>
    )
  }

  const yearId = editor ? Number(editor.draft.academic_year_id) : 0
  const semesterChoices = semesters.filter((semester) => !yearId || semester.academicYearId === yearId)

  return (
    <Screen title="Academic calendar" subtitle="Teaching, exam, break and internship terms. The timetable is generated only inside teaching terms." action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: empty })} /> : null}>
      <Banners error={error} notice={notice} />
      {totals && (
        <section className="grid grid-cols-3 gap-2">
          <div className="rounded-2xl border border-gray-200 bg-white px-4 py-3"><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Scheduled</p><p className="text-lg font-bold text-gray-800">{totals.scheduled}</p><p className="text-[11px] text-gray-500">Teaching-day slots, {totals.from} – {totals.to}</p></div>
          <div className="rounded-2xl border border-gray-200 bg-white px-4 py-3"><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Conducted</p><p className="text-lg font-bold text-gray-800">{totals.conducted}</p><p className="text-[11px] text-gray-500">Lectures held</p></div>
          <div className="rounded-2xl border border-gray-200 bg-white px-4 py-3"><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">Attended</p><p className="text-lg font-bold text-gray-800">{totals.attended}</p><p className="text-[11px] text-gray-500">Present or late marks</p></div>
        </section>
      )}
      <Table headers={['Term', 'Kind', 'Dates', 'Year', 'Actions']} count={rows.length} loading={loading} empty="No terms yet. Until you add one, timetables and attendance keep today's behaviour.">
        {rows.map((term) => (
          <tr key={term.id}>
            <td className="px-4 py-2 font-semibold text-gray-900">{term.name}</td>
            <td className="px-4 py-2 text-xs text-gray-700">{kindLabel[term.kind] || term.kind}</td>
            <td className="px-4 py-2 text-xs text-gray-600">{term.start_date} – {term.end_date}</td>
            <td className="px-4 py-2 text-xs text-gray-600">{term.year_name}{term.semester_name ? ` · ${term.semester_name}` : ''}</td>
            <RowActions
              canChange={permissions.change}
              canDelete={permissions.delete}
              onEdit={() => setEditor({ id: term.id, draft: { name: term.name, kind: term.kind, start_date: term.start_date, end_date: term.end_date, academic_year_id: term.academic_year_id, semester_id: term.semester_id ?? '' } })}
              onDelete={() => setPending(term)}
            />
          </tr>
        ))}
      </Table>
      {weeks.length > 0 && (
        <p className="px-1 text-xs text-gray-500">
          Coming teaching weeks: {weeks.map((week) => `${week.week_start} (${week.teaching_days}d)`).join(', ')}.
        </p>
      )}
      {editor ? (
        <Dialog title={editor.id ? 'Edit term' : 'Add term'} onClose={() => setEditor(null)}>
          <form className="grid gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="text-xs font-semibold text-gray-700">Name<input required maxLength={80} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">Kind
              <select value={editor.draft.kind} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, kind: event.target.value } })} className={fieldClass()}>
                {Object.entries(kindLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-gray-700">Academic year
              <select required value={editor.draft.academic_year_id} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, academic_year_id: Number(event.target.value), semester_id: '' } })} className={fieldClass()}>
                <option value="">Select</option>
                {years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-gray-700">Semester (optional)
              <select value={editor.draft.semester_id} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_id: event.target.value === '' ? '' : Number(event.target.value) } })} className={fieldClass()}>
                <option value="">Whole year</option>
                {semesterChoices.map((semester) => <option key={semester.id} value={semester.id}>{semester.name}</option>)}
              </select>
            </label>
            <label className="text-xs font-semibold text-gray-700">Start<input required type="date" value={editor.draft.start_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, start_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">End<input required type="date" value={editor.draft.end_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, end_date: event.target.value } })} className={fieldClass()} /></label>
            <button type="submit" disabled={saving} className="rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? (
        <Dialog title="Delete term?" onClose={() => setPending(null)}>
          <p className="text-sm text-gray-600">Delete {pending.name}? Lectures cancelled because of it are not restored.</p>
          <button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button>
        </Dialog>
      ) : null}
    </Screen>
  )
}
