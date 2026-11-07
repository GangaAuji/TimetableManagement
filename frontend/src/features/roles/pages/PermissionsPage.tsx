import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Permission = { id: number; module: string; name: string; description: string }
const permissionColumns: TableColumnSpec[] = [
  { key: 'action', label: 'Action', sortable: false },
  { key: 'name', label: 'Permission', sortable: false },
  { key: 'description', label: 'What it allows', sortable: false },
]

function actionLabel(name: string) {
  if (name.includes('_delete') || name.startsWith('delete')) return 'Delete'
  if (name.includes('_add') || name.startsWith('add')) return 'Add'
  if (name.includes('_view') || name.startsWith('view')) return 'View'
  if (name.includes('_change') || name.includes('_update') || name.includes('_edit')) return 'Update'
  return 'Other'
}

export function PermissionsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Permission[]>([])
  const [canAdd, setCanAdd] = useState(false)
  const [moduleName, setModuleName] = useState('')
  const [activeModule, setActiveModule] = useState('All modules')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [query, setQuery] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [filters, setFilters] = useState({ action: '', name: '', description: '' })
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  function load() {
    return apiRequest<{ permissions?: Record<string, unknown>[]; can_add?: boolean }>('/api/permissions').then((data) => {
      setRows((data.permissions || []).map((row) => ({
        id: safeCount(row.id),
        module: safeText(row.module, 50) || 'General',
        name: safeText(row.name, 50),
        description: safeText(row.description, 200),
      })).filter((row) => row.id > 0 && row.name))
      setCanAdd(data.can_add === true)
    })
  }

  useEffect(() => {
    setPageHeader('Permissions')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  const modules = useMemo(() => {
    const groups = new Map<string, Permission[]>()
    for (const row of rows) {
      const list = groups.get(row.module) || []
      list.push(row)
      groups.set(row.module, list)
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right))
  }, [rows])
  const needle = query.trim().toLowerCase()
  const actionText = filters.action.trim().toLowerCase()
  const nameText = filters.name.trim().toLowerCase()
  const descriptionText = filters.description.trim().toLowerCase()
  const visibleModules = modules
    .map(([module, items]) => [module, items.filter((item) => {
      const action = actionLabel(item.name).toLowerCase()
      const blob = `${module} ${action} ${item.name} ${item.description}`.toLowerCase()
      if (needle && !blob.includes(needle)) return false
      if (actionText && !action.includes(actionText)) return false
      if (nameText && !item.name.toLowerCase().includes(nameText)) return false
      if (descriptionText && !item.description.toLowerCase().includes(descriptionText)) return false
      return true
    })] as const)
    .filter(([, items]) => items.length > 0)
  const shown = activeModule === 'All modules' ? visibleModules : visibleModules.filter(([module]) => module === activeModule)

  async function add(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson('/api/permissions', { name: name.trim().toLowerCase(), module: moduleName.trim(), description: description.trim() })
      setName('')
      setDescription('')
      setActiveModule(moduleName.trim() || 'All modules')
      setNotice('Permission added. Assign it from a role to put it into use.')
      setAdding(false)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <header className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Permission catalog</h2>
          <p className="text-xs text-gray-500">{rows.length} permissions in {modules.length} modules. Pick a module to see what it controls.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/admin/roles" className="rounded-xl border border-gray-200 px-3 py-2 text-xs font-bold text-gray-700">Roles</Link>
          {canAdd && (
            <button type="button" onClick={() => setAdding((open) => !open)} className="rounded-xl bg-gray-900 px-3 py-2 text-xs font-bold text-white">
              {adding ? 'Close form' : 'Add permission'}
            </button>
          )}
        </div>
      </header>
      {adding && (
        <form onSubmit={(event) => void add(event)} className="mb-4 grid shrink-0 gap-3 rounded-2xl border border-gray-200 bg-white p-4 md:grid-cols-4">
          <label className="text-[10px] font-bold tracking-wide text-gray-500 uppercase">
            Module
            <input required list="permission-modules" value={moduleName} onChange={(event) => setModuleName(event.target.value)} placeholder="Courses" className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-medium normal-case" />
            <datalist id="permission-modules">{modules.map(([item]) => <option key={item} value={item} />)}</datalist>
          </label>
          <label className="text-[10px] font-bold tracking-wide text-gray-500 uppercase">
            Permission name
            <input required value={name} onChange={(event) => setName(event.target.value)} placeholder="courses_view_course" className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 font-mono text-sm font-medium normal-case" />
          </label>
          <label className="text-[10px] font-bold tracking-wide text-gray-500 uppercase">
            Description
            <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="View courses" className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm font-medium normal-case" />
          </label>
          <div className="flex items-end">
            <button type="submit" disabled={saving} className="rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">{saving ? 'Adding...' : 'Save permission'}</button>
          </div>
        </form>
      )}
      <div className="mb-4 overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <TableToolbar search={query} onSearch={setQuery} filtersOpen={filtersOpen} onToggleFilters={() => setFiltersOpen((open) => !open)} matched={visibleModules.reduce((sum, [, items]) => sum + items.length, 0)} source={rows.length} activeCount={(query.trim() ? 1 : 0) + Object.values(filters).filter((value) => value.trim()).length} onClear={() => { setQuery(''); setFilters({ action: '', name: '', description: '' }) }} />
      </div>
      {error && <p className="mb-3 rounded-xl border border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p>}
      <div className="grid min-h-0 flex-1 gap-2 lg:grid-cols-[240px_1fr]">
        <aside className="overflow-auto rounded-2xl border border-gray-200 bg-white p-2">
          <button type="button" onClick={() => setActiveModule('All modules')} className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-bold ${activeModule === 'All modules' ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-50'}`}>
            All modules
            <span className={activeModule === 'All modules' ? 'text-gray-300' : 'text-gray-400'}>{rows.length}</span>
          </button>
          {modules.map(([module, items]) => (
            <button key={module} type="button" onClick={() => { setActiveModule(module); setModuleName(module) }} className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs font-bold ${activeModule === module ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-50'}`}>
              <span className="truncate">{module}</span>
              <span className={`ml-2 shrink-0 ${activeModule === module ? 'text-gray-300' : 'text-gray-400'}`}>{items.length}</span>
            </button>
          ))}
        </aside>
        <div className="space-y-4 overflow-auto">
          {shown.map(([module, items]) => (
            <section key={module} className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
              <header className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
                <h3 className="text-sm font-bold text-gray-800">{module}</h3>
                <span className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">{items.length} permissions</span>
              </header>
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50">
                  <DataTableHead columns={permissionColumns} sortKey="" sortDir="asc" onSort={() => undefined} filtersOpen={filtersOpen} filters={filters} onFilter={(key, value) => setFilters((current) => ({ ...current, [key]: value }))} />
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td className="px-5 py-3"><span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold tracking-wide text-indigo-700 uppercase">{actionLabel(item.name)}</span></td>
                      <td className="px-3 py-3 font-mono text-xs text-gray-800">{item.name}</td>
                      <td className="px-5 py-3 text-xs text-gray-500">{item.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
          {rows.length > 0 && shown.length === 0 && <p className="py-10 text-center text-xs text-gray-400">No permissions match this search.</p>}
        </div>
      </div>
    </section>
  )
}
