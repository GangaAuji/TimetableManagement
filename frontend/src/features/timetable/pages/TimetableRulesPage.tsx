import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom, useCapability } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type ParamSpec = { kind: 'int' | 'time'; default: number | string }
type RuleSpec = {
  name: string
  title: string
  description: string
  scope: string
  defaultWeight: number
  params: Record<string, ParamSpec>
}
type RuleValues = Record<string, number | string>
type Rules = Record<string, RuleValues>
type Payload = {
  institution_id?: number
  rules?: Record<string, unknown>
  stored?: boolean
  defaults?: Record<string, unknown>
  registry?: Record<string, unknown>[]
  max_weight?: number
  can_change?: boolean
}

const ruleName = /^[a-z][a-z0-9_]{0,59}$/
const timeText = /^(?:[01]\d|2[0-3]):[0-5]\d$/
const scopeLabel: Record<string, string> = { faculty: 'Teachers', cohort: 'Students', both: 'Teachers and students' }
const paramLabel: Record<string, string> = { hours: 'Hours', start: 'From', end: 'To' }
const secondaryButton = 'rounded-xl border px-3 py-1.5 text-xs font-bold disabled:opacity-50'

function readRegistry(rows: Record<string, unknown>[] | undefined): RuleSpec[] {
  return (rows || []).slice(0, 40).map((row) => {
    const params: Record<string, ParamSpec> = {}
    const raw = row.params && typeof row.params === 'object' ? (row.params as Record<string, Record<string, unknown>>) : {}
    for (const [key, spec] of Object.entries(raw).slice(0, 8)) {
      if (!ruleName.test(key) || !spec || typeof spec !== 'object') continue
      const kind = spec.kind === 'time' ? 'time' : 'int'
      params[key] = { kind, default: kind === 'int' ? safeCount(spec.default) : safeText(spec.default, 5) }
    }
    return {
      name: safeText(row.name, 60),
      title: safeText(row.title, 80),
      description: safeText(row.description, 240),
      scope: safeText(row.scope, 20),
      defaultWeight: safeCount(row.default_weight),
      params,
    }
  }).filter((rule) => ruleName.test(rule.name))
}

function readRules(registry: RuleSpec[], raw: Record<string, unknown> | undefined): Rules {
  const rules: Rules = {}
  for (const spec of registry) {
    const given = raw && raw[spec.name] && typeof raw[spec.name] === 'object' ? (raw[spec.name] as Record<string, unknown>) : {}
    const values: RuleValues = { weight: safeCount(given.weight) }
    for (const [key, param] of Object.entries(spec.params)) {
      values[key] = param.kind === 'int' ? safeCount(given[key] ?? param.default) : safeText(given[key] ?? param.default, 5)
    }
    rules[spec.name] = values
  }
  return rules
}

function sameRules(left: Rules, right: Rules) {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function TimetableRulesPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('timetable_preferences')
  const [registry, setRegistry] = useState<RuleSpec[]>([])
  const [saved, setSaved] = useState<Rules>({})
  const [defaults, setDefaults] = useState<Rules>({})
  const [draft, setDraft] = useState<Rules>({})
  const [stored, setStored] = useState(false)
  const [maxWeight, setMaxWeight] = useState(20)
  const [canChange, setCanChange] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function apply(data: Payload) {
    const specs = readRegistry(data.registry)
    const rules = readRules(specs, data.rules)
    setRegistry(specs)
    setSaved(rules)
    setDraft(rules)
    setDefaults(readRules(specs, data.defaults))
    setStored(data.stored === true)
    setMaxWeight(Math.max(1, safeCount(data.max_weight) || 20))
    setCanChange(data.can_change === true)
  }

  useEffect(() => {
    setPageHeader('Timetable rules')
    if (!enabled) {
      setLoading(false)
      return
    }
    void apiRequest<Payload>('/api/timetable/rules')
      .then(apply)
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [enabled, setPageHeader])

  function update(name: string, key: string, value: number | string) {
    setDraft((current) => ({ ...current, [name]: { ...current[name], [key]: value } }))
  }

  function invalid(): string {
    for (const spec of registry) {
      const values = draft[spec.name] || {}
      const weight = Number(values.weight)
      if (!Number.isInteger(weight) || weight < 0 || weight > maxWeight) return `${spec.title}: weight must be 0 to ${maxWeight}.`
      for (const [key, param] of Object.entries(spec.params)) {
        const raw = values[key]
        if (param.kind === 'int') {
          const number = Number(raw)
          if (!Number.isInteger(number) || number < 1 || number > 12) return `${spec.title}: ${paramLabel[key] || key} must be 1 to 12.`
        } else if (raw !== '' && !timeText.test(String(raw))) {
          return `${spec.title}: ${paramLabel[key] || key} must be HH:MM or empty.`
        }
      }
    }
    return ''
  }

  async function save() {
    if (!canChange) return
    const problem = invalid()
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const data = await apiRequest<Payload>('/api/timetable/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ rules: draft }),
      })
      apply(data)
      setNotice('Rules saved. The next generation run uses them.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  const dirty = !sameRules(draft, saved)
  const atDefaults = sameRules(draft, defaults)

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow-sm">
        Timetable rules are part of the <strong>Timetable preferences</strong> capability, which is switched off for this institution. Turn it on under Settings → Capabilities.
      </section>
    )
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-800">Timetable rules</h2>
            <p className="text-xs text-gray-500">
              Each rule is a cost per violation, 0 to {maxWeight}. Zero switches a rule off. The generator keeps every hard constraint
              (no double booking, availability, room capacity) and then finds the timetable with the lowest total cost.
            </p>
            {!stored && !loading && <p className="mt-1 text-xs text-gray-500">Nothing saved yet: these are the defaults.</p>}
            {!canChange && !loading && <p className="mt-1 text-xs text-gray-500">You can view the rules. Changing them needs the timetable generation permission.</p>}
          </div>
          {canChange && (
            <div className="flex gap-2">
              <button type="button" className={`${secondaryButton} border-gray-300 text-gray-700`} disabled={busy || atDefaults} onClick={() => setDraft(defaults)}>
                Reset to defaults
              </button>
              <button type="button" className={`${secondaryButton} border-gray-300 text-gray-700`} disabled={busy || !dirty} onClick={() => setDraft(saved)}>
                Discard
              </button>
              <button type="button" className="rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-bold text-white disabled:opacity-50" disabled={busy || !dirty} onClick={() => void save()}>
                {busy ? 'Saving…' : 'Save rules'}
              </button>
            </div>
          )}
        </div>
        {error && <div className="mt-3"><FailureNotice message={error} /></div>}
        {notice && <div className="mt-3"><SuccessNotice message={notice} /></div>}
      </section>
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {loading && <p className="p-6 text-center text-sm text-gray-500">Loading rules…</p>}
        {!loading && (
          <ul className="divide-y divide-gray-100 rounded-2xl border border-gray-200 bg-white">
            {registry.map((spec) => {
              const values = draft[spec.name] || {}
              const weight = Number(values.weight) || 0
              const changed = JSON.stringify(values) !== JSON.stringify(saved[spec.name] || {})
              return (
                <li key={spec.name} className={`flex flex-wrap items-start gap-4 px-5 py-4 ${weight === 0 ? 'opacity-70' : ''}`}>
                  <div className="min-w-[16rem] flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-gray-900">{spec.title}</span>
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold tracking-wide text-gray-500 uppercase">{scopeLabel[spec.scope] || spec.scope}</span>
                      {changed && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold tracking-wide text-amber-700 uppercase">Unsaved</span>}
                    </div>
                    <p className="mt-1 text-xs text-gray-500">{spec.description}</p>
                    <p className="mt-1 text-[11px] text-gray-400">Default weight {spec.defaultWeight}.</p>
                  </div>
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="flex flex-col text-xs text-gray-600">
                      <span className="mb-1 font-semibold">Weight</span>
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min={0}
                          max={maxWeight}
                          value={weight}
                          disabled={!canChange || busy}
                          aria-label={`${spec.title} weight`}
                          onChange={(event) => update(spec.name, 'weight', Number(event.target.value))}
                          className="w-32"
                        />
                        <input
                          type="number"
                          min={0}
                          max={maxWeight}
                          value={weight}
                          disabled={!canChange || busy}
                          aria-label={`${spec.title} weight value`}
                          onChange={(event) => update(spec.name, 'weight', Number(event.target.value))}
                          className="w-16 rounded border border-gray-300 px-2 py-1 text-xs"
                        />
                      </div>
                    </label>
                    {Object.entries(spec.params).map(([key, param]) => (
                      <label key={key} className="flex flex-col text-xs text-gray-600">
                        <span className="mb-1 font-semibold">{paramLabel[key] || key}</span>
                        {param.kind === 'int' ? (
                          <input
                            type="number"
                            min={1}
                            max={12}
                            value={Number(values[key]) || 0}
                            disabled={!canChange || busy}
                            aria-label={`${spec.title} ${paramLabel[key] || key}`}
                            onChange={(event) => update(spec.name, key, Number(event.target.value))}
                            className="w-16 rounded border border-gray-300 px-2 py-1 text-xs"
                          />
                        ) : (
                          <input
                            type="time"
                            value={String(values[key] ?? '')}
                            disabled={!canChange || busy}
                            aria-label={`${spec.title} ${paramLabel[key] || key}`}
                            onChange={(event) => update(spec.name, key, event.target.value)}
                            className="rounded border border-gray-300 px-2 py-1 text-xs"
                          />
                        )}
                      </label>
                    ))}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
