import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { todayInput } from '../../../shared/dates'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, optionsOf, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Group = {
  id: number
  course_id: number
  course_name: string
  class_id: number
  class_name: string
  division_id: number | null
  division_name: string
  academic_year_id: number
  academic_year_name: string
  semester_id: number | null
  semester_name: string
  name: string
  capacity: number | null
  is_active: boolean
  member_count: number
  slot_count: number
}

type Draft = {
  course_id: number | null
  class_id: number | null
  division_id: number | null
  academic_year_id: number | null
  semester_id: number | null
  name: string
  capacity: number | null
  is_active: boolean
}

type Student = { id: number; name: string; roll_number: string; lab_batch_group_id: number | null }
type Sibling = { id: number; name: string; capacity: number | null }
type Roster = { group: Group; siblings: Sibling[]; students: Student[]; chosen: Set<number>; on_date: string }

const empty: Draft = { course_id: null, class_id: null, division_id: null, academic_year_id: null, semester_id: null, name: '', capacity: null, is_active: true }

function asGroup(value: Partial<Group>): Group | null {
  const id = asId(value.id)
  if (!id) return null
  return {
    id,
    course_id: asId(value.course_id),
    course_name: safeText(value.course_name, 100),
    class_id: asId(value.class_id),
    class_name: safeText(value.class_name, 100),
    division_id: asId(value.division_id) || null,
    division_name: safeText(value.division_name, 100),
    academic_year_id: asId(value.academic_year_id),
    academic_year_name: safeText(value.academic_year_name, 50),
    semester_id: asId(value.semester_id) || null,
    semester_name: safeText(value.semester_name, 50),
    name: safeText(value.name, 20),
    capacity: safeCount(value.capacity) || null,
    is_active: value.is_active === true,
    member_count: safeCount(value.member_count),
    slot_count: safeCount(value.slot_count),
  }
}

function asStudent(value: Partial<Student>): Student | null {
  const id = asId(value.id)
  if (!id) return null
  return { id, name: safeText(value.name, 100), roll_number: safeText(value.roll_number, 30), lab_batch_group_id: asId(value.lab_batch_group_id) || null }
}

function cohortLabel(row: Group) {
  return [row.class_name, row.division_name ? `Div ${row.division_name}` : 'whole class', row.academic_year_name, row.semester_name].filter(Boolean).join(' · ')
}

export function LabBatchesPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Group[]>([])
  const [courses, setCourses] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [divisions, setDivisions] = useState<Option[]>([])
  const [years, setYears] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<Option[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [roster, setRoster] = useState<Roster | null>(null)
  const [pending, setPending] = useState<Group | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ groups?: Partial<Group>[]; courses?: Option[]; classes?: Option[]; divisions?: Option[]; years?: Option[]; semesters?: Option[] }>('/api/lab-batches')
    setRows((data.groups || []).map(asGroup).filter((row): row is Group => row !== null))
    setCourses(optionsOf(data.courses))
    setClasses(optionsOf(data.classes))
    setDivisions(optionsOf(data.divisions))
    setYears(optionsOf(data.years))
    setSemesters(optionsOf(data.semesters))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Lab Batches') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  function draftFrom(row: Group): Draft {
    return { course_id: row.course_id, class_id: row.class_id, division_id: row.division_id, academic_year_id: row.academic_year_id, semester_id: row.semester_id, name: row.name, capacity: row.capacity, is_active: row.is_active }
  }

  async function run(action: () => Promise<void>, done: string) {
    setSaving(true)
    setError('')
    try {
      await action()
      setNotice(done)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    await run(async () => {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/lab-batches/${editor.id}` : '/api/lab-batches', editor.draft)
      setEditor(null)
      await load()
    }, editor.id ? 'Lab batch updated.' : 'Lab batch added.')
  }

  async function onDelete() {
    if (!pending) return
    await run(async () => {
      await sendJson('DELETE', `/api/lab-batches/${pending.id}`)
      setPending(null)
      await load()
    }, 'Lab batch deleted.')
  }

  async function openRoster(row: Group) {
    setError('')
    try {
      const data = await apiRequest<{ group?: Partial<Group>; siblings?: Partial<Sibling>[]; students?: Partial<Student>[] }>(`/api/lab-batches/${row.id}/members`)
      const group = asGroup(data.group || {}) || row
      const students = (data.students || []).map(asStudent).filter((student): student is Student => student !== null)
      const siblings = (data.siblings || []).map((s) => ({ id: asId(s.id), name: safeText(s.name, 20), capacity: safeCount(s.capacity) || null })).filter((s) => s.id > 0)
      setRoster({ group, siblings, students, chosen: new Set(students.filter((s) => s.lab_batch_group_id === group.id).map((s) => s.id)), on_date: todayInput() })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  function toggle(studentId: number) {
    if (!roster) return
    const chosen = new Set(roster.chosen)
    if (chosen.has(studentId)) chosen.delete(studentId)
    else chosen.add(studentId)
    setRoster({ ...roster, chosen })
  }

  async function saveRoster() {
    if (!roster) return
    const target = roster
    await run(async () => {
      await sendJson('PUT', `/api/lab-batches/${target.group.id}/members`, { student_ids: Array.from(target.chosen), on_date: target.on_date })
      setRoster(null)
      await load()
    }, `Members of ${target.group.name} saved.`)
  }

  async function splitRoster() {
    if (!roster) return
    const target = roster
    await run(async () => {
      await sendJson('POST', `/api/lab-batches/${target.group.id}/split`, { on_date: target.on_date })
      setRoster(null)
      await load()
    }, 'Students dealt across the batches by roll number.')
  }

  const siblingName = (id: number | null) => (id === null ? '' : roster?.siblings.find((s) => s.id === id)?.name || (id === roster?.group.id ? roster.group.name : `#${id}`))

  return (
    <Screen title="Lab Batches" subtitle="Groups a division is split into for practicals" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: { ...empty, course_id: courses[0]?.id ?? null, class_id: classes[0]?.id ?? null, academic_year_id: years[0]?.id ?? null } })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Batch', 'Course', 'Cohort', 'Students', 'Slots', 'Actions']} count={rows.length} loading={loading} empty="No lab batches yet. Add two or more per division, then assign students.">
        {rows.map((row) => (
          <tr key={row.id} className={row.is_active ? '' : 'text-gray-400'}>
            <td className="px-4 py-2 font-semibold">{row.name}{row.capacity ? <span className="ml-1 text-xs font-normal text-gray-500">/ {row.capacity}</span> : null}</td>
            <td className="px-4 py-2 text-xs">{row.course_name}</td>
            <td className="px-4 py-2 text-xs">{cohortLabel(row)}</td>
            <td className="px-4 py-2 text-xs">
              <button type="button" className="text-indigo-600 hover:underline" onClick={() => void openRoster(row)}>{row.member_count} student{row.member_count === 1 ? '' : 's'}</button>
            </td>
            <td className="px-4 py-2 text-xs">{row.slot_count}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: draftFrom(row) })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Lab Batch' : 'Add Lab Batch'} onClose={() => setEditor(null)}>
          <form className="grid grid-cols-2 gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="text-xs font-semibold">Name<input required maxLength={20} placeholder="A1" value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Capacity<input type="number" min={1} max={500} value={editor.draft.capacity ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, capacity: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()} /></label>
            {editor.id ? (
              <p className="col-span-2 text-xs text-gray-500">The class, division and year cannot change once a batch exists; add a new batch instead.</p>
            ) : (
              <>
                <label className="col-span-2 text-xs font-semibold">Course<select required value={editor.draft.course_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_id: Number(event.target.value) } })} className={fieldClass()}>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label>
                <label className="text-xs font-semibold">Class<select required value={editor.draft.class_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, class_id: Number(event.target.value) } })} className={fieldClass()}>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label className="text-xs font-semibold">Division<select value={editor.draft.division_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, division_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">Whole class</option>{divisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label className="text-xs font-semibold">Academic year<select required value={editor.draft.academic_year_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, academic_year_id: Number(event.target.value) } })} className={fieldClass()}>{years.map((year) => <option key={year.id} value={year.id}>{year.name}</option>)}</select></label>
              </>
            )}
            <label className="text-xs font-semibold">Semester<select value={editor.draft.semester_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">Whole year</option>{semesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="col-span-2 inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_active} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_active: event.target.checked } })} className="mr-2" />Active</label>
            <button type="submit" disabled={saving} className="col-span-2 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {roster ? (
        <Dialog title={`Students in ${roster.group.name}`} onClose={() => setRoster(null)}>
          <p className="text-xs text-gray-500">{cohortLabel(roster.group)}. Ticked students are in this batch; a student ticked here leaves their other batch on the date below, and attendance already marked stays with the batch it was marked in.</p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-xs font-semibold">Applies from<input type="date" value={roster.on_date} onChange={(event) => setRoster({ ...roster, on_date: event.target.value })} className={fieldClass()} /></label>
            <span className="text-xs text-gray-600">{roster.chosen.size} chosen{roster.group.capacity ? ` of ${roster.group.capacity}` : ''}</span>
            {permissions.change && roster.siblings.length >= 2 ? <button type="button" disabled={saving} className="rounded border border-indigo-600 px-3 py-1.5 text-xs text-indigo-700 disabled:opacity-60" onClick={() => void splitRoster()}>Deal all by roll number across {roster.siblings.length} batches</button> : null}
          </div>
          <div className="mt-3 max-h-80 overflow-auto rounded border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-gray-50 text-left text-xs text-gray-600"><tr><th className="px-3 py-2">In</th><th className="px-3 py-2">Roll</th><th className="px-3 py-2">Student</th><th className="px-3 py-2">Now in</th></tr></thead>
              <tbody className="divide-y divide-gray-100">
                {roster.students.length === 0 ? <tr><td colSpan={4} className="px-3 py-4 text-center text-gray-500">No students in this class and division.</td></tr> : null}
                {roster.students.map((student) => (
                  <tr key={student.id}>
                    <td className="px-3 py-1.5"><input type="checkbox" disabled={!permissions.change} checked={roster.chosen.has(student.id)} onChange={() => toggle(student.id)} /></td>
                    <td className="px-3 py-1.5 text-xs">{student.roll_number}</td>
                    <td className="px-3 py-1.5">{student.name}</td>
                    <td className="px-3 py-1.5 text-xs text-gray-500">{siblingName(student.lab_batch_group_id) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {permissions.change ? <button type="button" disabled={saving} className="mt-4 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60" onClick={() => void saveRoster()}>{saving ? 'Saving…' : 'Save members'}</button> : null}
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete lab batch?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Delete {pending.name} ({cohortLabel(pending)})? Its {pending.slot_count} timetable slot{pending.slot_count === 1 ? '' : 's'} will become whole-division slots.</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
