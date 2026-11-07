import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Dialog, fieldClass } from '../../academics/ui'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TablePager, TableToolbar, useDataTable, type TableColumnSpec } from '../../../shared/components/table-page'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { safeCount, safeText } from '../../../shared/security/sanitize'

const primaryButton = 'inline-block rounded-xl bg-gray-900 px-4 py-2 text-center text-xs font-bold text-white'
const secondaryButton = 'inline-block rounded-xl border border-gray-200 px-3 py-2 text-center text-xs font-bold text-gray-800'

type RoleRow = { id: string; name: string; description: string; level: number; users: string; permissions: string }

export function RolesPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<RoleRow[]>([])
  const [canAdd, setCanAdd] = useState(false)
  const [canUpdate, setCanUpdate] = useState(false)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [level, setLevel] = useState('2')
  const [saving, setSaving] = useState(false)

  function load() {
    return apiRequest<{ roles?: Record<string, unknown>[]; can_add?: boolean; can_update?: boolean }>('/api/roles').then((data) => {
      setCanAdd(data.can_add === true)
      setCanUpdate(data.can_update === true)
      setRows((data.roles || []).map((role) => ({
        id: String(safeCount(role.id)),
        name: safeText(role.name, 50),
        description: safeText(role.description, 400),
        level: safeCount(role.hierarchy_level) || 50,
        users: String(safeCount(role.user_count)),
        permissions: String(safeCount(role.permission_count)),
      })))
    })
  }

  useEffect(() => {
    setPageHeader('Roles')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function openAdd() {
    const highest = rows.reduce((top, row) => Math.max(top, row.level), 1)
    setName('')
    setDescription('')
    setLevel(String(Math.min(99, Math.max(2, highest + 1))))
    setFormOpen(true)
    setNotice('')
    setError('')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson('/api/roles', {
        name: name.trim(),
        description: description.trim(),
        hierarchy_level: name.trim() === 'Super Admin' ? 1 : Number(level),
      })
      setNotice('Role added. Open Update role to set its permissions.')
      setFormOpen(false)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const needle = query.trim().toLowerCase()
  const visible = rows.filter((row) => !needle || `${row.name} ${row.description}`.toLowerCase().includes(needle))
  const lockedLevel = name.trim() === 'Super Admin'

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-5 py-4">
        <div>
          <h2 className="text-lg font-bold text-gray-800">Roles</h2>
          <p className="text-xs text-gray-500">{rows.length} roles</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search roles" className="rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500" />
          <Link to="/admin/permissions" className={secondaryButton}>Permission catalog</Link>
          {canAdd && <button type="button" onClick={openAdd} className={primaryButton}>Add role</button>}
        </div>
      </header>
      {error && !formOpen && <p className="mb-3 text-xs text-red-700">{error}</p>}
      {notice && <p className="mb-3 text-xs text-gray-600">{notice}</p>}
      <div className="grid flex-1 content-start gap-2 overflow-auto sm:grid-cols-2 xl:grid-cols-3">
        {rows.length > 0 && visible.length === 0 && <p className="col-span-full py-10 text-center text-xs text-gray-400">No roles match this search.</p>}
        {visible.map((row) => (
          <article key={row.id} className="flex flex-col rounded-2xl border border-gray-200 bg-white p-5">
            <div className="flex items-start gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-sm font-semibold text-gray-700">
                {row.name.slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0">
                <h3 className="truncate text-base font-semibold text-gray-800">{row.name}</h3>
                <p className="mt-1 line-clamp-2 text-xs text-gray-500">{row.description || 'No description'}</p>
              </div>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-gray-100 px-3 py-2">
                <dt className="text-xs text-gray-500">People</dt>
                <dd className="text-lg font-semibold text-gray-800">{row.users}</dd>
              </div>
              <div className="rounded-lg border border-gray-100 px-3 py-2">
                <dt className="text-xs text-gray-500">Permissions</dt>
                <dd className="text-lg font-semibold text-gray-800">{row.permissions}</dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Link to={`/admin/roles/${row.id}/users`} className={secondaryButton}>View roles</Link>
              {canUpdate && <Link to={`/admin/roles/${row.id}`} className={primaryButton}>Update role</Link>}
            </div>
          </article>
        ))}
      </div>
      {formOpen && (
        <Dialog title="Add role" onClose={() => setFormOpen(false)}>
          <form className="grid gap-4" onSubmit={(event) => void save(event)}>
            <label className="text-xs font-semibold text-gray-700">Role name
              <input required value={name} maxLength={50} onChange={(event) => setName(event.target.value)} className={fieldClass()} />
            </label>
            <label className="text-xs font-semibold text-gray-700">Description
              <input value={description} maxLength={400} onChange={(event) => setDescription(event.target.value)} className={fieldClass()} />
            </label>
            <label className="text-xs font-semibold text-gray-700">Hierarchy level
              <input required type="number" min={1} max={99} value={lockedLevel ? '1' : level} disabled={lockedLevel} onChange={(event) => setLevel(event.target.value)} className={fieldClass()} />
            </label>
            <p className="text-xs text-gray-500">Super Admin is 1. Use 2, 3, 4, and so on for the roles under it. The same numbers work for a college or a school.</p>
            {error && <p className="text-sm text-red-700">{error}</p>}
            <button type="submit" disabled={saving} className={primaryButton}>{saving ? 'Saving...' : 'Save'}</button>
          </form>
        </Dialog>
      )}
    </section>
  )
}

type AssignedUser = { id: string; username: string; status: string; last_login: string }

const userColumns: TableColumnSpec[] = [
  { key: 'username', label: 'Username' },
  { key: 'status', label: 'Status' },
  { key: 'last_login', label: 'Last login' },
]

export function RoleAssignmentsPage() {
  const { roleId } = useParams()
  const setPageHeader = useSetPageHeader()
  const [roleName, setRoleName] = useState('')
  const [users, setUsers] = useState<AssignedUser[]>([])
  const [canUpdate, setCanUpdate] = useState(false)
  const [canDelete, setCanDelete] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState<AssignedUser | null>(null)
  const [saving, setSaving] = useState(false)
  const valueOf = useCallback((row: AssignedUser, key: string) => row[key as keyof AssignedUser], [])
  const table = useDataTable(users, userColumns, valueOf)

  function load(id: string) {
    return apiRequest<{ role?: unknown; can_update?: boolean; can_delete?: boolean; users?: Record<string, unknown>[] }>(`/api/roles/${id}/users`).then((data) => {
      setRoleName(safeText(data.role, 50))
      setCanUpdate(data.can_update === true)
      setCanDelete(data.can_delete === true)
      setUsers((data.users || []).flatMap((user) => {
        const idValue = String(safeCount(user.id))
        const username = safeText(user.username, 50)
        if (idValue === '0' || !username) return []
        return [{ id: idValue, username, status: safeText(user.status, 20), last_login: safeText(user.last_login, 19) }]
      }))
    })
  }

  useEffect(() => {
    setPageHeader('View roles')
    if (!roleId || !/^\d+$/.test(roleId)) {
      setError('That role was not found.')
      return
    }
    void load(roleId).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [roleId, setPageHeader])

  async function removeUser() {
    if (!pending || !roleId) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson(`/api/users/${pending.id}/deactivate`, {})
      setNotice(`${pending.username} was deactivated.`)
      setPending(null)
      await load(roleId)
    } catch (reason) {
      setError(messageFrom(reason))
      setPending(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="grid min-h-0 flex-1 gap-2 lg:grid-cols-[240px_1fr]">
      <aside className="flex h-fit flex-col gap-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <Link to="/admin/roles" className="text-xs font-bold text-gray-500">Roles</Link>
        <h2 className="text-lg font-bold text-gray-800">{roleName || 'Role'}</h2>
        {canUpdate && roleId && <Link to={`/admin/roles/${roleId}`} className={primaryButton}>Update role</Link>}
      </aside>
      <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md">
        {users.length === 500 && <p className="px-4 py-2 text-xs text-gray-500">Showing the first 500 users.</p>}
        {error && <p className="px-4 py-2 text-xs text-red-700">{error}</p>}
        {notice && <p className="px-4 py-2 text-xs text-emerald-700">{notice}</p>}
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="sticky top-0 z-10 bg-gray-50">
              <DataTableHead columns={userColumns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {users.length === 0 && !error ? (
                <tr><td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">No users are assigned to this role.</td></tr>
              ) : table.rows.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">No users match these filters.</td></tr>
              ) : table.rows.map((user) => (
                <tr key={user.id} className="group hover:bg-indigo-50">
                  <td className="px-4 py-2 font-semibold text-gray-900">{user.username}</td>
                  <td className="px-4 py-2 text-gray-700">{user.status || '—'}</td>
                  <td className="px-4 py-2 text-gray-600">{user.last_login || '—'}</td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <div className="flex justify-end gap-2">
                      <Link to={`/admin/users?search=${encodeURIComponent(user.username)}&role=${encodeURIComponent(roleName)}`} title="View user" className="rounded p-1.5 text-blue-600 hover:bg-blue-50 hover:text-blue-800">
                        <i className="fas fa-eye" />
                      </Link>
                      {canDelete && user.status !== 'inactive' && (
                        <button type="button" title="Delete user" className="rounded p-1.5 text-red-600 hover:bg-red-50 hover:text-red-800" onClick={() => setPending(user)}>
                          <i className="fas fa-trash-alt" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
      </section>
      {pending && (
        <Dialog title="Delete user?" onClose={() => setPending(null)}>
          <p className="text-sm text-gray-600">Deactivate {pending.username}? The account stays in the records but can no longer sign in.</p>
          <button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white disabled:opacity-60" onClick={() => void removeUser()}>{saving ? 'Deleting...' : 'Delete'}</button>
        </Dialog>
      )}
    </section>
  )
}

type RolePermission = { id: number; module: string; name: string; description: string }

function actionLabel(name: string) {
  if (name.includes('_delete') || name.startsWith('delete')) return 'Delete'
  if (name.includes('_add') || name.startsWith('add')) return 'Add'
  if (name.includes('_view') || name.startsWith('view')) return 'View'
  if (name.includes('_change') || name.includes('_update') || name.includes('_edit')) return 'Update'
  return name.replaceAll('_', ' ')
}

export function RolePermissionsPage() {
  const { roleId } = useParams()
  const setPageHeader = useSetPageHeader()
  const [role, setRole] = useState('')
  const [description, setDescription] = useState('')
  const [level, setLevel] = useState('2')
  const [rows, setRows] = useState<RolePermission[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [canUpdate, setCanUpdate] = useState(false)
  const [query, setQuery] = useState('')
  const [moduleName, setModuleName] = useState('All modules')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingRole, setSavingRole] = useState(false)

  useEffect(() => {
    setPageHeader('Update role')
    void apiRequest<{ role?: unknown; description?: unknown; hierarchy_level?: unknown; permissions?: Record<string, unknown>[]; can_update?: boolean }>(`/api/roles/${roleId}/permissions`)
      .then((data) => {
        const granted: number[] = []
        const next = (data.permissions || []).flatMap((row) => {
          const id = safeCount(row.id)
          const name = safeText(row.name, 50)
          if (id <= 0 || !name) return []
          if (row.granted === true) granted.push(id)
          return [{ id, module: safeText(row.module, 50) || 'General', name, description: safeText(row.description, 200) }]
        })
        setRole(safeText(data.role, 50))
        setDescription(safeText(data.description, 400))
        setLevel(String(safeCount(data.hierarchy_level) || 2))
        setRows(next)
        setSelected(granted)
        setCanUpdate(data.can_update === true)
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [roleId, setPageHeader])

  const chosen = useMemo(() => new Set(selected), [selected])
  const needle = query.trim().toLowerCase()
  const modules = useMemo(() => {
    const groups = new Map<string, RolePermission[]>()
    for (const row of rows) {
      const list = groups.get(row.module) || []
      list.push(row)
      groups.set(row.module, list)
    }
    return [...groups.entries()].map(([module, items]) => ({
      module,
      items,
      visible: items.filter((item) => !needle || `${module} ${item.name} ${item.description} ${actionLabel(item.name)}`.toLowerCase().includes(needle)),
    })).filter((group) => group.visible.length > 0)
  }, [needle, rows])

  function toggle(id: number) {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  function toggleMany(ids: number[], on: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return [...next]
    })
  }

  async function saveRole(event: FormEvent) {
    event.preventDefault()
    if (!canUpdate || !roleId) return
    setSavingRole(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest(`/api/roles/${roleId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({
          name: role.trim(),
          description: description.trim(),
          hierarchy_level: role.trim() === 'Super Admin' ? 1 : Number(level),
        }),
      })
      setNotice('Role updated.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSavingRole(false)
    }
  }

  async function save() {
    if (!canUpdate || !roleId) return
    if (selected.length === 0 && !window.confirm('This removes every permission from this role. Continue?')) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest(`/api/roles/${roleId}/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ permission_ids: selected }),
      })
      setNotice(`Saved ${selected.length} permissions. The previous set was replaced.`)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const allIds = rows.map((row) => row.id)
  const allOn = allIds.length > 0 && allIds.every((id) => chosen.has(id))
  const active = moduleName === 'All modules' ? modules : modules.filter((group) => group.module === moduleName)
  const lockedLevel = role.trim() === 'Super Admin'

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-4 shadow-sm">
        <div>
          <Link to="/admin/roles" className="text-xs font-semibold text-indigo-600">Roles</Link>
          <h2 className="text-lg font-bold text-gray-800">{role || 'Update role'}</h2>
          <p className="text-xs text-gray-500">{selected.length} of {rows.length} permissions granted</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this role" className="rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500" />
          {canUpdate && (
            <>
              <label className="flex items-center gap-2 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700">
                <input type="checkbox" checked={allOn} onChange={(event) => toggleMany(allIds, event.target.checked)} aria-label="Select all permissions" />
                Select all
              </label>
              <button type="button" disabled={saving} onClick={() => void save()} className={primaryButton}>
                {saving ? 'Saving…' : 'Save permissions'}
              </button>
            </>
          )}
        </div>
      </header>
      {canUpdate && (
        <form onSubmit={(event) => void saveRole(event)} className="mb-4 grid shrink-0 gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm md:grid-cols-4">
          <label className="text-xs font-semibold text-gray-700">Role name
            <input required value={role} maxLength={50} disabled={lockedLevel} onChange={(event) => setRole(event.target.value)} className={fieldClass()} />
          </label>
          <label className="text-xs font-semibold text-gray-700">Description
            <input value={description} maxLength={400} onChange={(event) => setDescription(event.target.value)} className={fieldClass()} />
          </label>
          <label className="text-xs font-semibold text-gray-700">Hierarchy level
            <input required type="number" min={1} max={99} value={lockedLevel ? '1' : level} disabled={lockedLevel} onChange={(event) => setLevel(event.target.value)} className={fieldClass()} />
          </label>
          <div className="flex items-end">
            <button type="submit" disabled={savingRole} className={primaryButton}>{savingRole ? 'Saving…' : 'Save role'}</button>
          </div>
        </form>
      )}
      {error && <p className="mb-3 rounded-xl border border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}
      {!canUpdate && !error && <p className="mb-3 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs text-gray-500">You can view these permissions. Updating them needs the role change permission.</p>}
      <div className="grid min-h-0 flex-1 gap-2 lg:grid-cols-[240px_1fr]">
        <aside className="overflow-auto rounded-2xl border border-gray-200 bg-white p-2">
          <ModuleButton label="All modules" count={rows.length} granted={selected.length} active={moduleName === 'All modules'} onClick={() => setModuleName('All modules')} />
          {modules.map((group) => {
            const granted = group.items.filter((item) => chosen.has(item.id)).length
            return (
              <ModuleButton
                key={group.module}
                label={group.module}
                count={group.items.length}
                granted={granted}
                active={moduleName === group.module}
                onClick={() => setModuleName(group.module)}
              />
            )
          })}
        </aside>
        <div className="space-y-4 overflow-auto">
          {active.map((group) => {
            const ids = group.items.map((item) => item.id)
            const moduleOn = ids.length > 0 && ids.every((id) => chosen.has(id))
            const partial = !moduleOn && ids.some((id) => chosen.has(id))
            return (
              <section key={group.module} className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
                <header className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-3">
                  <div>
                    <h3 className="text-sm font-bold text-gray-800">{group.module}</h3>
                    <p className="text-[10px] font-medium text-gray-400">{ids.filter((id) => chosen.has(id)).length} of {ids.length} granted</p>
                  </div>
                  <label className="flex items-center gap-2 text-xs font-bold text-gray-600">
                    <input
                      type="checkbox"
                      checked={moduleOn}
                      ref={(node) => { if (node) node.indeterminate = partial }}
                      disabled={!canUpdate}
                      onChange={(event) => toggleMany(ids, event.target.checked)}
                      aria-label={`Select all ${group.module} permissions`}
                    />
                    Select module
                  </label>
                </header>
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                    <tr>
                      <th className="w-16 px-5 py-2">Grant</th>
                      <th className="px-3 py-2">Action</th>
                      <th className="px-3 py-2">Permission</th>
                      <th className="px-5 py-2">What it allows</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {group.visible.map((item) => (
                      <tr key={item.id} className={chosen.has(item.id) ? 'bg-indigo-50/60' : undefined}>
                        <td className="px-5 py-3">
                          <input type="checkbox" checked={chosen.has(item.id)} disabled={!canUpdate} onChange={() => toggle(item.id)} aria-label={`${group.module} ${item.name}`} className="h-4 w-4 accent-indigo-600" />
                        </td>
                        <td className="px-3 py-3"><span className="rounded-full bg-gray-100 px-2 py-1 text-[10px] font-bold tracking-wide text-gray-600 uppercase">{actionLabel(item.name)}</span></td>
                        <td className="px-3 py-3 font-mono text-xs text-gray-800">{item.name}</td>
                        <td className="px-5 py-3 text-xs text-gray-500">{item.description || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )
          })}
          {rows.length > 0 && active.length === 0 && <p className="py-10 text-center text-xs text-gray-400">No permissions match this search.</p>}
        </div>
      </div>
    </section>
  )
}

function ModuleButton({ label, count, granted, active, onClick }: { label: string; count: number; granted: number; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left ${active ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-50'}`}>
      <span className="truncate text-xs font-bold">{label}</span>
      <span className={`ml-2 shrink-0 text-[10px] font-bold ${active ? 'text-gray-300' : 'text-gray-400'}`}>{granted}/{count}</span>
    </button>
  )
}
