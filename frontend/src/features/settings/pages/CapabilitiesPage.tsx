import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeText } from '../../../shared/security/sanitize'

type SettingKind = { kind: string; default: unknown }
type Capability = {
  name: string
  title: string
  description: string
  phase: string
  flag: boolean
  enabled: boolean
  stored: boolean
  default: boolean
  effective: boolean
  settings: Record<string, unknown>
  schema: Record<string, SettingKind>
}
type Payload = { table_exists?: boolean; capabilities?: Record<string, unknown>[]; can_change?: boolean }

const capabilityName = /^[a-z][a-z0-9_]{0,59}$/
const phaseLabel: Record<string, string> = {
  J: 'Timetable engine', K: 'Academic completeness', L: 'Compliance and operations', I: 'Communication',
}
const secondaryButton = 'rounded-xl border px-3 py-1.5 text-xs font-bold disabled:opacity-50'

function readCapabilities(rows: Record<string, unknown>[] | undefined): Capability[] {
  return (rows || []).map((row) => {
    const schema: Record<string, SettingKind> = {}
    const rawSchema = row.schema && typeof row.schema === 'object' ? (row.schema as Record<string, Record<string, unknown>>) : {}
    for (const [key, spec] of Object.entries(rawSchema).slice(0, 20)) {
      if (capabilityName.test(key) && spec && typeof spec === 'object') {
        schema[key] = { kind: safeText(spec.kind, 60), default: spec.default }
      }
    }
    const settings: Record<string, unknown> = {}
    const rawSettings = row.settings && typeof row.settings === 'object' ? (row.settings as Record<string, unknown>) : {}
    for (const key of Object.keys(schema)) settings[key] = rawSettings[key] ?? schema[key].default
    return {
      name: safeText(row.name, 60),
      title: safeText(row.title, 80),
      description: safeText(row.description, 240),
      phase: safeText(row.phase, 4),
      flag: row.flag === true,
      enabled: row.enabled === true,
      stored: row.stored === true,
      default: row.default === true,
      effective: row.effective === true,
      settings,
      schema,
    }
  }).filter((item) => capabilityName.test(item.name))
}

function settingValue(kind: string, raw: string | boolean): unknown {
  if (kind === 'bool') return raw === true
  if (kind === 'int') return Number(raw)
  return String(raw)
}

export function CapabilitiesPage() {
  const setPageHeader = useSetPageHeader()
  const [items, setItems] = useState<Capability[]>([])
  const [tableExists, setTableExists] = useState(true)
  const [canChange, setCanChange] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [drafts, setDrafts] = useState<Record<string, Record<string, unknown>>>({})

  function apply(data: Payload) {
    setItems(readCapabilities(data.capabilities))
    setTableExists(data.table_exists !== false)
    setCanChange(data.can_change === true)
    setDrafts({})
  }

  useEffect(() => {
    setPageHeader('Capabilities')
    void apiRequest<Payload>('/api/capabilities').then(apply).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  async function save(name: string, body: Record<string, unknown>, done: string) {
    if (!canChange) return
    setBusy(name)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const data = await apiRequest<Payload>(`/api/capabilities/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(body),
      })
      apply(data)
      setNotice(`${done} Menu entries follow on the next page reload.`)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy('')
    }
  }

  const groups = Object.keys(phaseLabel).map((prefix) => ({
    prefix,
    label: phaseLabel[prefix],
    items: items.filter((item) => item.phase.startsWith(prefix)),
  })).filter((group) => group.items.length > 0)

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Capabilities</h2>
        <p className="text-xs text-gray-500">
          Optional features for this institution. Everything here is off until switched on, and the core (sign-in, attendance, timetable, reports) works without any of them.
        </p>
        {!tableExists && <p className="mt-2 text-xs font-semibold text-amber-700">The capabilities table is missing. Apply the database migrations before switching features on.</p>}
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view these switches. Changing them needs the settings permission.</p>}
      </section>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-2">
        {groups.map((group) => (
          <section key={group.prefix} className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">{group.label}</h3>
            <ul className="divide-y divide-gray-100">
              {group.items.map((item) => {
                const draft = drafts[item.name] || item.settings
                const dirty = JSON.stringify(draft) !== JSON.stringify(item.settings)
                const toggleDisabled = !canChange || !tableExists || !item.flag || busy === item.name
                return (
                  <li key={item.name} className="flex flex-col gap-2 py-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-gray-800">{item.title}</span>
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold text-gray-500 uppercase">{item.phase}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${item.effective ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-50 text-gray-400'}`}>
                          {item.effective ? 'On' : 'Off'}
                        </span>
                        {!item.flag && <span className="text-[10px] font-semibold text-amber-700">Disabled on this server (FEATURE_{item.name.toUpperCase()})</span>}
                        {!item.stored && item.default && item.flag && tableExists && <span className="text-[10px] font-medium text-gray-400">On by default</span>}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">{item.description}</p>
                      {Object.keys(item.schema).length > 0 && (
                        <div className="mt-2 flex flex-wrap items-end gap-3">
                          {Object.entries(item.schema).map(([key, spec]) => {
                            const value = draft[key]
                            const label = key.replace(/_/g, ' ')
                            const update = (next: unknown) => setDrafts({ ...drafts, [item.name]: { ...draft, [key]: next } })
                            if (spec.kind === 'bool') {
                              return (
                                <label key={key} className="flex items-center gap-2 text-xs font-semibold text-gray-700">
                                  <input type="checkbox" checked={value === true} disabled={!canChange || !tableExists} onChange={(event) => update(settingValue('bool', event.target.checked))} />
                                  {label}
                                </label>
                              )
                            }
                            if (spec.kind.startsWith('choice:')) {
                              const choiceText: Record<string, string> = {
                                optional: 'Only people who enrolled',
                                staff: 'Required for Super Admin, Admin and HOD',
                                everyone: 'Required for every role',
                                soft: 'Soft',
                                hard: 'Hard',
                              }
                              return (
                                <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                                  <select value={String(value ?? '')} disabled={!canChange || !tableExists} onChange={(event) => update(event.target.value)} className="mt-1 block rounded-lg border border-gray-200 px-2 py-1 text-xs">
                                    {spec.kind.slice(7).split('|').map((choice) => <option key={choice} value={choice}>{choiceText[choice] || choice}</option>)}
                                  </select>
                                </label>
                              )
                            }
                            return (
                              <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                                <input
                                  type={spec.kind === 'int' ? 'number' : 'text'}
                                  min={0}
                                  value={String(value ?? '')}
                                  disabled={!canChange || !tableExists}
                                  onChange={(event) => update(settingValue(spec.kind, event.target.value))}
                                  className="mt-1 block w-28 rounded-lg border border-gray-200 px-2 py-1 text-xs"
                                />
                              </label>
                            )
                          })}
                          {dirty && canChange && (
                            <button type="button" className={secondaryButton} disabled={busy === item.name} onClick={() => void save(item.name, { settings: draft }, `${item.title}: settings saved.`)}>
                              Save settings
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    {canChange && (
                      <button
                        type="button"
                        className={`${secondaryButton} shrink-0 ${item.enabled ? 'border-gray-300 text-gray-700' : 'border-gray-900 bg-gray-900 text-white'}`}
                        disabled={toggleDisabled}
                        onClick={() => void save(item.name, { enabled: !item.enabled }, `${item.title} turned ${item.enabled ? 'off' : 'on'}.`)}
                      >
                        {busy === item.name ? 'Saving...' : item.enabled ? 'Turn off' : 'Turn on'}
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
        {items.length === 0 && !error && <p className="p-6 text-center text-xs text-gray-400">Loading...</p>}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-gray-200 bg-white px-4 py-2">
        <FailureNotice message={error} />
        <SuccessNotice message={notice} />
      </div>
    </section>
  )
}
