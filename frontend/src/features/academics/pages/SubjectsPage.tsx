import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, optionsOf, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

const courseTypes = ['Core', 'Elective', 'Core Practical', 'Project'] as const
const modes = ['Theory', 'Practical', 'Both'] as const

type Subject = {
  id: number
  name: string
  course_code: string
  course_id: number
  course_name: string
  class_id: number | null
  class_name: string
  semester_id: number | null
  semester_name: string
  course_type: string
  theory_practical: string
  credits: number
  theory_credits: number
  practical_credits: number
  marks: number
  theory_marks: number
  practical_marks: number
  lectures_per_week: number
  practical_hours_per_week: number
  is_elective: boolean
  description: string
  syllabus_url: string
  faculty_names: string
}

type Draft = Omit<Subject, 'id' | 'course_name' | 'class_name' | 'semester_name' | 'marks' | 'credits' | 'faculty_names'>

const empty: Draft = {
  name: '', course_code: '', course_id: 0, class_id: null, semester_id: null, course_type: 'Core',
  theory_practical: 'Theory', theory_credits: 3, practical_credits: 0, theory_marks: 100, practical_marks: 0,
  lectures_per_week: 3, practical_hours_per_week: 0, is_elective: false, description: '', syllabus_url: '',
}

function asSubject(value: Partial<Subject>): Subject | null {
  const id = asId(value.id)
  const name = safeText(value.name, 150)
  if (!id || !name) return null
  return {
    id, name, course_code: safeText(value.course_code, 20), course_id: asId(value.course_id),
    course_name: safeText(value.course_name, 100), class_id: asId(value.class_id) || null,
    class_name: safeText(value.class_name, 100), semester_id: asId(value.semester_id) || null,
    semester_name: safeText(value.semester_name, 100), course_type: safeText(value.course_type, 40),
    theory_practical: safeText(value.theory_practical, 20), credits: safeCount(value.credits),
    theory_credits: Number(value.theory_credits) || 0, practical_credits: Number(value.practical_credits) || 0,
    marks: safeCount(value.marks), theory_marks: safeCount(value.theory_marks), practical_marks: safeCount(value.practical_marks),
    lectures_per_week: safeCount(value.lectures_per_week), practical_hours_per_week: safeCount(value.practical_hours_per_week),
    is_elective: value.is_elective === true, description: safeText(value.description, 4000),
    syllabus_url: safeText(value.syllabus_url, 500), faculty_names: safeText(value.faculty_names, 500),
  }
}

export function SubjectsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Subject[]>([])
  const [courses, setCourses] = useState<Option[]>([])
  const [classes, setClasses] = useState<Option[]>([])
  const [semesters, setSemesters] = useState<Option[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [query, setQuery] = useState('')
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Subject | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ subjects?: Partial<Subject>[]; courses?: Option[]; classes?: Option[]; semesters?: Option[] }>('/api/subjects')
    setRows((data.subjects || []).map(asSubject).filter((row): row is Subject => row !== null))
    setCourses(optionsOf(data.courses))
    setClasses(optionsOf(data.classes))
    setSemesters(optionsOf(data.semesters))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Subjects') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  const visible = rows.filter((row) => {
    const needle = query.trim().toLowerCase()
    return !needle || `${row.name} ${row.course_code} ${row.course_name}`.toLowerCase().includes(needle)
  })

  function draftFrom(row: Subject): Draft {
    return {
      name: row.name, course_code: row.course_code, course_id: row.course_id, class_id: row.class_id,
      semester_id: row.semester_id, course_type: courseTypes.includes(row.course_type as 'Core') ? row.course_type as Draft['course_type'] : 'Core',
      theory_practical: modes.includes(row.theory_practical as 'Theory') ? row.theory_practical as Draft['theory_practical'] : 'Theory',
      theory_credits: row.theory_credits, practical_credits: row.practical_credits, theory_marks: row.theory_marks,
      practical_marks: row.practical_marks, lectures_per_week: row.lectures_per_week,
      practical_hours_per_week: row.practical_hours_per_week, is_elective: row.is_elective,
      description: row.description, syllabus_url: row.syllabus_url,
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/subjects/${editor.id}` : '/api/subjects', editor.draft)
      setNotice(editor.id ? 'Subject updated.' : 'Subject added.')
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
      await sendJson('DELETE', `/api/subjects/${pending.id}`)
      setNotice('Subject deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Subjects" subtitle="Curriculum items for each course" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: { ...empty, course_id: courses[0]?.id ?? 0 } })} /> : null}>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subjects..." className="w-full rounded border border-gray-300 px-3 py-2 text-sm md:w-72" />
      <Banners error={error} notice={notice} />
      <Table headers={['Subject', 'Course', 'Type', 'Faculty', 'Actions']} count={visible.length} loading={loading} empty="No subjects found.">
        {visible.map((row) => (
          <tr key={row.id}>
            <td className="px-4 py-2"><div className="font-semibold">{row.name}</div><div className="font-mono text-[10px] text-gray-500">{row.course_code}</div></td>
            <td className="px-4 py-2 text-xs">{row.course_name}</td>
            <td className="px-4 py-2 text-xs">{row.course_type} · {row.theory_practical}</td>
            <td className="px-4 py-2 text-xs">{row.faculty_names || '—'}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: draftFrom(row) })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Subject' : 'Add Subject'} onClose={() => setEditor(null)}>
          <form className="grid grid-cols-2 gap-3" onSubmit={(event) => void onSave(event)}>
            <label className="col-span-2 text-xs font-semibold">Name<input required maxLength={150} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Code<input required maxLength={20} value={editor.draft.course_code} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_code: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Type<select value={editor.draft.course_type} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_type: event.target.value as Draft['course_type'] } })} className={fieldClass()}>{courseTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
            <label className="col-span-2 text-xs font-semibold">Course<select required value={editor.draft.course_id || ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, course_id: Number(event.target.value) } })} className={fieldClass()}>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Class<select value={editor.draft.class_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, class_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="text-xs font-semibold">Semester<select value={editor.draft.semester_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, semester_id: event.target.value ? Number(event.target.value) : null } })} className={fieldClass()}><option value="">None</option>{semesters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="col-span-2 text-xs font-semibold">Mode<select value={editor.draft.theory_practical} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, theory_practical: event.target.value as Draft['theory_practical'] } })} className={fieldClass()}>{modes.map((mode) => <option key={mode}>{mode}</option>)}</select></label>
            <label className="text-xs font-semibold">Theory credits<input type="number" min={0} max={100} step="0.1" value={editor.draft.theory_credits} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, theory_credits: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Practical credits<input type="number" min={0} max={100} step="0.1" value={editor.draft.practical_credits} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, practical_credits: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Theory marks<input type="number" min={0} max={1000} value={editor.draft.theory_marks} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, theory_marks: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Practical marks<input type="number" min={0} max={1000} value={editor.draft.practical_marks} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, practical_marks: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Lectures / week<input type="number" min={0} max={40} value={editor.draft.lectures_per_week} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, lectures_per_week: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Practical hours / week<input type="number" min={0} max={40} value={editor.draft.practical_hours_per_week} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, practical_hours_per_week: Number(event.target.value) } })} className={fieldClass()} /></label>
            <label className="col-span-2 text-xs font-semibold">Syllabus URL<input maxLength={500} value={editor.draft.syllabus_url} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, syllabus_url: event.target.value } })} className={fieldClass()} /></label>
            <label className="col-span-2 text-xs font-semibold">Description<textarea rows={2} maxLength={4000} value={editor.draft.description} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })} className={fieldClass()} /></label>
            <label className="col-span-2 inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_elective} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_elective: event.target.checked } })} className="mr-2" />Elective</label>
            <button type="submit" disabled={saving} className="col-span-2 rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete subject?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Delete {pending.name}? Subjects used on the timetable cannot be removed.</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
