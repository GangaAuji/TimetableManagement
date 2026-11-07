import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeText } from '../../../shared/security/sanitize'
import { asId, optionsOf, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Semester = {
  id: number
  academic_year_id: number
  academic_year_name: string
  semester_number: number
  semester_name: string
  start_date: string
  end_date: string
  class_id: number | null
  class_name: string
  is_current: boolean
  min_credits: number
  max_credits: number
}

type Draft = {
  academic_year_id: number | null
  semester_number: number
  semester_name: string
  start_date: string
  end_date: string
  class_id: number | null
  is_current: boolean
  min_credits: number
  max_credits: number
}

const empty: Draft = { academic_year_id: null, semester_number: 1, semester_name: '', start_date: '', end_date: '', class_id: null, is_current: false, min_credits: 18, max_credits: 30 }

function asSemester(value: Partial<Semester>): Semester | null {
  const id = asId(value.id)
  if (!id) return null
  return {
    id,
    academic_year_id: asId(value.academic_year_id),
    academic_year_name: safeText(value.academic_year_name, 50),
    semester_number: asId(value.semester_number),
    semester_name: safeText(value.semester_name, 100),
    start_date: safeText(value.start_date, 10),
    end_date: safeText(value.end_date, 10),
    class_id: asId(value.class_id) || null,
    class_name: safeText(value.class_name, 100),
    is_current: value.is_current === true,
    min_credits: Number(value.min_credits) || 0,
    max_credits: Number(value.max_credits) || 0,
  }
}

export function SemestersPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Semester[]>([])
  const [years, setYears] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Semester | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ semesters?: Partial<Semester>[]; years?: Option[]; classes?: Option[] }>('/api/semesters')
    setRows((data.semesters || []).map(asSemester).filter((row): row is Semester => row !== null))
    setYears(optionsOf(data.years))
    setClasses(optionsOf(data.classes))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Semesters') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/semesters/${editor.id}` : '/api/semesters', editor.draft)
      setNotice(editor.id ? 'Semester updated.' : 'Semester added.')
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
    try {
      await sendJson('DELETE', `/api/semesters/${pending.id}`)
      setNotice('Semester deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Semesters" subtitle="Periods inside an academic year" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: { ...empty, academic_year_id: years[0]?.id ?? null } })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Semester', 'Year', 'Dates', 'Class', 'Actions']} count={rows.length} loading={loading} empty="No semesters found.">
        {rows.map((row) => (
          <tr key={row.id}>
            <td className="px-4 py-2"><div className="font-semibold">{row.semester_name}</div><div className="text-[10px] text-gray-500">Semester {row.semester_number}</div></td>
            <td className="px-4 py-2 text-xs">{row.academic_year_name}</td>
            <td className="px-4 py-2 text-xs">{row.start_date} – {row.end_date}</td>
            <td className="px-4 py-2 text-xs">{row.class_name || '—'}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: { academic_year_id: row.academic_year_id, semester_number: row.semester_number, semester_name: row.semester_name, start_date: row.start_date, end_date: row.end_date, class_id: row.class_id, is_current: row.is_current, min_credits: row.min_credits, max_credits: row.max_credits } })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Semester' : 'Add Semester'} onClose={() => setEditor(null)}>
          <form className="grid grid-cols-2 gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="col-span-2 text-xs font-semibold">Name<input required maxLength={100} value={editor.draft.semester_name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Number<input required type="number" min={1} max={20} value={editor.draft.semester_number} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_number: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Year<select required value={editor.draft.academic_year_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, academic_year_id: Number(event.target.value) } })} className={fieldClass()}>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Start<input required type="date" value={editor.draft.start_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, start_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">End<input required type="date" value={editor.draft.end_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, end_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Class<select value={editor.draft.class_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, class_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Min credits<input required type="number" min={0} max={100} step="0.1" value={editor.draft.min_credits} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, min_credits: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Max credits<input required type="number" min={0} max={100} step="0.1" value={editor.draft.max_credits} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, max_credits: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="col-span-2 inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_current} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_current: event.target.checked } })} className="mr-2" />Current</label>
            <button type="submit" disabled={saving} className="col-span-2 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete semester?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Delete {pending.semester_name}?</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
