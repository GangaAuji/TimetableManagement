import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { displayValue, messageFrom, postJson, type DataRow } from '../../../shared/components/data-list'
import { DataTableHead, TablePager, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Flags = {
  add: boolean
  change: boolean
  delete: boolean
  manage: boolean
  password: boolean
  export: boolean
}

const emptyFlags: Flags = { add: false, change: false, delete: false, manage: false, password: false, export: false }
const userColumns: TableColumnSpec[] = [
  { key: 'username', label: 'Username' },
  { key: 'role', label: 'Role' },
  { key: 'status', label: 'Status' },
  { key: 'last_login', label: 'Last login' },
]

type EditUser = {
  id: string
  username: string
  email: string
  role: string
  status: string
  is_hod: boolean
  department_id: string
}

export function UsersPage() {
  const setPageHeader = useSetPageHeader()
  const [query] = useSearchParams()
  const initialSearch = safeText(query.get('search') || '', 80)
  const initialRole = safeText(query.get('role') || '', 50)
  const [users, setUsers] = useState<DataRow[]>([])
  const [flags, setFlags] = useState<Flags>(emptyFlags)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [exportQueued, setExportQueued] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [search, setSearch] = useState(initialSearch)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [filters, setFilters] = useState({ username: '', role: initialRole, status: '', last_login: '' })
  const [selected, setSelected] = useState<string[]>([])
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteName, setInviteName] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('Teacher')
  const [editor, setEditor] = useState<EditUser | null>(null)
  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([])
  const [editRoles, setEditRoles] = useState<string[]>([])
  const [password, setPassword] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [applied, setApplied] = useState({ search: initialSearch, username: '', role: initialRole, status: '', lastLogin: '', sort: 'username', order: 'ASC' as 'ASC' | 'DESC' })

  async function load(next: { search: string; username: string; role: string; status: string; lastLogin: string; sort: string; order: 'ASC' | 'DESC' }, nextPage: number, nextPerPage: number) {
    const params = new URLSearchParams()
    if (next.search) params.set('search', next.search)
    if (next.username) params.set('username', next.username)
    if (next.role) params.set('role', next.role)
    if (next.status) params.set('status', next.status)
    if (next.lastLogin) params.set('last_login', next.lastLogin)
    if (next.sort) params.set('sort', next.sort)
    if (next.order) params.set('order', next.order)
    params.set('page', String(nextPage))
    params.set('per_page', String(nextPerPage))
    const query = params.toString()
    const data = await apiRequest<{ users?: Record<string, unknown>[]; roles?: unknown[]; permissions?: Partial<Flags>; total?: unknown; total_pages?: unknown }>(
      `/api/users?${query}`,
    )
    const hidden = new Set(['Teacher', 'Student'])
    setUsers((data.users || []).flatMap((user) => {
      const roleName = displayValue(user.role)
      if (hidden.has(roleName)) return []
      return [{
        id: displayValue(user.id),
        username: displayValue(user.username),
        role: roleName,
        status: displayValue(user.status),
        last_login: displayValue(user.last_login) || 'Never',
      }]
    }))
    setFlags({ ...emptyFlags, ...data.permissions })
    setTotal(safeCount(data.total))
    setTotalPages(Math.max(safeCount(data.total_pages), 1))
    setSelected([])
  }

  useEffect(() => {
    setPageHeader('Users')
  }, [setPageHeader])

  useEffect(() => {
    void load(applied, page, perPage).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [applied, page, perPage])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = { search: search.trim(), username: filters.username.trim(), role: filters.role.trim(), status: filters.status.trim(), lastLogin: filters.last_login.trim() }
      setApplied((current) => {
        if (current.search === next.search && current.username === next.username && current.role === next.role && current.status === next.status && current.lastLogin === next.lastLogin) return current
        setPage(1)
        return { ...current, ...next }
      })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [filters, search])

  async function invite(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await postJson('/api/invitations', { name: inviteName, email: inviteEmail, role: inviteRole, days_valid: 7 })
      setExportQueued(false)
      setNotice('Invitation created. It expires in 7 days.')
      setInviteOpen(false)
      setInviteName('')
      setInviteEmail('')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function openEdit(id: string) {
    setError('')
    try {
      const data = await apiRequest<{ user: EditUser & { department_id: number | null }; roles?: string[]; departments?: { id: number; name: string }[] }>(`/api/users/${id}`)
      setDepartments((data.departments || []).map((item) => ({ id: String(item.id), name: safeText(item.name, 100) })))
      setEditRoles((data.roles || []).map((item) => safeText(item, 50)).filter(Boolean))
      setEditor({
        id: String(data.user.id),
        username: data.user.username,
        email: data.user.email || '',
        role: data.user.role,
        status: data.user.status === 'inactive' ? 'inactive' : 'active',
        is_hod: data.user.is_hod === true,
        department_id: data.user.department_id ? String(data.user.department_id) : '',
      })
      setPassword('')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setError('')
    try {
      await postJson(`/api/users/${editor.id}`, {
        username: editor.username,
        password,
        role: editor.role,
        status: editor.status,
        email: editor.email,
        department_id: editor.department_id ? Number(editor.department_id) : null,
        is_hod: editor.is_hod,
      })
      setExportQueued(false)
      setNotice('User updated.')
      setEditor(null)
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function run(path: string, success: string) {
    setError('')
    try {
      const data = await postJson<{ temporary_password?: string }>(path, {})
      setExportQueued(false)
      setNotice(data.temporary_password ? `${success} Temporary password: ${data.temporary_password}` : success)
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function bulk(action: 'activate' | 'deactivate' | 'delete') {
    if (selected.length === 0) return
    setError('')
    try {
      await postJson('/api/users/bulk', { action, ids: selected.map(Number) })
      setExportQueued(false)
      setNotice(action === 'delete' ? 'Selected users were deactivated.' : `Selected users were ${action}d.`)
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function exportUsers() {
    setError('')
    setExporting(true)
    try {
      await postJson('/api/exports', {
        kind: 'users',
        search: applied.search,
        username: applied.username,
        role: applied.role,
        status: applied.status,
        last_login: applied.lastLogin,
      })
      setExportQueued(true)
      setNotice('Export queued.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setExporting(false)
    }
  }

  function sortBy(sort: string) {
    setPage(1)
    setApplied((current) => ({ ...current, sort, order: current.sort === sort && current.order === 'ASC' ? 'DESC' : 'ASC' }))
  }

  const canSelect = flags.change || flags.delete

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">System users</h2>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{total} accounts</p>
        </div>
        <div className="flex gap-2">
          {flags.export && <button type="button" disabled={exporting} onClick={() => void exportUsers()} className="rounded-xl border px-3 py-2 text-xs font-bold disabled:opacity-50">Export</button>}
          {flags.add && <button type="button" onClick={() => setInviteOpen(true)} className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white">Invite user</button>}
        </div>
      </header>
      {canSelect && selected.length > 0 && (
        <div className="flex gap-2 border-b border-gray-100 px-5 py-2">
          {flags.change && <button type="button" className="text-[10px] font-bold text-emerald-700" onClick={() => void bulk('activate')}>Activate</button>}
          {flags.change && <button type="button" className="text-[10px] font-bold text-amber-700" onClick={() => void bulk('deactivate')}>Deactivate</button>}
          {flags.delete && <button type="button" className="text-[10px] font-bold text-red-700" onClick={() => void bulk('delete')}>Delete</button>}
        </div>
      )}
      {error && <p className="px-5 py-2 text-xs text-red-700">{error}</p>}
      {notice && (
        <p className="px-5 py-2 text-xs text-emerald-700">
          {notice}
          {exportQueued && <> <Link to="/admin/reports" className="font-bold underline">Open Reports</Link> to follow the progress and download the file.</>}
        </p>
      )}
      <TableToolbar
        search={search}
        onSearch={setSearch}
        filtersOpen={filtersOpen}
        onToggleFilters={() => setFiltersOpen((open) => !open)}
        matched={total}
        source={total}
        activeCount={(search.trim() ? 1 : 0) + Object.values(filters).filter((value) => value.trim()).length + (applied.sort !== 'username' || applied.order !== 'ASC' ? 1 : 0)}
        onClear={() => { setSearch(''); setFilters({ username: '', role: '', status: '', last_login: '' }); setApplied((current) => ({ ...current, sort: 'username', order: 'ASC' })) }}
      />
      <div className="flex-1 overflow-hidden">
        <div className="h-full overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead
              columns={userColumns}
              sortKey={applied.sort}
              sortDir={applied.order === 'DESC' ? 'desc' : 'asc'}
              onSort={sortBy}
              filtersOpen={filtersOpen}
              filters={filters}
              onFilter={(key, value) => setFilters((current) => ({ ...current, [key]: value }))}
              leading={canSelect ? <th className="w-10 px-4 py-2.5" /> : undefined}
              trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>}
            />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((user) => {
              const id = String(user.id)
              const protectedAccount = user.role === 'Super Admin'
              return (
                <tr key={id}>
                  {canSelect && (
                    <td className="px-4 py-2">
                      {!protectedAccount && (
                        <input type="checkbox" checked={selected.includes(id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, id] : current.filter((item) => item !== id))} />
                      )}
                    </td>
                  )}
                  <td className="px-4 py-2 font-medium text-gray-800">{user.username}</td>
                  <td className="px-4 py-2">{user.role}</td>
                  <td className="px-4 py-2">{user.status}</td>
                  <td className="px-4 py-2">{user.last_login}</td>
                  <td className="px-4 py-2 text-right">
                    <span className="inline-flex gap-2">
                      {flags.change && <button type="button" className="text-[10px] font-bold text-indigo-700" onClick={() => void openEdit(id)}>Edit</button>}
                      {flags.manage && flags.change && <Link className="text-[10px] font-bold text-blue-700" to={`/admin/users/${id}/permissions`}>Permissions</Link>}
                      {flags.change && !protectedAccount && <button type="button" className="text-[10px] font-bold text-amber-700" onClick={() => void run(`/api/users/${id}/status`, 'Status updated.')}>Status</button>}
                      {flags.password && !protectedAccount && <button type="button" className="text-[10px] font-bold text-gray-700" onClick={() => void run(`/api/users/${id}/password`, 'Password reset.')}>Reset</button>}
                      {flags.delete && user.status !== 'inactive' && !protectedAccount && <button type="button" className="text-[10px] font-bold text-red-600" onClick={() => void run(`/api/users/${id}/deactivate`, `${String(user.username)} was deactivated.`)}>Delete</button>}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
      </div>
      <TablePager page={page} totalPages={totalPages} pageSize={perPage} onPage={setPage} onPageSize={(size) => { setPerPage(size); setPage(1) }} />
      {inviteOpen && (
        <form onSubmit={invite} className="space-y-3 border-t border-gray-100 p-5">
          <div className="grid gap-3 md:grid-cols-3">
            <input required value={inviteName} onChange={(event) => setInviteName(event.target.value)} placeholder="Full name" className="rounded-xl border px-3 py-2 text-sm" />
            <input required type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="Email" className="rounded-xl border px-3 py-2 text-sm" />
            <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)} className="rounded-xl border px-3 py-2 text-sm">
              <option value="Teacher">Teacher</option>
              <option value="Student">Student</option>
            </select>
          </div>
          <p className="text-[10px] text-gray-500">The invitation link expires in 7 days.</p>
          <div className="flex gap-2">
            <button type="submit" className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white">Send invitation</button>
            <button type="button" onClick={() => setInviteOpen(false)} className="rounded-xl border px-4 py-2 text-xs font-bold">Cancel</button>
          </div>
        </form>
      )}
      {editor && (
        <form onSubmit={saveEdit} className="space-y-3 border-t border-gray-100 p-5">
          <h3 className="text-xs font-bold text-gray-800">Edit account</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <input required value={editor.username} onChange={(event) => setEditor({ ...editor, username: event.target.value })} className="rounded-xl border px-3 py-2 text-sm" />
            <select required value={editor.role} onChange={(event) => setEditor({ ...editor, role: event.target.value })} className="rounded-xl border px-3 py-2 text-sm">
              {editRoles.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select value={editor.department_id} onChange={(event) => setEditor({ ...editor, department_id: event.target.value })} className="rounded-xl border px-3 py-2 text-sm">
              <option value="">No department</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <input type="email" value={editor.email} onChange={(event) => setEditor({ ...editor, email: event.target.value })} placeholder="Email" className="rounded-xl border px-3 py-2 text-sm" />
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="New password, optional" className="rounded-xl border px-3 py-2 text-sm" />
            <select value={editor.status} onChange={(event) => setEditor({ ...editor, status: event.target.value })} className="rounded-xl border px-3 py-2 text-sm">
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-xs font-bold text-gray-700">
            <input type="checkbox" checked={editor.is_hod} onChange={(event) => setEditor({ ...editor, is_hod: event.target.checked })} />
            Head of department
          </label>
          <div className="flex gap-2">
            <button type="submit" className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white">Save changes</button>
            <button type="button" onClick={() => setEditor(null)} className="rounded-xl border px-4 py-2 text-xs font-bold">Cancel</button>
          </div>
        </form>
      )}
    </section>
  )
}

