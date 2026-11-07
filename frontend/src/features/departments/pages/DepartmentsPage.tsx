import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError } from '../../../shared/api/client'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { getCsrfToken } from '../../../shared/api/endpoints'
import {
  createDepartment,
  deleteDepartment,
  getDepartment,
  getDepartments,
  updateDepartment,
  type DepartmentDraft,
  type DepartmentPermissions,
  type DepartmentRecord,
} from '../api'

const emptyPermissions: DepartmentPermissions = { add: false, change: false, delete: false, invite: false }
const emptyDraft: DepartmentDraft = { name: '', code: '', description: '', head_of_department: '', is_active: true }
const departmentColumns: TableColumnSpec[] = [
  { key: 'name', label: 'Department' },
  { key: 'code', label: 'Code' },
  { key: 'head_of_department', label: 'Head', className: 'hidden md:table-cell' },
  { key: 'course_count', label: 'Stats', className: 'hidden sm:table-cell' },
  { key: 'status', label: 'Status', className: 'text-center' },
]

function departmentValue(department: DepartmentRecord, key: string) {
  if (key === 'status') return department.is_active ? 'Active' : 'Inactive'
  return department[key as keyof DepartmentRecord]
}

function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function DepartmentsPage() {
  const setPageHeader = useSetPageHeader()
  const [departments, setDepartments] = useState<DepartmentRecord[]>([])
  const [permissions, setPermissions] = useState<DepartmentPermissions>(emptyPermissions)
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [editor, setEditor] = useState<{ id: number | null; draft: DepartmentDraft } | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DepartmentRecord | null>(null)
  const [invite, setInvite] = useState<DepartmentRecord | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await getDepartments()
    setDepartments(data.departments)
    setPermissions(data.permissions)
  }

  useEffect(() => {
    setPageHeader('Departments')
  }, [setPageHeader])

  useEffect(() => {
    void load()
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [])

  const rows = useMemo(() => departments.filter((department) => {
    const status = department.is_active ? 'Active' : 'Inactive'
    return !statusFilter || status === statusFilter
  }), [departments, statusFilter])
  const table = useDataTable(rows, departmentColumns, departmentValue)

  async function openEdit(departmentId: number) {
    setError('')
    try {
      const department = await getDepartment(departmentId)
      setEditor({
        id: department.id,
        draft: {
          name: department.name,
          code: department.code,
          description: department.description,
          head_of_department: department.head_of_department,
          is_active: department.is_active,
        },
      })
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function openInvite(department: DepartmentRecord) {
    setError('')
    try {
      const token = await getCsrfToken()
      setCsrfToken(token.csrf_token)
      setInvite(department)
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
      if (editor.id) await updateDepartment(editor.id, editor.draft)
      else await createDepartment(editor.draft)
      setNotice(editor.id ? 'Department updated.' : 'Department added.')
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
      await deleteDepartment(pendingDelete.id)
      setNotice('Department deleted.')
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
        <div className="flex flex-col items-start justify-between gap-4 p-4 xl:flex-row xl:items-center">
          <div className="flex w-full items-center justify-between gap-4 xl:w-auto">
            <div>
              <h2 className="text-lg font-bold text-gray-800">Departments</h2>
              <p className="text-xs text-gray-500">Academic units configuration</p>
            </div>
            {permissions.add ? (
              <button type="button" className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white shadow hover:bg-indigo-700 xl:hidden" onClick={() => setEditor({ id: null, draft: emptyDraft })}>
                <i className="fas fa-plus" />
              </button>
            ) : null}
          </div>
          <div className="flex w-full flex-col flex-wrap items-end gap-2 md:flex-row md:items-center xl:w-auto">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="w-full rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500 md:w-32">
              <option value="">All Status</option>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
            {permissions.add ? (
              <button type="button" className="hidden items-center rounded bg-indigo-600 px-4 py-1.5 text-xs whitespace-nowrap text-white shadow hover:bg-indigo-700 xl:flex" onClick={() => setEditor({ id: null, draft: emptyDraft })}>
                <i className="fas fa-plus mr-2" /> Add Department
              </button>
            ) : null}
          </div>
        </div>
      </section>

      {error ? <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</p> : null}

      <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="max-h-[70vh] overflow-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="sticky top-0 z-10 bg-gray-50 shadow-sm">
              <DataTableHead columns={departmentColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {loading ? (
                <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">Loading departments…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">No departments found.</td></tr>
              ) : table.rows.length === 0 ? (
                <tr><td colSpan={6} className="px-6 py-8 text-center text-gray-500">No departments match these filters.</td></tr>
              ) : table.rows.map((department) => (
                <tr key={department.id} className="group transition-colors hover:bg-indigo-50">
                  <td className="px-4 py-2">
                    <div className="font-semibold text-gray-900">{department.name}</div>
                    {department.description ? <div className="hidden max-w-xs truncate text-[10px] text-gray-500 lg:block">{department.description}</div> : null}
                  </td>
                  <td className="px-4 py-2">
                    <span className="rounded border border-gray-200 bg-gray-100 px-2 py-0.5 font-mono text-xs">{department.code || '—'}</span>
                  </td>
                  <td className="hidden px-4 py-2 text-xs text-gray-600 md:table-cell">
                    {department.head_of_department ? <><i className="fas fa-user-tie mr-1 text-gray-400" />{department.head_of_department}</> : <span className="text-gray-400 italic">-</span>}
                  </td>
                  <td className="hidden px-4 py-2 text-xs sm:table-cell">
                    <span className="rounded border border-blue-100 bg-blue-50 px-2 py-0.5 text-blue-700">{department.course_count} Courses</span>
                  </td>
                  <td className="px-4 py-2 text-center">
                    {department.is_active ? (
                      <span className="inline-flex rounded bg-green-100 px-2 py-0.5 text-[10px] font-bold text-green-800 uppercase">Active</span>
                    ) : (
                      <span className="inline-flex rounded bg-gray-100 px-2 py-0.5 text-[10px] font-bold text-gray-600 uppercase">Inactive</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <div className="flex justify-end gap-2 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100">
                      {permissions.invite ? (
                        <button type="button" title="Invite Teacher" className="rounded p-1.5 text-emerald-600 hover:bg-emerald-50 hover:text-emerald-800" onClick={() => void openInvite(department)}>
                          <i className="fas fa-paper-plane" />
                        </button>
                      ) : null}
                      {permissions.change ? (
                        <button type="button" title="Edit" className="rounded p-1.5 text-blue-600 hover:bg-blue-50 hover:text-blue-800" onClick={() => void openEdit(department.id)}>
                          <i className="fas fa-edit" />
                        </button>
                      ) : null}
                      {permissions.delete ? (
                        <button type="button" title="Delete" className="rounded p-1.5 text-red-600 hover:bg-red-50 hover:text-red-800" onClick={() => setPendingDelete(department)}>
                          <i className="fas fa-trash-alt" />
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
            <div className={`flex items-center justify-between px-6 py-4 ${editor.id ? 'bg-blue-600' : 'bg-indigo-600'}`}>
              <h3 className="text-lg font-bold text-white">{editor.id ? 'Edit Department' : 'Add Department'}</h3>
              <button type="button" className="text-xl text-white hover:text-gray-200" onClick={() => setEditor(null)}>&times;</button>
            </div>
            <form className="p-6" onSubmit={(event) => void onSave(event)}>
              <div className="grid grid-cols-2 gap-4">
                <label className="col-span-2 block text-xs font-semibold text-gray-700 sm:col-span-1">
                  Name <span className="text-red-500">*</span>
                  <input required maxLength={100} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-indigo-500" />
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700 sm:col-span-1">
                  Code <span className="text-red-500">*</span>
                  <input required maxLength={20} value={editor.draft.code} placeholder="e.g. CSE" onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, code: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-indigo-500" />
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Head of Department
                  <input maxLength={100} value={editor.draft.head_of_department} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, head_of_department: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-indigo-500" />
                </label>
                <label className="col-span-2 block text-xs font-semibold text-gray-700">
                  Description
                  <textarea maxLength={4000} rows={2} value={editor.draft.description} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-indigo-500" />
                </label>
              </div>
              <div className="mt-6 flex items-center justify-between border-t border-gray-100 pt-4">
                <label className="inline-flex items-center text-sm text-gray-700">
                  <input type="checkbox" checked={editor.draft.is_active} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_active: event.target.checked } })} className="h-4 w-4 rounded text-indigo-600" />
                  <span className="ml-2">{editor.id ? 'Active' : 'Set as Active'}</span>
                </label>
                <div className="flex gap-3">
                  <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200" onClick={() => setEditor(null)}>Cancel</button>
                  <button type="submit" disabled={saving} className={`rounded-md px-6 py-2 text-sm font-medium text-white shadow disabled:opacity-60 ${editor.id ? 'bg-blue-600 hover:bg-blue-700' : 'bg-indigo-600 hover:bg-indigo-700'}`}>
                    {saving ? 'Saving…' : editor.id ? 'Update' : 'Save'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {invite ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
          <button type="button" aria-label="Close invite" className="absolute inset-0 bg-gray-900/60" onClick={() => setInvite(null)} />
          <div className="relative m-4 w-full max-w-md overflow-hidden rounded-lg bg-white shadow-2xl">
            <div className="flex items-center justify-between bg-emerald-600 px-6 py-4">
              <h3 className="text-lg font-bold text-white">Invite Teacher</h3>
              <button type="button" className="text-xl text-white hover:text-gray-200" onClick={() => setInvite(null)}>&times;</button>
            </div>
            <form method="POST" action="/admin/invitations/create" className="p-6">
              <input type="hidden" name="csrf_token" value={csrfToken} />
              <input type="hidden" name="role" value="Teacher" />
              <input type="hidden" name="department_id" value={invite.id} />
              <div className="mb-4 rounded border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                Invite for: <strong>{invite.name}</strong>
              </div>
              <div className="space-y-4">
                <label className="block text-xs font-semibold text-gray-700">
                  Full Name
                  <input required name="name" maxLength={100} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-emerald-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  Email
                  <input required type="email" name="email" maxLength={160} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-emerald-500" />
                </label>
                <label className="block text-xs font-semibold text-gray-700">
                  Valid For (days)
                  <input required type="number" name="days_valid" defaultValue={7} min={1} max={90} className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:ring-1 focus:ring-emerald-500" />
                </label>
              </div>
              <div className="mt-6 flex justify-end gap-3 border-t border-gray-100 pt-4">
                <button type="button" className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200" onClick={() => setInvite(null)}>Cancel</button>
                <button type="submit" className="rounded-md bg-emerald-600 px-6 py-2 text-sm font-medium text-white shadow hover:bg-emerald-700">Send Invite</button>
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
              <h3 className="text-lg font-medium text-gray-900">Delete Department?</h3>
              <p className="mt-2 text-sm text-gray-500">Delete <strong>{pendingDelete.name}</strong>? This may affect related courses.</p>
            </div>
            <div className="flex flex-row-reverse gap-2 rounded-b-lg bg-gray-50 px-4 py-3">
              <button type="button" disabled={saving} className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60" onClick={() => void onDelete()}>Delete</button>
              <button type="button" className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50" onClick={() => setPendingDelete(null)}>Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
