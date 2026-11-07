import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, optionsOf, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Batch = {
  id: number
  course_id: number
  course_name: string
  batch_name: string
  academic_year_id: number | null
  academic_year_name: string
  start_year: number
  end_year: number
  total_students: number
  current_semester: number
  is_active: boolean
}

type Draft = {
  course_id: number | null
  batch_name: string
  academic_year_id: number | null
  start_year: number
  end_year: number
  total_students: number
  current_semester: number
  is_active: boolean
}

const empty: Draft = { course_id: null, batch_name: '', academic_year_id: null, start_year: new Date().getFullYear(), end_year: new Date().getFullYear() + 3, total_students: 0, current_semester: 1, is_active: true }

function asBatch(value: Partial<Batch>): Batch | null {
  const id = asId(value.id)
  if (!id) return null
  return {
    id,
    course_id: asId(value.course_id),
    course_name: safeText(value.course_name, 100),
    batch_name: safeText(value.batch_name, 100),
    academic_year_id: asId(value.academic_year_id) || null,
    academic_year_name: safeText(value.academic_year_name, 50),
    start_year: safeCount(value.start_year),
    end_year: safeCount(value.end_year),
    total_students: safeCount(value.total_students),
    current_semester: safeCount(value.current_semester),
    is_active: value.is_active === true,
  }
}

export function BatchesPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Batch[]>([])
  const [courses, setCourses] = useState<Option[]>([])
  const [years, setYears] = useState<Option[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Batch | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ batches?: Partial<Batch>[]; courses?: Option[]; years?: Option[] }>('/api/batches')
    setRows((data.batches || []).map(asBatch).filter((row): row is Batch => row !== null))
    setCourses(optionsOf(data.courses))
    setYears(optionsOf(data.years))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Course Batches') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  function draftFrom(row: Batch): Draft {
    return { course_id: row.course_id, batch_name: row.batch_name, academic_year_id: row.academic_year_id, start_year: row.start_year, end_year: row.end_year, total_students: row.total_students, current_semester: row.current_semester, is_active: row.is_active }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/batches/${editor.id}` : '/api/batches', editor.draft)
      setNotice(editor.id ? 'Batch updated.' : 'Batch added.')
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
      await sendJson('DELETE', `/api/batches/${pending.id}`)
      setNotice('Batch deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Course Batches" subtitle="Student groups moving through a course" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: { ...empty, course_id: courses[0]?.id ?? null } })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Batch', 'Course', 'Years', 'Students', 'Actions']} count={rows.length} loading={loading} empty="No batches found.">
        {rows.map((row) => (
          <tr key={row.id}>
            <td className="px-4 py-2 font-semibold">{row.batch_name}</td>
            <td className="px-4 py-2 text-xs">{row.course_name}</td>
            <td className="px-4 py-2 text-xs">{row.start_year} – {row.end_year}</td>
            <td className="px-4 py-2 text-xs">{row.total_students}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: draftFrom(row) })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Batch' : 'Add Batch'} onClose={() => setEditor(null)}>
          <form className="grid grid-cols-2 gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="col-span-2 text-xs font-semibold">Name<input required maxLength={100} value={editor.draft.batch_name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, batch_name: event.target.value } })} className={fieldClass()} /></label>
            <label className="col-span-2 text-xs font-semibold">Course<select required value={editor.draft.course_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_id: Number(event.target.value) } })} className={fieldClass()}>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label>
            <label className="col-span-2 text-xs font-semibold">Academic year<select value={editor.draft.academic_year_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, academic_year_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Start year<input required type="number" min={1990} max={2100} value={editor.draft.start_year} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, start_year: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">End year<input required type="number" min={1990} max={2100} value={editor.draft.end_year} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, end_year: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Students<input required type="number" min={0} max={10000} value={editor.draft.total_students} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, total_students: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Current semester<input required type="number" min={1} max={40} value={editor.draft.current_semester} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, current_semester: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="col-span-2 inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_active} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_active: event.target.checked } })} className="mr-2" />Active</label>
            <button type="submit" disabled={saving} className="col-span-2 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete batch?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Delete {pending.batch_name}?</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
