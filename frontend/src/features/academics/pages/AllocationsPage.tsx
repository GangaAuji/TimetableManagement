import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, optionsOf, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

const allocationTypes = ['Regular', 'Tutorial', 'Lab', 'Guest'] as const

type Allocation = {
  id: number
  faculty_id: number
  faculty_name: string
  subject_id: number
  subject_name: string
  class_id: number | null
  class_name: string
  division_id: number | null
  semester_id: number | null
  course_batch_id: number | null
  batch_name: string
  allocated_hours: number
  workload_percentage: number
  is_primary: boolean
  allocation_type: string
  start_date: string
  end_date: string
  notes: string
}

type Draft = {
  faculty_id: number | null
  subject_id: number | null
  class_id: number | null
  division_id: number | null
  semester_id: number | null
  course_batch_id: number | null
  allocated_hours: number
  workload_percentage: number
  is_primary: boolean
  allocation_type: (typeof allocationTypes)[number]
  start_date: string
  end_date: string
  notes: string
}

const empty: Draft = {
  faculty_id: null, subject_id: null, class_id: null, division_id: null, semester_id: null, course_batch_id: null,
  allocated_hours: 0, workload_percentage: 100, is_primary: true, allocation_type: 'Regular', start_date: '', end_date: '', notes: '',
}

function asAllocation(value: Partial<Allocation>): Allocation | null {
  const id = asId(value.id)
  if (!id) return null
  return {
    id,
    faculty_id: asId(value.faculty_id),
    faculty_name: safeText(value.faculty_name, 160),
    subject_id: asId(value.subject_id),
    subject_name: safeText(value.subject_name, 150),
    class_id: asId(value.class_id) || null,
    class_name: safeText(value.class_name, 100),
    division_id: asId(value.division_id) || null,
    semester_id: asId(value.semester_id) || null,
    course_batch_id: asId(value.course_batch_id) || null,
    batch_name: safeText(value.batch_name, 100),
    allocated_hours: safeCount(value.allocated_hours),
    workload_percentage: safeCount(value.workload_percentage),
    is_primary: value.is_primary === true,
    allocation_type: safeText(value.allocation_type, 20),
    start_date: safeText(value.start_date, 10),
    end_date: safeText(value.end_date, 10),
    notes: safeText(value.notes, 500),
  }
}

export function AllocationsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Allocation[]>([])
  const [faculty, setFaculty] = useState<Option[]>([])
  const [subjects, setSubjects] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [divisions, setDivisions] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<Option[]>([])
  const [batches, setBatches] = useState<Option[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Allocation | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ allocations?: Partial<Allocation>[]; faculty?: Option[]; subjects?: Option[]; classes?: Option[]; divisions?: Option[]; semesters?: Option[]; batches?: Option[] }>('/api/allocations')
    setRows((data.allocations || []).map(asAllocation).filter((row): row is Allocation => row !== null))
    setFaculty(optionsOf(data.faculty))
    setSubjects(optionsOf(data.subjects))
    setClasses(optionsOf(data.classes))
    setDivisions(optionsOf(data.divisions))
    setSemesters(optionsOf(data.semesters))
    setBatches(optionsOf(data.batches))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Faculty Allocations') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  function draftFrom(row: Allocation): Draft {
    return {
      faculty_id: row.faculty_id, subject_id: row.subject_id, class_id: row.class_id, division_id: row.division_id,
      semester_id: row.semester_id, course_batch_id: row.course_batch_id, allocated_hours: row.allocated_hours,
      workload_percentage: row.workload_percentage, is_primary: row.is_primary,
      allocation_type: allocationTypes.includes(row.allocation_type as 'Regular') ? row.allocation_type as Draft['allocation_type'] : 'Regular',
      start_date: row.start_date, end_date: row.end_date, notes: row.notes,
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      const body = { ...editor.draft, start_date: editor.draft.start_date || null, end_date: editor.draft.end_date || null }
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/allocations/${editor.id}` : '/api/allocations', body)
      setNotice(editor.id ? 'Allocation updated.' : 'Allocation added.')
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
      await sendJson('DELETE', `/api/allocations/${pending.id}`)
      setNotice('Allocation deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Faculty Allocations" subtitle="Who teaches each subject" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: empty })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Faculty', 'Subject', 'Class', 'Hours', 'Actions']} count={rows.length} loading={loading} empty="No allocations found.">
        {rows.map((row) => (
          <tr key={row.id}>
            <td className="px-4 py-2 font-semibold">{row.faculty_name}</td>
            <td className="px-4 py-2 text-xs">{row.subject_name}</td>
            <td className="px-4 py-2 text-xs">{row.class_name || '—'}</td>
            <td className="px-4 py-2 text-xs">{row.allocated_hours}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: draftFrom(row) })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Allocation' : 'Add Allocation'} onClose={() => setEditor(null)}>
          <form className="grid grid-cols-2 gap-3" onSubmit={(event) => void onSave(event)}>
            <label className="col-span-2 text-xs font-semibold">Faculty<select required value={editor.draft.faculty_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, faculty_id: Number(event.target.value) } })} className={fieldClass()}><option value="">Select...</option>{faculty.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="col-span-2 text-xs font-semibold">Subject<select required value={editor.draft.subject_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, subject_id: Number(event.target.value) } })} className={fieldClass()}><option value="">Select...</option>{subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Class<select value={editor.draft.class_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, class_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Division<select value={editor.draft.division_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, division_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{divisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Semester<select value={editor.draft.semester_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{semesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Batch<select value={editor.draft.course_batch_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_batch_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{batches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Type<select value={editor.draft.allocation_type} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, allocation_type: event.target.value as Draft['allocation_type'] } })} className={fieldClass()}>{allocationTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
            <label className="text-xs font-semibold">Hours<input type="number" min={0} max={80} step="0.1" value={editor.draft.allocated_hours} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, allocated_hours: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Workload %<input type="number" min={0} max={100} step="0.1" value={editor.draft.workload_percentage} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, workload_percentage: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Start<input type="date" value={editor.draft.start_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, start_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">End<input type="date" value={editor.draft.end_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, end_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="col-span-2 text-xs font-semibold">Notes<textarea rows={2} maxLength={500} value={editor.draft.notes} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, notes: event.target.value } })} className={fieldClass()} /></label>
            <label className="col-span-2 inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_primary} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_primary: event.target.checked } })} className="mr-2" />Primary teacher</label>
            <button type="submit" disabled={saving} className="col-span-2 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete allocation?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Remove {pending.faculty_name} from {pending.subject_name}?</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
