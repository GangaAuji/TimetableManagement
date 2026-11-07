import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Assigned = { name: string; module: string; source: string; department_id: number | null; department_name: string }
type CatalogItem = { name: string; module: string; description: string }
type Department = { id: number; name: string }
type Group = { id: number; name: string }
type AssignedGroup = { group_id: number; name: string; department_id: number | null; department_name: string }

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'

function actionLabel(name: string) {
  if (name.includes('_delete') || name.startsWith('delete')) return 'Delete'
  if (name.includes('_add') || name.startsWith('add')) return 'Add'
  if (name.includes('_view') || name.startsWith('view')) return 'View'
  if (name.includes('_change') || name.includes('_update') || name.includes('_edit')) return 'Update'
  return 'Other'
}

function sourceLabel(source: string) {
  if (source === 'individual') return 'Individual'
  if (source === 'role') return 'Role'
  if (source === 'group') return 'Group'
  return source || 'Granted'
}

export function UserPermissionsPage() {
  const { userId } = useParams()
  const setPageHeader = useSetPageHeader()
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('')
  const [department, setDepartment] = useState('')
  const [assigned, setAssigned] = useState<Assigned[]>([])
  const [catalog, setCatalog] = useState<CatalogItem[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [assignedGroups, setAssignedGroups] = useState<AssignedGroup[]>([])
  const [departmentId, setDepartmentId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [groupDepartment, setGroupDepartment] = useState('')
  const [query, setQuery] = useState('')
  const [moduleName, setModuleName] = useState('All modules')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await apiRequest<{
      user?: { username?: string; role?: string; department_name?: string }
      assigned?: Assigned[]
      catalog?: Record<string, unknown>[]
      departments?: Department[]
      groups?: Group[]
      assigned_groups?: AssignedGroup[]
    }>(`/api/users/${userId}/access`)
    setUsername(safeText(data.user?.username, 50))
    setRole(safeText(data.user?.role, 50))
    setDepartment(safeText(data.user?.department_name, 100))
    setAssigned(data.assigned || [])
    setCatalog((data.catalog || []).flatMap((row) => {
      const name = safeText(row.name, 80)
      if (!name) return []
      return [{ name, module: safeText(row.module, 50) || 'General', description: safeText(row.description, 200) }]
    }))
    setDepartments((data.departments || []).flatMap((item) => {
      const id = safeCount(item.id)
      const name = safeText(item.name, 100)
      return id > 0 && name ? [{ id, name }] : []
    }))
    setGroups((data.groups || []).flatMap((item) => {
      const id = safeCount(item.id)
      const name = safeText(item.name, 80)
      return id > 0 && name ? [{ id, name }] : []
    }))
    setAssignedGroups(data.assigned_groups || [])
  }

  useEffect(() => {
    setPageHeader('User permissions')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader, userId])

  const scope = departmentId ? Number(departmentId) : null
  const scopeName = departments.find((item) => item.id === scope)?.name || 'Global'

  function rowsFor(name: string) {
    return assigned.filter((item) => item.name === name)
  }

  function individualAtScope(name: string) {
    return assigned.find((item) => item.source === 'individual' && item.name === name && (item.department_id || null) === scope)
  }

  function lockedFor(name: string) {
    return rowsFor(name).filter((item) => item.source !== 'individual')
  }

  async function grantNames(names: string[]) {
    if (names.length === 0) return
    if (names.length === 1) {
      await postJson(`/api/users/${userId}/permissions`, { permission_name: names[0], department_id: scope })
      return
    }
    await postJson(`/api/users/${userId}/permissions/bulk`, { permission_names: names, department_id: scope })
  }

  async function revokeRow(row: Assigned) {
    await postJson(`/api/users/${userId}/permissions/revoke`, {
      permission_name: row.name,
      department_id: row.department_id,
    })
  }

  async function toggle(item: CatalogItem) {
    const current = individualAtScope(item.name)
    if (!current && lockedFor(item.name).length > 0) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (current) {
        await revokeRow(current)
        setNotice('Permission revoked.')
      } else {
        await grantNames([item.name])
        setNotice('Permission granted.')
      }
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function toggleModule(items: CatalogItem[], on: boolean) {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      if (on) {
        const names = items.filter((item) => !individualAtScope(item.name) && lockedFor(item.name).length === 0).map((item) => item.name)
        await grantNames(names)
        if (names.length > 0) setNotice('Selected permissions were granted.')
      } else {
        const rows = items.flatMap((item) => {
          const row = individualAtScope(item.name)
          return row ? [row] : []
        })
        for (const row of rows) await revokeRow(row)
        if (rows.length > 0) setNotice('Permission revoked.')
      }
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function grantGroup() {
    if (!groupId) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson(`/api/users/${userId}/groups`, {
        group_id: Number(groupId),
        department_id: groupDepartment ? Number(groupDepartment) : null,
      })
      setNotice('Permission group granted.')
      setGroupId('')
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function revokeGroup(group: AssignedGroup) {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson(`/api/users/${userId}/groups/revoke`, {
        group_id: group.group_id,
        department_id: group.department_id,
      })
      setNotice('Permission group removed.')
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const needle = query.trim().toLowerCase()
  const modules = useMemo(() => {
    const groupsByModule = new Map<string, CatalogItem[]>()
    for (const item of catalog) {
      const list = groupsByModule.get(item.module) || []
      list.push(item)
      groupsByModule.set(item.module, list)
    }
    return [...groupsByModule.entries()].map(([module, items]) => ({
      module,
      items,
      visible: items.filter((item) => !needle || `${module} ${item.name} ${item.description} ${actionLabel(item.name)}`.toLowerCase().includes(needle)),
    })).filter((group) => group.visible.length > 0)
  }, [catalog, needle])

  const heldNames = new Set(assigned.map((item) => item.name))
  const active = moduleName === 'All modules' ? modules : modules.filter((group) => group.module === moduleName)
  const heldCount = catalog.filter((item) => heldNames.has(item.name)).length

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-4 shadow-sm">
        <div>
          <Link to="/admin/users" className="text-xs font-semibold text-indigo-600">Users</Link>
          <h2 className="text-lg font-bold text-gray-800">{username || 'User permissions'}</h2>
          <p className="text-xs text-gray-500">{role || 'No role'}{department ? ` · ${department}` : ''} · {heldCount} of {catalog.length} permissions granted</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search permissions" className="rounded border border-gray-300 bg-gray-50 px-3 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500" />
          <label className="text-xs font-semibold text-gray-700">
            Grant scope
            <select value={departmentId} onChange={(event) => setDepartmentId(event.target.value)} className="ml-2 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium">
              <option value="">Global</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
        </div>
      </header>

      <section className="mb-4 shrink-0 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-gray-800">Permission groups</h3>
            <p className="text-[10px] text-gray-400">Groups stay with this user until you remove them.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select value={groupId} onChange={(event) => setGroupId(event.target.value)} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-xs" aria-label="Permission group">
              <option value="">Choose a group</option>
              {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
            </select>
            <select value={groupDepartment} onChange={(event) => setGroupDepartment(event.target.value)} className="rounded border border-gray-300 bg-white px-3 py-1.5 text-xs" aria-label="Group scope">
              <option value="">Global scope</option>
              {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <button type="button" disabled={saving || !groupId} onClick={() => void grantGroup()} className={primaryButton}>Add group</button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {assignedGroups.length === 0 ? <p className="text-xs text-gray-400">No groups assigned.</p> : assignedGroups.map((group) => (
            <span key={`${group.group_id}-${group.department_id || 'global'}`} className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-semibold text-gray-700">
              {group.name} · {group.department_name || 'Global'}
              <button type="button" disabled={saving} className="font-bold text-red-600" onClick={() => void revokeGroup(group)}>Remove</button>
            </span>
          ))}
        </div>
      </section>

      {error && <p className="mb-3 rounded-xl border border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}

      <div className="grid min-h-0 flex-1 gap-2 lg:grid-cols-[240px_1fr]">
        <aside className="overflow-auto rounded-2xl border border-gray-200 bg-white p-2">
          <ModuleButton label="All modules" count={catalog.length} granted={heldCount} active={moduleName === 'All modules'} onClick={() => setModuleName('All modules')} />
          {modules.map((group) => (
            <ModuleButton
              key={group.module}
              label={group.module}
              count={group.items.length}
              granted={group.items.filter((item) => heldNames.has(item.name)).length}
              active={moduleName === group.module}
              onClick={() => setModuleName(group.module)}
            />
          ))}
        </aside>
        <div className="space-y-4 overflow-auto">
          {active.map((group) => {
            const controllable = group.items.filter((item) => lockedFor(item.name).length === 0 || individualAtScope(item.name))
            const moduleOn = group.items.length > 0 && group.items.every((item) => heldNames.has(item.name) || Boolean(individualAtScope(item.name)))
            const partial = !moduleOn && group.items.some((item) => heldNames.has(item.name))
            return (
              <section key={group.module} className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
                <header className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-3">
                  <div>
                    <h3 className="text-sm font-bold text-gray-800">{group.module}</h3>
                    <p className="text-[10px] font-medium text-gray-400">{group.items.filter((item) => heldNames.has(item.name)).length} of {group.items.length} granted · new grants use {scopeName}</p>
                  </div>
                  <label className="flex items-center gap-2 text-xs font-bold text-gray-600">
                    <input
                      type="checkbox"
                      checked={moduleOn}
                      ref={(node) => { if (node) node.indeterminate = partial }}
                      disabled={saving || controllable.length === 0}
                      onChange={(event) => void toggleModule(group.items, event.target.checked)}
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
                      <th className="px-5 py-2">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {group.visible.map((item) => {
                      const current = individualAtScope(item.name)
                      const locked = lockedFor(item.name)
                      const others = rowsFor(item.name).filter((row) => row !== current)
                      const checked = Boolean(current) || locked.length > 0
                      const disabled = saving || (locked.length > 0 && !current)
                      return (
                        <tr key={item.name} className={checked ? 'bg-indigo-50/60' : undefined}>
                          <td className="px-5 py-3">
                            <input type="checkbox" checked={checked} disabled={disabled} onChange={() => void toggle(item)} aria-label={`${group.module} ${item.name}`} className="h-4 w-4 accent-indigo-600" />
                          </td>
                          <td className="px-3 py-3"><span className="rounded-full bg-gray-100 px-2 py-1 text-[10px] font-bold tracking-wide text-gray-600 uppercase">{actionLabel(item.name)}</span></td>
                          <td className="px-3 py-3 font-mono text-xs text-gray-800">{item.name}</td>
                          <td className="px-5 py-3 text-xs text-gray-500">{item.description || '—'}</td>
                          <td className="px-5 py-3 text-xs text-gray-500">
                            {current ? <span className="mr-2 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">Individual · {scopeName}</span> : null}
                            {locked.map((row) => <span key={`${row.source}-${row.department_id || 'global'}`} className="mr-2 rounded-full bg-gray-100 px-2 py-1 text-[10px] font-bold text-gray-600">{sourceLabel(row.source)}{row.department_name ? ` · ${row.department_name}` : ''}</span>)}
                            {others.filter((row) => row.source === 'individual').map((row) => <span key={`other-${row.department_id || 'global'}`} className="mr-2 text-[10px]">Also {row.department_name || 'Global'}</span>)}
                            {!checked && others.length === 0 ? '—' : null}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </section>
            )
          })}
          {catalog.length > 0 && active.length === 0 && <p className="py-10 text-center text-xs text-gray-400">No permissions match this search.</p>}
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
