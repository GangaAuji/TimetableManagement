import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { sendJson } from '../../academics/api'
import { fieldClass } from '../../academics/ui'

type Organization = { id: number; name: string; short_name: string }
type Institution = {
  id: number
  name: string
  code: string
  short_name: string
  is_active: boolean
  sort_order: number
  departments: number
  rooms: number
  members: number
}
type Payload = {
  organization?: Record<string, unknown> | null
  institutions?: Record<string, unknown>[]
  permissions?: { change?: unknown }
}
type Form = { id: number | null; name: string; code: string; short_name: string; is_active: boolean; sort_order: string }

const emptyForm: Form = { id: null, name: '', code: '', short_name: '', is_active: true, sort_order: '0' }
const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const secondaryButton = 'rounded-xl border px-3 py-2 text-xs font-bold disabled:opacity-50'

function readOrganization(source: Record<string, unknown> | null | undefined): Organization {
  const value = source || {}
  return { id: safeCount(value.id), name: safeText(value.name, 150), short_name: safeText(value.short_name, 40) }
}

function readInstitutions(rows: Record<string, unknown>[] | undefined): Institution[] {
  return (rows || [])
    .map((row) => ({
      id: safeCount(row.id),
      name: safeText(row.name, 150),
      code: safeText(row.code, 20),
      short_name: safeText(row.short_name, 40),
      is_active: row.is_active === true,
      sort_order: safeCount(row.sort_order),
      departments: safeCount(row.departments),
      rooms: safeCount(row.rooms),
      members: safeCount(row.members),
    }))
    .filter((row) => row.id > 0)
}

/**
 * The organization (one row) and the institutions inside it. A tenant with
 * one institution is the default; adding a second one turns on the
 * institution switcher and the scoping of departments, rooms, faculty,
 * courses and students (see docs/DESIGN_INSTITUTIONS.md).
 */
export function InstitutionsPage() {
  const setPageHeader = useSetPageHeader()
  const [organization, setOrganization] = useState<Organization>({ id: 0, name: '', short_name: '' })
  const [institutions, setInstitutions] = useState<Institution[]>([])
  const [canChange, setCanChange] = useState(false)
  const [form, setForm] = useState<Form>(emptyForm)
  const [orgForm, setOrgForm] = useState({ name: '', short_name: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  function apply(data: Payload) {
    const org = readOrganization(data.organization)
    setOrganization(org)
    setOrgForm({ name: org.name, short_name: org.short_name })
    setInstitutions(readInstitutions(data.institutions))
    setCanChange(data.permissions?.change === true)
  }

  async function load() {
    try {
      apply(await apiRequest<Payload>('/api/institutions'))
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  useEffect(() => {
    setPageHeader('Institutions')
    void load()
  }, [setPageHeader])

  async function saveOrganization(event: FormEvent) {
    event.preventDefault()
    if (!canChange) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await sendJson('PUT', '/api/institutions/organization', { name: orgForm.name.trim(), short_name: orgForm.short_name.trim() })
      setNotice('Organization saved.')
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  async function saveInstitution(event: FormEvent) {
    event.preventDefault()
    if (!canChange) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const body = {
        name: form.name.trim(),
        code: form.code.trim().toUpperCase(),
        short_name: form.short_name.trim(),
        is_active: form.is_active,
        sort_order: Number(form.sort_order) || 0,
      }
      if (form.id) {
        await sendJson('PUT', `/api/institutions/${form.id}`, body)
        setNotice('Institution saved.')
      } else {
        await sendJson('POST', '/api/institutions', body)
        setNotice('Institution added. Members and the switcher appear after the next sign-in or page reload.')
      }
      setForm(emptyForm)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  function edit(item: Institution) {
    setForm({ id: item.id, name: item.name, code: item.code, short_name: item.short_name, is_active: item.is_active, sort_order: String(item.sort_order) })
  }

  const single = institutions.length <= 1

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Institutions</h2>
        <p className="text-xs text-gray-500">
          The colleges, schools or campuses that make up {organization.name || 'this organization'}. Each department and room
          belongs to one institution; rooms and faculty can be shared with the others from their own forms.
        </p>
        {single && (
          <p className="mt-1 text-[11px] font-medium text-gray-500">
            With one institution nothing changes: every list shows everything. Add a second institution to turn on scoping and the switcher.
          </p>
        )}
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view these settings. Changing them needs the settings permission.</p>}
      </section>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-2">
        {error && <FailureNotice message={error} />}
        {notice && <SuccessNotice message={notice} />}

        <form className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm" onSubmit={(event) => void saveOrganization(event)}>
          <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Organization</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-semibold text-gray-700">
              Name
              <input className={fieldClass()} value={orgForm.name} maxLength={150} required disabled={!canChange} onChange={(event) => setOrgForm({ ...orgForm, name: event.target.value })} />
            </label>
            <label className="text-xs font-semibold text-gray-700">
              Short name
              <input className={fieldClass()} value={orgForm.short_name} maxLength={40} disabled={!canChange} onChange={(event) => setOrgForm({ ...orgForm, short_name: event.target.value })} />
            </label>
          </div>
          {canChange && (
            <div className="mt-3 flex justify-end">
              <button type="submit" className={primaryButton} disabled={busy}>Save organization</button>
            </div>
          )}
        </form>

        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Institutions</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-gray-500">
                <tr>
                  <th className="px-2 py-1">Order</th>
                  <th className="px-2 py-1">Code</th>
                  <th className="px-2 py-1">Name</th>
                  <th className="px-2 py-1">Short name</th>
                  <th className="px-2 py-1">Departments</th>
                  <th className="px-2 py-1">Rooms</th>
                  <th className="px-2 py-1">Members</th>
                  <th className="px-2 py-1">Status</th>
                  {canChange && <th className="px-2 py-1" />}
                </tr>
              </thead>
              <tbody>
                {institutions.map((item) => (
                  <tr key={item.id} className="border-t border-gray-100">
                    <td className="px-2 py-1 text-gray-500">{item.sort_order}</td>
                    <td className="px-2 py-1 font-mono">{item.code}</td>
                    <td className="px-2 py-1 font-semibold text-gray-800">{item.name}</td>
                    <td className="px-2 py-1">{item.short_name}</td>
                    <td className="px-2 py-1">{item.departments}</td>
                    <td className="px-2 py-1">{item.rooms}</td>
                    <td className="px-2 py-1">{item.members}</td>
                    <td className="px-2 py-1">{item.is_active ? 'Active' : 'Inactive'}</td>
                    {canChange && (
                      <td className="px-2 py-1 text-right">
                        <button type="button" className={secondaryButton} onClick={() => edit(item)}>Edit</button>
                      </td>
                    )}
                  </tr>
                ))}
                {institutions.length === 0 && (
                  <tr><td className="px-2 py-3 text-gray-500" colSpan={9}>No institutions yet. Run the database upgrade to create the first one.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {canChange && (
          <form className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm" onSubmit={(event) => void saveInstitution(event)}>
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">{form.id ? 'Edit institution' : 'Add institution'}</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-xs font-semibold text-gray-700 sm:col-span-2">
                Name
                <input className={fieldClass()} value={form.name} maxLength={150} required onChange={(event) => setForm({ ...form, name: event.target.value })} />
              </label>
              <label className="text-xs font-semibold text-gray-700">
                Code
                <input className={fieldClass()} value={form.code} maxLength={20} required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,19}" title="Letters, digits, hyphens or underscores" onChange={(event) => setForm({ ...form, code: event.target.value })} />
              </label>
              <label className="text-xs font-semibold text-gray-700">
                Short name
                <input className={fieldClass()} value={form.short_name} maxLength={40} onChange={(event) => setForm({ ...form, short_name: event.target.value })} />
              </label>
              <label className="text-xs font-semibold text-gray-700">
                Sort order
                <input className={fieldClass()} type="number" min={0} max={10000} value={form.sort_order} onChange={(event) => setForm({ ...form, sort_order: event.target.value })} />
              </label>
              <label className="flex items-end gap-2 pb-2 text-xs font-semibold text-gray-700">
                <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
                Active
              </label>
            </div>
            <p className="mt-2 text-[11px] text-gray-500">Institutions are deactivated rather than deleted so their departments and rooms keep their history.</p>
            <div className="mt-3 flex justify-end gap-2">
              {form.id && <button type="button" className={secondaryButton} onClick={() => setForm(emptyForm)} disabled={busy}>Cancel</button>}
              <button type="submit" className={primaryButton} disabled={busy}>{form.id ? 'Save' : 'Add'}</button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}
