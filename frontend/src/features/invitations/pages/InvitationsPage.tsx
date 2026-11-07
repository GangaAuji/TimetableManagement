import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { DataTableHead, TablePager, TableToolbar, type TableColumnSpec } from '../../../shared/components/table-page'
import { Dialog, fieldClass } from '../../academics/ui'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Catalog = { id: string; name: string }
type Invitation = {
  id: string
  name: string
  email: string
  role: string
  status: string
  course_name: string
  department_name: string
  expires_at: string
}

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const invitationColumns: TableColumnSpec[] = [
  { key: 'name', label: 'Name', sortable: false },
  { key: 'email', label: 'Email', sortable: false },
  { key: 'role', label: 'Role', sortable: false },
  { key: 'place', label: 'Place', sortable: false },
  { key: 'status', label: 'Status', sortable: false },
  { key: 'expires_at', label: 'Expires', sortable: false },
]

function catalog(rows: unknown): Catalog[] {
  if (!Array.isArray(rows)) return []
  return rows.flatMap((row) => {
    if (!row || typeof row !== 'object') return []
    const record = row as Record<string, unknown>
    const id = String(safeCount(record.id))
    const name = safeText(record.name, 100)
    return id !== '0' && name ? [{ id, name }] : []
  })
}

export function InvitationsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Invitation[]>([])
  const [courses, setCourses] = useState<Catalog[]>([])
  const [classes, setClasses] = useState<Catalog[]>([])
  const [divisions, setDivisions] = useState<Catalog[]>([])
  const [departments, setDepartments] = useState<Catalog[]>([])
  const [stats, setStats] = useState({ pending: 0, used: 0, expired: 0, total: 0 })
  const [canInvite, setCanInvite] = useState(false)
  const [canChange, setCanChange] = useState(false)
  const [search, setSearch] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [filters, setFilters] = useState({ name: '', email: '', role: '', place: '', status: '', expires_at: '' })
  const [applied, setApplied] = useState({ search: '', name: '', email: '', role: '', place: '', status: '', expires_at: '' })
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pending, setPending] = useState<Invitation | null>(null)
  const [form, setForm] = useState({ name: '', email: '', role: 'Teacher', days_valid: '7', course_id: '', class_id: '', division_id: '', department_id: '' })

  function load(next: { search: string; name: string; email: string; role: string; place: string; status: string; expires_at: string }, nextPage: number, nextPerPage: number) {
    const params = new URLSearchParams({ page: String(nextPage), per_page: String(nextPerPage) })
    if (next.search) params.set('search', next.search)
    if (next.name) params.set('name', next.name)
    if (next.email) params.set('email', next.email)
    if (next.role) params.set('role', next.role)
    if (next.place) params.set('place', next.place)
    if (next.status === 'pending' || next.status === 'used' || next.status === 'expired') params.set('status', next.status)
    if (next.status) params.set('status_text', next.status)
    if (next.expires_at) params.set('expires', next.expires_at)
    return apiRequest<Record<string, unknown>>(`/api/invitations?${params}`).then((data) => {
      const counts = (data.stats && typeof data.stats === 'object' ? data.stats : {}) as Record<string, unknown>
      setStats({
        pending: safeCount(counts.pending),
        used: safeCount(counts.used),
        expired: safeCount(counts.expired),
        total: safeCount(counts.total),
      })
      setCourses(catalog(data.courses))
      setClasses(catalog(data.classes))
      setDivisions(catalog(data.divisions))
      setDepartments(catalog(data.departments))
      setCanInvite(data.can_invite === true)
      setCanChange(data.can_change === true)
      setTotalPages(Math.max(safeCount(data.total_pages), 1))
      setTotal(safeCount(data.total))
      setRows((Array.isArray(data.invitations) ? data.invitations : []).flatMap((row) => {
        if (!row || typeof row !== 'object') return []
        const record = row as Record<string, unknown>
        const id = String(safeCount(record.id))
        if (id === '0') return []
        return [{
          id,
          name: safeText(record.name, 100),
          email: safeText(record.email, 160),
          role: safeText(record.role, 50),
          status: safeText(record.status, 20),
          course_name: safeText(record.course_name, 100),
          department_name: safeText(record.department_name, 100),
          expires_at: safeText(record.expires_at, 19),
        }]
      }))
    })
  }

  useEffect(() => {
    setPageHeader('Invitations')
  }, [setPageHeader])

  useEffect(() => {
    void load(applied, page, perPage).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [applied, page, perPage])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = { search: search.trim(), name: filters.name.trim(), email: filters.email.trim(), role: filters.role.trim(), place: filters.place.trim(), status: filters.status.trim(), expires_at: filters.expires_at.trim() }
      setApplied((current) => {
        if (current.search === next.search && current.name === next.name && current.email === next.email && current.role === next.role && current.place === next.place && current.status === next.status && current.expires_at === next.expires_at) return current
        setPage(1)
        return next
      })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [filters, search])

  async function remember(link: string) {
    const path = safeText(link, 120)
    if (!path.startsWith('/register/')) return
    const url = `${window.location.origin}${path}`
    try {
      await navigator.clipboard.writeText(url)
      setNotice('Registration link copied.')
    } catch {
      setNotice(`Registration link: ${url}`)
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const data = await postJson<{ link?: string }>('/api/invitations', {
        name: form.name.trim(),
        email: form.email.trim(),
        role: form.role,
        days_valid: Number(form.days_valid),
        course_id: form.role === 'Student' && form.course_id ? Number(form.course_id) : null,
        class_id: form.role === 'Student' && form.class_id ? Number(form.class_id) : null,
        division_id: form.role === 'Student' && form.division_id ? Number(form.division_id) : null,
        department_id: form.role === 'Teacher' && form.department_id ? Number(form.department_id) : null,
      })
      setOpen(false)
      await remember(data.link || '')
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function resend(row: Invitation) {
    setError('')
    setNotice('')
    try {
      const data = await postJson<{ link?: string }>(`/api/invitations/${row.id}/resend`, {})
      await remember(data.link || '')
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function copy(row: Invitation) {
    setError('')
    try {
      const data = await apiRequest<{ link?: string }>(`/api/invitations/${row.id}/link`)
      await remember(data.link || '')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function revoke() {
    if (!pending) return
    setSaving(true)
    setError('')
    try {
      await postJson(`/api/invitations/${pending.id}/revoke`, {})
      setNotice('Invitation revoked.')
      setPending(null)
      await load(applied, page, perPage)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-sm font-bold text-gray-800">Invitations</h2>
          <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{stats.pending} pending · {stats.used} used · {stats.expired} expired · {stats.total} total</p>
        </div>
        {canInvite && <button type="button" onClick={() => { setOpen(true); setError('') }} className={primaryButton}>Create invitation</button>}
      </header>
      {error && <p className="px-5 py-2 text-xs text-red-700">{error}</p>}
      {notice && <p className="px-5 py-2 text-xs text-emerald-700">{notice}</p>}
      <TableToolbar search={search} onSearch={setSearch} filtersOpen={filtersOpen} onToggleFilters={() => setFiltersOpen((open) => !open)} matched={total} source={stats.total} activeCount={(search.trim() ? 1 : 0) + Object.values(filters).filter((value) => value.trim()).length} onClear={() => { setSearch(''); setFilters({ name: '', email: '', role: '', place: '', status: '', expires_at: '' }) }} />
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead columns={invitationColumns} sortKey="" sortDir="asc" onSort={() => undefined} filtersOpen={filtersOpen} filters={filters} onFilter={(key, value) => setFilters((current) => ({ ...current, [key]: value }))} trailing={<th className="px-4 py-2.5 text-right text-[10px] font-bold tracking-wider text-gray-400 uppercase">Actions</th>} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500">No invitations found.</td></tr>
            ) : rows.map((row) => (
              <tr key={row.id}>
                <td className="px-4 py-2 font-medium text-gray-800">{row.name}</td>
                <td className="px-4 py-2">{row.email}</td>
                <td className="px-4 py-2">{row.role}</td>
                <td className="px-4 py-2">{row.role === 'Teacher' ? row.department_name : row.course_name}</td>
                <td className="px-4 py-2"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${row.status === 'expired' ? 'bg-red-50 text-red-700' : row.status === 'used' ? 'bg-gray-100 text-gray-600' : 'bg-emerald-50 text-emerald-700'}`}>{row.status === 'expired' ? 'Expired' : row.status === 'used' ? 'Used' : 'Pending'}</span></td>
                <td className="px-4 py-2">{row.expires_at || '—'}</td>
                <td className="px-4 py-2 text-right">
                  {canChange && (
                    <span className="inline-flex gap-2">
                      {row.status === 'pending' && <button type="button" className="text-[10px] font-bold text-indigo-700" onClick={() => void copy(row)}>Copy link</button>}
                      {row.status !== 'used' && <button type="button" className="text-[10px] font-bold text-gray-700" onClick={() => void resend(row)}>Resend</button>}
                      {row.status === 'pending' && <button type="button" className="text-[10px] font-bold text-red-600" onClick={() => setPending(row)}>Revoke</button>}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TablePager page={page} totalPages={totalPages} pageSize={perPage} onPage={setPage} onPageSize={(size) => { setPerPage(size); setPage(1) }} />
      {open && (
        <Dialog title="Create invitation" onClose={() => setOpen(false)}>
          <form className="grid gap-4" onSubmit={(event) => void create(event)}>
            <label className="text-xs font-semibold text-gray-700">Name<input required maxLength={100} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">Email<input required type="email" maxLength={160} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">Role
              <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} className={fieldClass()}>
                <option value="Teacher">Teacher</option>
                <option value="Student">Student</option>
              </select>
            </label>
            <label className="text-xs font-semibold text-gray-700">Days valid<input required type="number" min={1} max={90} value={form.days_valid} onChange={(event) => setForm({ ...form, days_valid: event.target.value })} className={fieldClass()} /></label>
            {form.role === 'Teacher' && (
              <label className="text-xs font-semibold text-gray-700">Department
                <select value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })} className={fieldClass()}>
                  <option value="">None</option>
                  {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>
            )}
            {form.role === 'Student' && (
              <>
                <label className="text-xs font-semibold text-gray-700">Course
                  <select value={form.course_id} onChange={(event) => setForm({ ...form, course_id: event.target.value })} className={fieldClass()}>
                    <option value="">None</option>
                    {courses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                <label className="text-xs font-semibold text-gray-700">Class
                  <select value={form.class_id} onChange={(event) => setForm({ ...form, class_id: event.target.value })} className={fieldClass()}>
                    <option value="">None</option>
                    {classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                <label className="text-xs font-semibold text-gray-700">Division
                  <select value={form.division_id} onChange={(event) => setForm({ ...form, division_id: event.target.value })} className={fieldClass()}>
                    <option value="">None</option>
                    {divisions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
              </>
            )}
            <button type="submit" disabled={saving} className={primaryButton}>{saving ? 'Saving...' : 'Create invitation'}</button>
          </form>
        </Dialog>
      )}
      {pending && (
        <Dialog title="Revoke invitation?" onClose={() => setPending(null)}>
          <p className="text-sm text-gray-600">Revoke the invitation for {pending.email}? The link will stop working.</p>
          <button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void revoke()}>Revoke</button>
        </Dialog>
      )}
    </section>
  )
}
