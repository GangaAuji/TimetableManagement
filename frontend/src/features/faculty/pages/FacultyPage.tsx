import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { ApiError } from '../../../shared/api/client'
import { DataTableHead, TablePager, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import {
  createFaculty,
  deactivateFaculty,
  emptyFacultyPermissions,
  getFaculty,
  getFacultyMember,
  invitationToken,
  updateFaculty,
  type FacultyDraft,
  type FacultyList,
  type FacultyQueryFields,
  type FacultyOption,
  type FacultyPermissions,
  type FacultyRecord,
} from '../api'

const emptyDraft: FacultyDraft = {
  username: '',
  password: '',
  name: '',
  email: '',
  phone: '',
  designation: '',
  employee_id: '',
  department_id: null,
  is_active: true,
}

const fieldClass = 'w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm shadow-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20'
const facultyColumns: TableColumnSpec[] = [
  { key: 'name', label: 'Name' },
  { key: 'username', label: 'Username', className: 'hidden lg:table-cell' },
  { key: 'email', label: 'Contact', className: 'hidden xl:table-cell' },
  { key: 'department', label: 'Department', filterable: false },
  { key: 'designation', label: 'Designation', className: 'hidden md:table-cell' },
  { key: 'status', label: 'Status', sortable: false, filterable: false, className: 'hidden text-center sm:table-cell' },
]

function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function FacultyPage() {
  const setPageHeader = useSetPageHeader()
  const [list, setList] = useState<FacultyList | null>(null)
  const [permissions, setPermissions] = useState<FacultyPermissions>(emptyFacultyPermissions)
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [department, setDepartment] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [fields, setFields] = useState<FacultyQueryFields>({ name: '', email: '', designation: '', username: '', sort: 'name', order: 'ASC' })
  const [columnFilters, setColumnFilters] = useState({ name: '', email: '', designation: '', username: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<number[]>([])
  const [editor, setEditor] = useState<{ id: number | null; draft: FacultyDraft } | null>(null)
  const [inviteToken, setInviteToken] = useState('')
  const [saving, setSaving] = useState(false)

  async function load(nextSearch: string, nextDepartment: string, nextPage: number, nextPerPage: number, nextFields: FacultyQueryFields = fields) {
    const data = await getFaculty(nextSearch, nextDepartment, nextPage, nextPerPage, nextFields)
    setList(data)
    setPermissions(data.permissions)
    setSelected([])
  }

  useEffect(() => {
    setPageHeader('Faculty Directory')
  }, [setPageHeader])

  useEffect(() => {
    void load(appliedSearch, department, page, perPage, fields)
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [appliedSearch, department, fields, page, perPage])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = search.trim()
      setAppliedSearch((current) => {
        if (current === next) return current
        setPage(1)
        return next
      })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = {
        name: columnFilters.name.trim(),
        email: columnFilters.email.trim(),
        designation: columnFilters.designation.trim(),
        username: columnFilters.username.trim(),
      }
      let changed = false
      setFields((current) => {
        if (current.name === next.name && current.email === next.email && current.designation === next.designation && current.username === next.username) return current
        changed = true
        return { ...current, ...next }
      })
      if (changed) setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [columnFilters])

  async function openEdit(member: FacultyRecord) {
    setError('')
    try {
      const detail = await getFacultyMember(member.id)
      setEditor({
        id: member.id,
        draft: {
          username: detail.username,
          password: '',
          name: detail.name,
          email: detail.email,
          phone: detail.phone,
          designation: detail.designation,
          employee_id: detail.employee_id,
          department_id: detail.department_id || null,
          is_active: detail.is_active,
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
      if (editor.id) await updateFaculty(editor.id, editor.draft)
      else await createFaculty(editor.draft)
      setNotice(editor.id ? 'Faculty member updated.' : 'Faculty member added.')
      setEditor(null)
      await load(appliedSearch, department, page, perPage)
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
      await deactivateFaculty(selected)
      setNotice('Selected faculty were deactivated.')
      await load(appliedSearch, department, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function openInvite() {
    setError('')
    try {
      setInviteToken(await invitationToken())
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  const faculty = list?.faculty ?? []
  const departments = list?.departments ?? []
  const filtered = Boolean(appliedSearch || department || fields.name || fields.email || fields.designation || fields.username)

  function toggleSort(sort: string) {
    setFields((current) => ({ ...current, sort, order: current.sort === sort && current.order === 'ASC' ? 'DESC' : 'ASC' }))
    setPage(1)
  }

  return (
    <div className="flex min-h-0 flex-1 max-w-full flex-col">
      <div className="relative z-30 flex shrink-0 flex-col justify-between gap-4 rounded-t-2xl border border-gray-200/80 bg-white p-3.5 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)] md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-2.5 text-emerald-600 shadow-sm">
            <i className="fas fa-chalkboard-teacher text-lg" />
          </div>
          <div>
            <h2 className="text-sm leading-tight font-bold tracking-tight text-gray-800">Faculty Directory</h2>
            <p className="mt-0.5 text-[10px] font-medium tracking-wide text-gray-500 uppercase">
              {list?.totalActive ?? 0} Active • {list?.totalInactive ?? 0} Inactive{filtered ? ` • ${list?.total ?? 0} Filtered` : ''}
            </p>
          </div>
          {permissions.delete && selected.length > 0 && (
            <button type="button" disabled={saving} onClick={() => void deactivate()} className="ml-2 border-l border-gray-200 pl-4 text-xs font-bold text-red-600">
              Delete Selected
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <select value={department} onChange={(event) => { setDepartment(event.target.value); setPage(1) }} className="rounded-xl border border-gray-200/80 bg-white py-2 pr-8 pl-3 text-xs font-medium text-gray-600 shadow-sm outline-none">
            <option value="">All Departments</option>
            {departments.map((item) => <option key={item.id} value={String(item.id)}>{item.name}</option>)}
          </select>
          {permissions.invite && (
            <button type="button" onClick={() => void openInvite()} className="rounded-lg p-2 text-gray-500 hover:bg-blue-50 hover:text-blue-600" title="Invite Faculty">
              <i className="fas fa-paper-plane text-sm" />
            </button>
          )}
          {permissions.add && (
            <button type="button" onClick={() => { setEditor({ id: null, draft: emptyDraft }); setError('') }} className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-black">
              Add Faculty
            </button>
          )}
        </div>
      </div>
      {error && <p className="border-x border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="border-x border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}
      <div className="flex flex-1 flex-col overflow-hidden rounded-b-2xl border-x border-b border-gray-200 bg-white">
        <TableToolbar search={search} onSearch={setSearch} filtersOpen={filtersOpen} onToggleFilters={() => setFiltersOpen((open) => !open)} matched={list?.total ?? 0} source={list?.total ?? 0} activeCount={(search.trim() ? 1 : 0) + Object.values(columnFilters).filter((value) => value.trim()).length + (department ? 1 : 0) + (fields.sort !== 'name' || fields.order !== 'ASC' ? 1 : 0)} onClear={() => { setSearch(''); setDepartment(''); setColumnFilters({ name: '', email: '', designation: '', username: '' }); setFields((current) => ({ ...current, sort: 'name', order: 'ASC' })) }} />
        <div className="flex-1 overflow-hidden">
          <div className="h-full overflow-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50/90">
              <DataTableHead
                columns={facultyColumns}
                sortKey={fields.sort}
                sortDir={fields.order === 'DESC' ? 'desc' : 'asc'}
                onSort={toggleSort}
                filtersOpen={filtersOpen}
                filters={columnFilters}
                onFilter={(key, value) => setColumnFilters((current) => ({ ...current, [key]: value }))}
                leading={permissions.delete ? <th className="w-10 px-5 py-2.5 text-center"><input type="checkbox" checked={faculty.length > 0 && selected.length === faculty.length} onChange={(event) => setSelected(event.target.checked ? faculty.map((member) => member.id) : [])} aria-label="Select all faculty" /></th> : undefined}
                trailing={<th className="px-5 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>}
              />
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && <tr><td colSpan={8} className="px-6 py-16 text-center text-gray-400">Loading faculty...</td></tr>}
              {!loading && faculty.length === 0 && <tr><td colSpan={8} className="px-6 py-16 text-center text-gray-400">No faculty match your search.</td></tr>}
              {faculty.map((member) => (
                <tr key={member.id} className="hover:bg-emerald-50/40">
                  {permissions.delete && (
                    <td className="px-5 py-2 text-center">
                      <input type="checkbox" checked={selected.includes(member.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, member.id] : current.filter((id) => id !== member.id))} aria-label={`Select ${member.name}`} />
                    </td>
                  )}
                  <td className="px-5 py-2 font-semibold text-gray-800">{member.name}</td>
                  <td className="hidden px-5 py-2 text-gray-500 lg:table-cell">{member.username}</td>
                  <td className="hidden px-5 py-2 text-gray-600 xl:table-cell">{member.email}</td>
                  <td className="px-5 py-2">{member.department_name || '-'}</td>
                  <td className="hidden px-5 py-2 md:table-cell">{member.designation || '-'}</td>
                  <td className="hidden px-5 py-2 text-center sm:table-cell">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${member.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>{member.is_active ? 'Active' : 'Inactive'}</span>
                  </td>
                  <td className="px-5 py-2 text-right">
                    <a href={`/admin/faculty/${member.id}`} className="mr-2 text-[10px] font-bold text-gray-500 hover:text-emerald-700">Details</a>
                    {permissions.change && <button type="button" onClick={() => void openEdit(member)} className="text-[10px] font-bold text-gray-500 hover:text-emerald-700">Edit</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
        <TablePager page={page} totalPages={list?.totalPages ?? 1} pageSize={perPage} onPage={setPage} onPageSize={(size) => { setPerPage(size); setPage(1) }} />
      </div>
      {editor && (
        <Editor
          id={editor.id}
          draft={editor.draft}
          departments={departments}
          saving={saving}
          onChange={(draft) => setEditor({ id: editor.id, draft })}
          onClose={() => setEditor(null)}
          onSubmit={save}
        />
      )}
      {inviteToken && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button type="button" className="absolute inset-0 bg-gray-900/40" aria-label="Close invite" onClick={() => setInviteToken('')} />
          <form method="POST" action="/admin/invitations/create" className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4">
              <h3 className="text-lg font-bold text-white">Invite Teacher</h3>
              <button type="button" onClick={() => setInviteToken('')} className="text-white/80" aria-label="Close">×</button>
            </div>
            <div className="space-y-4 p-6">
              <input type="hidden" name="csrf_token" value={inviteToken} />
              <input type="hidden" name="role" value="Teacher" />
              <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Full Name<input required name="name" maxLength={100} className="mt-1 w-full rounded-lg border border-gray-200 px-4 py-2 text-sm font-normal normal-case" /></label>
              <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Email Address<input required type="email" name="email" maxLength={100} className="mt-1 w-full rounded-lg border border-gray-200 px-4 py-2 text-sm font-normal normal-case" /></label>
              <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Department
                <select required name="department_id" className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-normal normal-case">
                  {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
              <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Valid (Days)<input type="number" name="days_valid" defaultValue={7} min={1} max={90} className="mt-1 w-full rounded-lg border border-gray-200 px-4 py-2 text-sm font-normal normal-case" /></label>
              <button type="submit" className="w-full rounded-xl bg-blue-600 py-2.5 text-xs font-bold text-white">Send Invitation</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

function Editor({
  id,
  draft,
  departments,
  saving,
  onChange,
  onClose,
  onSubmit,
}: {
  id: number | null
  draft: FacultyDraft
  departments: FacultyOption[]
  saving: boolean
  onChange: (draft: FacultyDraft) => void
  onClose: () => void
  onSubmit: (event: FormEvent) => void
}) {
  function set<K extends keyof FacultyDraft>(key: K, value: FacultyDraft[K]) {
    onChange({ ...draft, [key]: value })
  }
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="faculty-editor-title">
      <button type="button" className="absolute inset-0 bg-gray-900/40" aria-label="Close" onClick={onClose} />
      <form onSubmit={onSubmit} className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b px-6 py-5">
          <h3 id="faculty-editor-title" className="text-lg font-extrabold text-gray-800">{id ? 'Edit Faculty' : 'Add Faculty'}</h3>
          <button type="button" onClick={onClose} aria-label="Close editor">×</button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto bg-gray-50/30 p-6">
          <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Full Name<input required value={draft.name} onChange={(event) => set('name', event.target.value)} className={fieldClass} /></label>
          <div className="grid grid-cols-2 gap-4">
            <label className="space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Username<input required={!id} readOnly={Boolean(id)} value={draft.username} onChange={(event) => set('username', event.target.value)} className={fieldClass} /></label>
            <label className="space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Password<input type="password" required={!id} autoComplete="new-password" value={draft.password} onChange={(event) => set('password', event.target.value)} className={fieldClass} /></label>
          </div>
          <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Email<input required type="email" value={draft.email} onChange={(event) => set('email', event.target.value)} className={fieldClass} /></label>
          <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Phone<input value={draft.phone} onChange={(event) => set('phone', event.target.value)} className={fieldClass} /></label>
          <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Department
            <select required value={draft.department_id ?? ''} onChange={(event) => set('department_id', event.target.value ? Number(event.target.value) : null)} className={fieldClass}>
              <option value="">Select Department</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Designation<input value={draft.designation} onChange={(event) => set('designation', event.target.value)} className={fieldClass} /></label>
          {!id && <label className="block space-y-1 text-[10px] font-bold tracking-wide text-gray-500 uppercase">Employee ID<input value={draft.employee_id} onChange={(event) => set('employee_id', event.target.value)} placeholder="Leave blank to generate" className={fieldClass} /></label>}
          <label className="flex items-center gap-2 text-xs font-medium text-gray-700"><input type="checkbox" checked={draft.is_active} onChange={(event) => set('is_active', event.target.checked)} /> Active</label>
        </div>
        <div className="flex gap-3 border-t px-6 py-4">
          <button type="button" onClick={onClose} className="flex-1 rounded-xl border px-4 py-2.5 text-xs font-bold text-gray-600">Cancel</button>
          <button type="submit" disabled={saving} className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-xs font-bold text-white">{saving ? 'Saving...' : 'Save Faculty'}</button>
        </div>
      </form>
    </div>
  )
}

