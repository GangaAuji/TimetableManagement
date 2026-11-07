import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError } from '../../../shared/api/client'
import { DataTableHead, TablePager, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import {
  createStudent,
  deactivateStudents,
  emptyPermissions,
  getStudent,
  getStudents,
  updateStudent,
  type StudentDraft,
  type StudentList,
  type StudentOption,
  type StudentPermissions,
  type StudentQuery,
  type StudentRecord,
} from '../api'

const emptyDraft: StudentDraft = {
  username: '',
  password: '',
  name: '',
  email: '',
  phone: '',
  roll_number: '',
  course_id: null,
  class_id: null,
  division_id: null,
}

const fieldClass = 'w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20'
const studentColumns: TableColumnSpec[] = [
  { key: 'name', label: 'Student Name' },
  { key: 'roll', label: 'Roll No' },
  { key: 'courseName', label: 'Course' },
  { key: 'className', label: 'Class/Div', className: 'hidden md:table-cell' },
  { key: 'email', label: 'Contact' },
]

function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

function initial(name: string) {
  const letter = name.trim().charAt(0)
  return letter ? letter.toUpperCase() : '?'
}

export function StudentsPage() {
  const setPageHeader = useSetPageHeader()
  const [list, setList] = useState<StudentList | null>(null)
  const [permissions, setPermissions] = useState<StudentPermissions>(emptyPermissions)
  const [query, setQuery] = useState<StudentQuery>({ search: '', course: '', name: '', roll: '', courseName: '', className: '', email: '', page: 1, perPage: 25, sort: 'name', order: 'ASC' })
  const [fields, setFields] = useState({ name: '', roll: '', courseName: '', className: '', email: '' })
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<number[]>([])
  const [editor, setEditor] = useState<{ id: number | null; draft: StudentDraft } | null>(null)
  const [saving, setSaving] = useState(false)

  async function load(next: StudentQuery) {
    const data = await getStudents(next)
    setList(data)
    setPermissions(data.permissions)
    setSelected([])
  }

  useEffect(() => {
    setPageHeader('Student Directory')
  }, [setPageHeader])

  useEffect(() => {
    void load(query)
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [query])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery((current) => {
        const next = {
          name: fields.name.trim(),
          roll: fields.roll.trim(),
          courseName: fields.courseName.trim(),
          className: fields.className.trim(),
          email: fields.email.trim(),
        }
        if (current.name === next.name && current.roll === next.roll && current.courseName === next.courseName && current.className === next.className && current.email === next.email) return current
        return { ...current, ...next, page: 1 }
      })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [fields])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = search.trim()
      setQuery((current) => (current.search === next ? current : { ...current, search: next, page: 1 }))
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search])

  function toggleSort(sort: string) {
    setQuery((current) => ({
      ...current,
      sort,
      order: current.sort === sort && current.order === 'ASC' ? 'DESC' : 'ASC',
      page: 1,
    }))
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? (list?.students.map((student) => student.id) ?? []) : [])
  }

  function toggleOne(id: number, checked: boolean) {
    setSelected((current) => (checked ? [...current, id] : current.filter((item) => item !== id)))
  }

  async function openEdit(student: StudentRecord) {
    setError('')
    try {
      const detail = await getStudent(student.id)
      setEditor({
        id: student.id,
        draft: {
          username: detail.username || '',
          password: '',
          name: detail.name,
          email: detail.email,
          phone: detail.phone,
          roll_number: detail.roll_number,
          course_id: detail.course_id || null,
          class_id: detail.class_id || null,
          division_id: detail.division_id || null,
        },
      })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      if (editor.id) await updateStudent(editor.id, editor.draft)
      else await createStudent(editor.draft)
      setNotice(editor.id ? 'Student updated.' : 'Student added.')
      setEditor(null)
      await load(query)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function deactivate() {
    if (!selected.length) return
    setSaving(true)
    setError('')
    try {
      await deactivateStudents(selected)
      setNotice('Selected students were deactivated.')
      await load(query)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const students = list?.students ?? []
  const courses = list?.courses ?? []
  const filtered = Boolean(query.search || query.course || query.name || query.roll || query.courseName || query.className || query.email)

  return (
    <div className="flex min-h-0 flex-1 max-w-full flex-col">
      <div className="relative z-30 flex shrink-0 flex-col justify-between gap-4 rounded-t-2xl border border-gray-200/80 bg-white p-3.5 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)] md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-2.5 text-indigo-600 shadow-sm">
            <i className="fas fa-user-graduate text-lg" />
          </div>
          <div>
            <h2 className="text-sm leading-tight font-bold tracking-tight text-gray-800">Student Directory</h2>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">
                {list?.totalActive ?? 0} Total Students{filtered ? ` • ${list?.total ?? 0} Filtered` : ''}
              </p>
            </div>
          </div>
          {permissions.delete && selected.length > 0 && (
            <button type="button" disabled={saving} onClick={() => void deactivate()} className="ml-2 border-l border-gray-200 pl-4 text-xs font-bold text-red-600">
              <i className="fas fa-trash-alt mr-1.5" />
              Delete Selected
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={query.course}
            onChange={(event) => setQuery((current) => ({ ...current, course: event.target.value, page: 1 }))}
            className="rounded-xl border border-gray-200/80 bg-white py-2 pr-8 pl-3 text-xs font-medium text-gray-600 shadow-sm outline-none"
          >
            <option value="">All Courses</option>
            {courses.map((course) => (
              <option key={course.id} value={String(course.id)}>{course.name}</option>
            ))}
          </select>
          {permissions.invite && (
            <a href="/admin/invitations" className="rounded-lg p-2 text-gray-500 hover:bg-emerald-50 hover:text-emerald-600" title="Invitations">
              <i className="fas fa-file-excel text-sm" />
            </a>
          )}
          {permissions.add && (
            <button type="button" onClick={() => { setEditor({ id: null, draft: emptyDraft }); setError('') }} className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-black">
              <i className="fas fa-plus mr-2 text-[10px]" /> Add Student
            </button>
          )}
        </div>
      </div>

      {error && <p className="border-x border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="border-x border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}

      <div className="relative flex flex-1 flex-col overflow-hidden rounded-b-2xl border-x border-b border-gray-200 bg-white shadow-[0_2px_15px_-3px_rgba(0,0,0,0.02)]">
        <TableToolbar search={search} onSearch={setSearch} filtersOpen={filtersOpen} onToggleFilters={() => setFiltersOpen((open) => !open)} matched={list?.total ?? 0} source={list?.total ?? 0} activeCount={(search.trim() ? 1 : 0) + Object.values(fields).filter((value) => value.trim()).length + (query.course ? 1 : 0) + (query.sort !== 'name' || query.order !== 'ASC' ? 1 : 0)} onClear={() => { setSearch(''); setFields({ name: '', roll: '', courseName: '', className: '', email: '' }); setQuery((current) => ({ ...current, course: '', sort: 'name', order: 'ASC', page: 1 })) }} />
        <div className="flex-1 overflow-hidden">
          <div className="h-full overflow-auto">
          <table className="w-full border-collapse text-left">
            <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50/90">
              <DataTableHead
                columns={studentColumns}
                sortKey={query.sort === 'roll_number' ? 'roll' : query.sort === 'course' ? 'courseName' : query.sort === 'class' ? 'className' : query.sort}
                sortDir={query.order === 'DESC' ? 'desc' : 'asc'}
                onSort={(key) => toggleSort(key === 'roll' ? 'roll_number' : key === 'courseName' ? 'course' : key === 'className' ? 'class' : key)}
                filtersOpen={filtersOpen}
                filters={fields}
                onFilter={(key, value) => setFields((current) => ({ ...current, [key]: value }))}
                leading={permissions.delete ? <th className="w-10 px-5 py-2.5 text-center"><input type="checkbox" checked={students.length > 0 && selected.length === students.length} onChange={(event) => toggleAll(event.target.checked)} aria-label="Select all students" /></th> : undefined}
                trailing={<th className="px-5 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Action</th>}
              />
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white text-xs">
              {loading && (
                <tr><td colSpan={7} className="px-6 py-16 text-center text-gray-400">Loading students...</td></tr>
              )}
              {!loading && students.length === 0 && (
                <tr><td colSpan={7} className="px-6 py-16 text-center text-xs font-medium text-gray-400">No students match your search.</td></tr>
              )}
              {students.map((student) => (
                <tr key={student.id} className="group hover:bg-indigo-50/40">
                  {permissions.delete && (
                    <td className="px-5 py-2 text-center">
                      <input type="checkbox" checked={selected.includes(student.id)} onChange={(event) => toggleOne(student.id, event.target.checked)} aria-label={`Select ${student.name}`} />
                    </td>
                  )}
                  <td className="px-5 py-2 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full border border-indigo-50 bg-gradient-to-br from-indigo-100 to-purple-100 text-[10px] font-bold text-indigo-700">{initial(student.name)}</div>
                      <p className="font-semibold text-gray-800 group-hover:text-indigo-700">{student.name}</p>
                    </div>
                  </td>
                  <td className="px-5 py-2"><span className="rounded border border-gray-100 bg-gray-50 px-1.5 py-0.5 font-mono text-[10px] text-gray-600">{student.roll_number || '-'}</span></td>
                  <td className="px-5 py-2">
                    {student.course_name ? <span className="rounded-md border border-blue-100 bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">{student.course_name}</span> : <span className="text-[10px] text-gray-300">-</span>}
                  </td>
                  <td className="hidden px-5 py-2 md:table-cell">
                    <span className="font-medium text-gray-700">{student.class_name}</span>
                    {student.division_name && <span className="ml-1.5 rounded border border-purple-100 bg-purple-50 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-purple-600 uppercase">Div {student.division_name}</span>}
                  </td>
                  <td className="px-5 py-2 whitespace-nowrap text-gray-600">{student.email}</td>
                  <td className="px-5 py-2 text-right">
                    {permissions.change && (
                      <button type="button" onClick={() => void openEdit(student)} className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:border hover:border-gray-200 hover:bg-white hover:text-indigo-600" aria-label={`Edit ${student.name}`}>
                        <i className="fas fa-pen text-[10px]" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
        <TablePager
          page={query.page}
          totalPages={list?.totalPages ?? 1}
          pageSize={query.perPage}
          onPage={(page) => setQuery((current) => ({ ...current, page }))}
          onPageSize={(perPage) => setQuery((current) => ({ ...current, perPage, page: 1 }))}
        />
      </div>

      {editor && (
        <Editor
          id={editor.id}
          draft={editor.draft}
          courses={courses}
          classes={list?.classes ?? []}
          divisions={list?.divisions ?? []}
          saving={saving}
          onChange={(draft) => setEditor({ id: editor.id, draft })}
          onClose={() => setEditor(null)}
          onSubmit={save}
        />
      )}
    </div>
  )
}

function Editor({
  id,
  draft,
  courses,
  classes,
  divisions,
  saving,
  onChange,
  onClose,
  onSubmit,
}: {
  id: number | null
  draft: StudentDraft
  courses: StudentOption[]
  classes: StudentOption[]
  divisions: StudentOption[]
  saving: boolean
  onChange: (draft: StudentDraft) => void
  onClose: () => void
  onSubmit: (event: FormEvent) => void
}) {
  function set<K extends keyof StudentDraft>(key: K, value: StudentDraft[K]) {
    onChange({ ...draft, [key]: value })
  }

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="student-editor-title">
      <button type="button" className="absolute inset-0 bg-gray-900/40" aria-label="Close" onClick={onClose} />
      <form onSubmit={onSubmit} className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-gray-100 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-5">
          <div>
            <h3 id="student-editor-title" className="text-lg font-extrabold tracking-tight text-gray-800">{id ? 'Edit Student' : 'Add Student'}</h3>
            <p className="mt-0.5 text-[10px] font-medium text-gray-500">Fill in the details below</p>
          </div>
          <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-50 text-gray-400" aria-label="Close editor">
            <i className="fas fa-times text-sm" />
          </button>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto bg-gray-50/30 p-6">
          <label className="block space-y-1">
            <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Full Name</span>
            <input required value={draft.name} onChange={(event) => set('name', event.target.value)} className={fieldClass} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Username</span>
              <input required={!id} readOnly={Boolean(id)} value={draft.username} onChange={(event) => set('username', event.target.value)} className={fieldClass} />
            </label>
            <label className="space-y-1">
              <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Password</span>
              <input type="password" required={!id} autoComplete="new-password" value={draft.password} onChange={(event) => set('password', event.target.value)} className={fieldClass} />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Email Address</span>
            <input type="email" required value={draft.email} onChange={(event) => set('email', event.target.value)} className={fieldClass} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Phone</span>
              <input value={draft.phone} onChange={(event) => set('phone', event.target.value)} className={fieldClass} />
            </label>
            <label className="space-y-1">
              <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Roll No</span>
              <input value={draft.roll_number} onChange={(event) => set('roll_number', event.target.value)} className={`${fieldClass} font-mono`} />
            </label>
          </div>
          <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h4 className="border-b border-gray-100 pb-2 text-xs font-bold text-indigo-600 uppercase">Academic Details</h4>
            <label className="block space-y-1">
              <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Course</span>
              <select required value={draft.course_id ?? ''} onChange={(event) => set('course_id', event.target.value ? Number(event.target.value) : null)} className={fieldClass}>
                <option value="">Select Course</option>
                {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="space-y-1">
                <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Class</span>
                <select value={draft.class_id ?? ''} onChange={(event) => set('class_id', event.target.value ? Number(event.target.value) : null)} className={fieldClass}>
                  <option value="">None</option>
                  {classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="space-y-1">
                <span className="ml-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Division</span>
                <select value={draft.division_id ?? ''} onChange={(event) => set('division_id', event.target.value ? Number(event.target.value) : null)} className={fieldClass}>
                  <option value="">None</option>
                  {divisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            </div>
          </div>
        </div>
        <div className="flex gap-3 border-t border-gray-100 px-6 py-4">
          <button type="button" onClick={onClose} className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-xs font-bold text-gray-600">Cancel</button>
          <button type="submit" disabled={saving} className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-xs font-bold text-white shadow-lg">{saving ? 'Saving...' : 'Save Details'}</button>
        </div>
      </form>
    </div>
  )
}
