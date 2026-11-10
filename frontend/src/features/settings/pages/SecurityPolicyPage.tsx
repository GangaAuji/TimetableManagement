import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { fieldClass } from '../../academics/ui'

type Policy = {
  min_length: number
  max_length: number
  require_upper: boolean
  require_lower: boolean
  require_digit: boolean
  require_symbol: boolean
  expiry_days: number
  idle_minutes: number
  max_sessions: number
  admin_ip_allowlist: string
  sign_in_notice: boolean
}

const emptyPolicy: Policy = {
  min_length: 8, max_length: 128, require_upper: false, require_lower: false, require_digit: false, require_symbol: false,
  expiry_days: 0, idle_minutes: 0, max_sessions: 0, admin_ip_allowlist: '', sign_in_notice: false,
}

const checks = [
  ['require_upper', 'Uppercase letter'],
  ['require_lower', 'Lowercase letter'],
  ['require_digit', 'Digit'],
  ['require_symbol', 'Symbol'],
] as const

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'

function readPolicy(source: Record<string, unknown> | undefined): Policy {
  const value = source || {}
  return {
    min_length: safeCount(value.min_length) || 8,
    max_length: safeCount(value.max_length) || 128,
    require_upper: value.require_upper === true,
    require_lower: value.require_lower === true,
    require_digit: value.require_digit === true,
    require_symbol: value.require_symbol === true,
    expiry_days: safeCount(value.expiry_days),
    idle_minutes: safeCount(value.idle_minutes),
    max_sessions: safeCount(value.max_sessions),
    admin_ip_allowlist: safeText(value.admin_ip_allowlist, 2000),
    sign_in_notice: value.sign_in_notice === true,
  }
}

export function SecurityPolicyPage() {
  const setPageHeader = useSetPageHeader()
  const [policy, setPolicy] = useState<Policy>(emptyPolicy)
  const [ready, setReady] = useState(true)
  const [enabled, setEnabled] = useState(false)
  const [canChange, setCanChange] = useState(false)
  const [currentIp, setCurrentIp] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  function apply(data: { settings?: Record<string, unknown>; ready?: boolean; enabled?: boolean; can_change?: boolean; current_ip?: unknown }) {
    setPolicy(readPolicy(data.settings))
    setReady(data.ready !== false)
    setEnabled(data.enabled === true)
    setCanChange(data.can_change === true)
    setCurrentIp(safeText(data.current_ip, 45))
  }

  useEffect(() => {
    setPageHeader('Security')
    void apiRequest<{ settings?: Record<string, unknown>; ready?: boolean; enabled?: boolean; can_change?: boolean; current_ip?: unknown }>('/api/security-policy')
      .then(apply)
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function update(patch: Partial<Policy>) {
    setPolicy((current) => ({ ...current, ...patch }))
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!canChange || !ready) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const data = await apiRequest<{ settings?: Record<string, unknown>; ready?: boolean; enabled?: boolean; can_change?: boolean; current_ip?: unknown }>('/api/security-policy', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(policy),
      })
      apply(data)
      setNotice('Security policy saved. It applies from the next sign-in.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const locked = !canChange || !ready

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Security policy</h2>
        <p className="text-xs text-gray-500">Password rules, session limits, the admin network list, and a notice when someone signs in.</p>
        {!ready && <p className="mt-2 text-xs text-gray-500">Apply the database upgrade before these rules can be saved.</p>}
        {ready && !enabled && <p className="mt-2 text-xs text-gray-500">Turn on Security policy under Settings → Capabilities. Saved rules apply from the next sign-in.</p>}
        {ready && enabled && <p className="mt-2 text-xs text-gray-500">These rules are on. They apply from the next sign-in.</p>}
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view this policy. Changing it needs the security policy permission.</p>}
      </section>
      <form className="min-h-0 flex-1 space-y-4 overflow-auto p-5" onSubmit={(event) => void save(event)}>
        <FailureNotice message={error} />
        <SuccessNotice message={notice} />
        <section className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs font-semibold text-gray-700">Minimum length
            <input type="number" min={8} max={64} disabled={locked} value={policy.min_length} onChange={(event) => update({ min_length: Number(event.target.value) })} className={fieldClass()} />
          </label>
          <label className="block text-xs font-semibold text-gray-700">Maximum length
            <input type="number" min={8} max={128} disabled={locked} value={policy.max_length} onChange={(event) => update({ max_length: Number(event.target.value) })} className={fieldClass()} />
          </label>
          <label className="block text-xs font-semibold text-gray-700">Password expiry, in days
            <input type="number" min={0} max={365} disabled={locked} value={policy.expiry_days} onChange={(event) => update({ expiry_days: Number(event.target.value) })} className={fieldClass()} />
            <span className="mt-1 block font-normal text-gray-500">0 keeps a password until it is changed. Existing passwords with no recorded change are not expired.</span>
          </label>
          <label className="block text-xs font-semibold text-gray-700">Idle timeout, in minutes
            <input type="number" min={0} max={720} disabled={locked} value={policy.idle_minutes} onChange={(event) => update({ idle_minutes: Number(event.target.value) })} className={fieldClass()} />
            <span className="mt-1 block font-normal text-gray-500">0 leaves the session to its 7-day expiry.</span>
          </label>
          <label className="block text-xs font-semibold text-gray-700">Concurrent sessions
            <input type="number" min={0} max={20} disabled={locked} value={policy.max_sessions} onChange={(event) => update({ max_sessions: Number(event.target.value) })} className={fieldClass()} />
            <span className="mt-1 block font-normal text-gray-500">0 does not limit how many sessions stay open. A lower number ends the oldest ones.</span>
          </label>
        </section>
        <fieldset className="space-y-2">
          <legend className="text-xs font-bold tracking-wide text-gray-500 uppercase">Complexity</legend>
          {checks.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" disabled={locked} checked={policy[key]} onChange={(event) => update({ [key]: event.target.checked })} />
              {label}
            </label>
          ))}
        </fieldset>
        <label className="block text-xs font-semibold text-gray-700">Admin network list
          <textarea rows={4} disabled={locked} value={policy.admin_ip_allowlist} maxLength={2000} onChange={(event) => update({ admin_ip_allowlist: event.target.value })} className={fieldClass()} placeholder="One address or network per line. Leave empty to allow every network." />
          <span className="mt-1 block font-normal text-gray-500">Applies to Super Admin, Admin and HOD. Your current address is {currentIp || 'unknown'}. A list that excludes it cannot be saved.</span>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" disabled={locked} checked={policy.sign_in_notice} onChange={(event) => update({ sign_in_notice: event.target.checked })} />
          Email a notice when someone signs in
        </label>
        {canChange && ready && <button type="submit" disabled={saving} className={primaryButton}>{saving ? 'Saving...' : 'Save policy'}</button>}
      </form>
    </section>
  )
}
