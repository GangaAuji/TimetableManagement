import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError } from '../../../shared/api/client'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import {
  createCourse,
  deleteCourse,
  getCourse,
  getCourses,
  programs,
  updateCourse,
  type CourseDraft,
  type CoursePermissions,
  type CourseRecord,
  type DepartmentOption,
  type Program,
} from '../api'

const emptyPermissions: CoursePermissions = { add: false, change: false, delete: false }
const courseColumns: TableColumnSpec[] = [
  { key: 'name', label: 'Course' },
  { key: 'code', label: 'Code' },
  { key: 'program', label: 'Program' },
  { key: 'department_name', label: 'Department', className: 'hidden md:table-cell' },
  { key: 'duration', label: 'Duration', className: 'hidden lg:table-cell' },
  { key: 'stats', label: 'Stats', className: 'hidden text-center sm:table-cell' },
  { key: 'status', label: 'Status', className: 'text-center' },
]

function courseValue(course: CourseRecord, key: string) {
  if (key === 'duration') return `${course.duration_years} years ${course.total_semesters} semesters`
  if (key === 'stats') return `${course.subject_count} subjects ${course.batch_count} batches`
  if (key === 'status') return course.is_active ? 'Active' : 'Inactive'
  return course[key as keyof CourseRecord]
}
const emptyDraft: CourseDraft = {
  name: '',
  code: '',
  program: 'UG',
  department_id: null,
  duration_years: 3,
  total_semesters: 6,
  description: '',
  is_active: true,
}

function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function CoursesPage() {
  const setPageHeader = useSetPageHeader()
  const [courses, setCourses] = useState<CourseRecord[]>([])
  const [departments, setDepartments] = useState<DepartmentOption[]>([])
  const [permissions, setPermissions] = useState<CoursePermissions>(emptyPermissions)
  const [programFilter, setProgramFilter] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [editor, setEditor] = useState<{ id: number | null; draft: CourseDraft } | null>(null)
  const [pendingDelete, setPendingDelete] = useState<CourseRecord | null>(null)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await getCourses()
    setCourses(data.courses)
    setDepartments(data.departments)
    setPermissions(data.permissions)
  }

  useEffect(() => {
    setPageHeader('Courses Registry')
  }, [setPageHeader])

  useEffect(() => {
    void load()
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [])

  const rows = useMemo(() => courses.filter((course) => {
    const matchesProgram = !programFilter || course.program === programFilter
    const matchesDepartment = !departmentFilter || course.department_name === departmentFilter
    return matchesProgram && matchesDepartment
  }), [courses, departmentFilter, programFilter])
  const table = useDataTable(rows, courseColumns, courseValue)

  const editorDepartments = useMemo(() => {
    if (!editor?.draft.department_id) return departments
    if (departments.some((department) => department.id === editor.draft.department_id)) return departments
    const current = courses.find((course) => course.department_id === editor.draft.department_id)
    if (!current?.department_name) return departments
    return [...departments, { id: current.department_id, name: current.department_name }]
  }, [courses, departments, editor])

  async function openEdit(courseId: number) {
    setError('')
    try {
      const course = await getCourse(courseId)
      setEditor({
        id: course.id,
        draft: {
          name: course.name,
          code: course.code,
          program: course.program || 'UG',
          department_id: course.department_id || null,
          duration_years: course.duration_years || 3,
          total_semesters: course.total_semesters || 6,
          description: course.description,
          is_active: course.is_active,
        },
      })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (editor.id) await updateCourse(editor.id, editor.draft)
      else await createCourse(editor.draft)
      setNotice(editor.id ? 'Course updated.' : 'Course added.')
      setEditor(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function onDelete() {
    if (!pendingDelete) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await deleteCourse(pendingDelete.id)
      setNotice('Course deleted.')
      setPendingDelete(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col items-start justify-between gap-3 p-3 xl:flex-row xl:items-center">
          <div className="flex w-full items-center justify-between xl:w-auto">
            <div>
              <h2 className="text-base font-bold text-gray-800">Course List</h2>
              <p className="text-[10px] tracking-wide text-gray-500 uppercase">Manage Programs & Curriculum</p>
            </div>
            {permissions.add ? (
              <button type="button" className="rounded bg-green-600 px-3 py-1.5 text-xs text-white shadow hover:bg-green-700 xl:hidden" onClick={() => setEditor({ id: null, draft: { ...emptyDraft, department_id: departments[0]?.id ?? null } })}>
                <i className="fas fa-plus" />
              </button>
            ) : null}
          </div>
          <div className="flex w-full flex-col items-center gap-2 md:flex-row xl:w-auto">
            <select value={programFilter} onChange={(event) => setProgramFilter(event.target.value)} className="w-full rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-green-500 md:w-32">
              <option value="">All Programs</option>
              {programs.map((program) => <option key={program} value={program}>{program}</option>)}
            </select>
            <select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)} className="w-full rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-green-500 md:w-40">
              <option value="">All Departments</option>
              {departments.map((department) => <option key={department.id} value={department.name}>{department.name}</option>)}
            </select>
            {permissions.add ? (
              <button type="button" className="hidden items-center rounded bg-green-600 px-4 py-1.5 text-xs font-medium whitespace-nowrap text-white shadow hover:bg-green-700 xl:flex" onClick={() => setEditor({ id: null, draft: { ...emptyDraft, department_id: departments[0]?.id ?? null } })}>
                <i className="fas fa-plus mr-2" /> Add Course
              </button>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</p> : null}

      <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="max-h-[75vh] overflow-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="sticky top-0 z-10 bg-gray-50 shadow-sm">
              <DataTableHead columns={courseColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white text-sm">
              {loading ? (
                <tr><td colSpan={8} className="px-6 py-8 text-center text-sm text-gray-500">Loading courses…</td></tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-sm text-gray-500">
                    <i className="fas fa-folder-open mb-2 block text-3xl text-gray-300" />
                    No courses found.
                  </td>
                </tr>
              ) : table.rows.length === 0 ? (
                <tr><td colSpan={8} className="px-6 py-8 text-center text-sm text-gray-500">No courses match these filters.</td></tr>
              ) : table.rows.map((course) => (
                <tr key={course.id} className="group transition-colors hover:bg-green-50">
                  <td className="px-4 py-2">
                    <div className="flex flex-col">
                      <span className="leading-tight font-semibold text-gray-900">{course.name}</span>
                      <span className="mt-0.5 font-mono text-[10px] text-gray-500">{course.code || '-'}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <span className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${course.program === 'UG' ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-purple-200 bg-purple-50 text-purple-700'}`}>
                      {course.program || '—'}
                    </span>
                  </td>
                  <td className="hidden px-4 py-2 text-xs text-gray-600 md:table-cell">{course.department_name}</td>
                  <td className="hidden px-4 py-2 text-xs text-gray-600 lg:table-cell">
                    {course.duration_years} Yrs <span className="mx-1 text-gray-300">|</span> {course.total_semesters} Sem
                  </td>
                  <td className="hidden px-4 py-2 text-center sm:table-cell">
                    <div className="flex justify-center gap-3 text-[10px] text-gray-500">
                      <span title="Subjects" className="flex items-center"><i className="fas fa-book mr-1 text-gray-400" />{course.subject_count}</span>
                      <span title="Batches" className="flex items-center"><i className="fas fa-layer-group mr-1 text-gray-400" />{course.batch_count}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-center">
                    {course.is_active ? (
                      <span className="inline-flex rounded bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-800">Active</span>
                    ) : (
                      <span className="inline-flex rounded bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">Inactive</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <div className="flex justify-end gap-2 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100">
                      {permissions.change ? (
                        <button type="button" title="Edit" className="rounded border border-transparent p-1.5 text-blue-600 hover:border-blue-200 hover:bg-blue-50" onClick={() => void openEdit(course.id)}>
                          <i className="fas fa-edit text-xs" />
                        </button>
                      ) : null}
                      {permissions.delete ? (
                        <button type="button" title="Delete" className="rounded border border-transparent p-1.5 text-red-600 hover:border-red-200 hover:bg-red-50" onClick={() => setPendingDelete(course)}>
                          <i className="fas fa-trash-alt text-xs" />
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
      </section>

      {editor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
          <button type="button" aria-label="Close" className="absolute inset-0 bg-gray-900/60" onClick={() => setEditor(null)} />
          <div className="relative m-4 w-full max-w-lg overflow-hidden rounded-lg bg-white shadow-2xl">
            <div className={`flex items-center justify-between px-6 py-3 ${editor.id ? 'bg-blue-600' : 'bg-green-600'}`}>
              <h3 className="text-base font-bold text-white">{editor.id ? 'Edit Course' : 'Add New Course'}</h3>
              <button type="button" className="text-lg text-white hover:text-gray-200" onClick={() => setEditor(null)}>&times;</button>
            </div>
            <form className="p-6" onSubmit={(event) => void onSave(event)}>
              <div className="grid grid-cols-2 gap-4">
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Course Name <span className="text-red-500">*</span>
                  <input required maxLength={100} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  Code
                  <input maxLength={20} value={editor.draft.code} placeholder="e.g. CSE" onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, code: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  Program <span className="text-red-500">*</span>
                  <select required value={editor.draft.program} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, program: event.target.value as Program } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500">
                    {programs.map((program) => <option key={program} value={program}>{program}</option>)}
                  </select>
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Department <span className="text-red-500">*</span>
                  <select required value={editor.draft.department_id ?? ''} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, department_id: Number(event.target.value) } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500">
                    <option value="" disabled>Select...</option>
                    {editorDepartments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  {editor.id ? 'Years' : 'Duration (Years)'}
                  <input required type="number" min={1} max={20} value={editor.draft.duration_years} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, duration_years: Number(event.target.value) } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  {editor.id ? 'Semesters' : 'Total Semesters'}
                  <input required type="number" min={1} max={40} value={editor.draft.total_semesters} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, total_semesters: Number(event.target.value) } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500" />
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Description
                  <textarea maxLength={4000} rows={2} value={editor.draft.description} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-green-500" />
                </label>
              </div>
              <div className="mt-6 flex items-center justify-between border-t border-gray-100 pt-4">
                <label className="inline-flex items-center text-xs font-medium text-gray-700">
                  <input type="checkbox" checked={editor.draft.is_active} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_active: event.target.checked } })} className="h-4 w-4 rounded text-green-600" />
                  <span className="ml-2">{editor.id ? 'Active' : 'Active Course'}</span>
                </label>
                <div className="flex gap-2">
                  <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-200" onClick={() => setEditor(null)}>Cancel</button>
                  <button type="submit" disabled={saving} className={`rounded-md px-6 py-2 text-xs font-medium text-white shadow disabled:opacity-60 ${editor.id ? 'bg-blue-600 hover:bg-blue-700' : 'bg-green-600 hover:bg-green-700'}`}>
                    {saving ? 'Saving…' : editor.id ? 'Update' : 'Save'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {pendingDelete ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
          <button type="button" aria-label="Close delete" className="absolute inset-0 bg-gray-900/60" onClick={() => setPendingDelete(null)} />
          <div className="relative m-4 w-full max-w-sm rounded-lg bg-white shadow-xl">
            <div className="p-6 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
                <i className="fas fa-trash-alt text-lg text-red-600" />
              </div>
              <h3 className="text-base font-bold text-gray-900">Delete Course?</h3>
              <p className="mt-2 text-xs text-gray-500">Delete <strong>{pendingDelete.name}</strong>? This affects subjects and batches.</p>
            </div>
            <div className="flex flex-row-reverse gap-2 rounded-b-lg bg-gray-50 px-4 py-3">
              <button type="button" disabled={saving} className="rounded-md bg-red-600 px-4 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60" onClick={() => void onDelete()}>Delete</button>
              <button type="button" className="rounded-md border border-gray-300 bg-white px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50" onClick={() => setPendingDelete(null)}>Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
