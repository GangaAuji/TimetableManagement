import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice, WarningNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { sendJson } from '../../academics/api'
import { fieldClass } from '../../academics/ui'

type Named = { name: string; description: string }
type ApiKey = { id: number; name: string; prefix: string; scopes: string[]; created_at: string; expires_at: string; last_used_at: string; revoked_at: string }
type Webhook = { id: number; name: string; url: string; events: string[]; is_active: boolean; created_at: string; last_delivery_at: string; last_status: string }
type Delivery = { id: number; endpoint_id: number; endpoint_name: string; event: string; status: string; attempts: number; response_status: number | null; last_error: string; created_at: string; sent_at: string }
type Identity = { id: number; user_id: number; username: string; role: string; issuer: string; email: string; created_at: string; last_login_at: string }
type Provider = { name: string; label: string; issuer: string }
type Sso = {
  enabled: boolean
  provider: string
  issuer: string
  client_id: string
  allowed_domains: string
  link_by_email: boolean
  button_label: string
  has_client_secret: boolean
  updated_at: string
}
type Payload = {
  api_keys?: Record<string, unknown>[]
  scopes?: Record<string, unknown>[]
  webhooks?: Record<string, unknown>[]
  events?: Record<string, unknown>[]
  webhook_status?: { ready?: unknown; queue?: Record<string, unknown> }
  sso?: Record<string, unknown>
  sso_identities?: Record<string, unknown>[]
  sso_redirect_uri?: unknown
  providers?: Record<string, unknown>[]
  openapi_url?: unknown
  can_change?: unknown
  key?: unknown
  secret?: unknown
}

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const secondaryButton = 'rounded-xl border px-3 py-2 text-xs font-bold disabled:opacity-50'
const dangerButton = 'rounded-xl border border-red-200 px-3 py-2 text-xs font-bold text-red-700 disabled:opacity-50'
const emptySso: Sso = { enabled: false, provider: 'oidc', issuer: '', client_id: '', allowed_domains: '', link_by_email: true, button_label: '', has_client_secret: false, updated_at: '' }

function strings(value: unknown, limit: number): string[] {
  return Array.isArray(value) ? value.map((item) => safeText(item, limit)).filter(Boolean) : []
}

function readNamed(rows: Record<string, unknown>[] | undefined): Named[] {
  return (rows || []).map((row) => ({ name: safeText(row.name, 40), description: safeText(row.description, 200) })).filter((row) => row.name)
}

function readKeys(rows: Record<string, unknown>[] | undefined): ApiKey[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id), name: safeText(row.name, 100), prefix: safeText(row.prefix, 12), scopes: strings(row.scopes, 40),
    created_at: safeText(row.created_at, 19), expires_at: safeText(row.expires_at, 19), last_used_at: safeText(row.last_used_at, 19),
    revoked_at: safeText(row.revoked_at, 19),
  })).filter((row) => row.id > 0)
}

function readWebhooks(rows: Record<string, unknown>[] | undefined): Webhook[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id), name: safeText(row.name, 100), url: safeText(row.url, 500), events: strings(row.events, 60), is_active: row.is_active === true,
    created_at: safeText(row.created_at, 19), last_delivery_at: safeText(row.last_delivery_at, 19), last_status: safeText(row.last_status, 20),
  })).filter((row) => row.id > 0)
}

function readDeliveries(rows: Record<string, unknown>[] | undefined): Delivery[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id), endpoint_id: safeCount(row.endpoint_id), endpoint_name: safeText(row.endpoint_name, 100), event: safeText(row.event, 60),
    status: safeText(row.status, 20), attempts: safeCount(row.attempts), response_status: row.response_status == null ? null : safeCount(row.response_status),
    last_error: safeText(row.last_error, 200), created_at: safeText(row.created_at, 19), sent_at: safeText(row.sent_at, 19),
  })).filter((row) => row.id > 0)
}

function readIdentities(rows: Record<string, unknown>[] | undefined): Identity[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id), user_id: safeCount(row.user_id), username: safeText(row.username, 50), role: safeText(row.role, 50),
    issuer: safeText(row.issuer, 255), email: safeText(row.email, 190), created_at: safeText(row.created_at, 19), last_login_at: safeText(row.last_login_at, 19),
  })).filter((row) => row.id > 0)
}

function readProviders(rows: Record<string, unknown>[] | undefined): Provider[] {
  return (rows || []).map((row) => ({ name: safeText(row.name, 20), label: safeText(row.label, 40), issuer: safeText(row.issuer, 255) })).filter((row) => row.name)
}

function readSso(source: Record<string, unknown> | undefined): Sso {
  const value = source || {}
  return {
    enabled: value.enabled === true, provider: safeText(value.provider, 20) || 'oidc', issuer: safeText(value.issuer, 255), client_id: safeText(value.client_id, 255),
    allowed_domains: safeText(value.allowed_domains, 500), link_by_email: value.link_by_email !== false, button_label: safeText(value.button_label, 60),
    has_client_secret: value.has_client_secret === true, updated_at: safeText(value.updated_at, 19),
  }
}

function Secret({ label, value, onDone }: { label: string; value: string; onDone: () => void }) {
  return <WarningNotice message={`${label}. Copy it now. It is shown once and cannot be recovered later.`} detail={value} hold onDone={onDone} />
}

export function IntegrationsPage() {
  const setPageHeader = useSetPageHeader()
  const [canChange, setCanChange] = useState(false)
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [scopes, setScopes] = useState<Named[]>([])
  const [hooks, setHooks] = useState<Webhook[]>([])
  const [events, setEvents] = useState<Named[]>([])
  const [queue, setQueue] = useState<Record<string, number>>({})
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [sso, setSso] = useState<Sso>(emptySso)
  const [identities, setIdentities] = useState<Identity[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [redirectUri, setRedirectUri] = useState('')
  const [openapiUrl, setOpenapiUrl] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<{ label: string; value: string } | null>(null)

  const [keyForm, setKeyForm] = useState({ name: '', scopes: [] as string[], expires_at: '' })
  const [hookForm, setHookForm] = useState<{ id: number | null; name: string; url: string; events: string[]; is_active: boolean }>({ id: null, name: '', url: '', events: [], is_active: true })
  const [clientSecret, setClientSecret] = useState('')
  const [clearSecret, setClearSecret] = useState(false)

  function apply(data: Payload) {
    setCanChange(data.can_change === true)
    setKeys(readKeys(data.api_keys))
    setScopes(readNamed(data.scopes))
    setHooks(readWebhooks(data.webhooks))
    setEvents(readNamed(data.events))
    const counts = data.webhook_status?.queue || {}
    setQueue(Object.fromEntries(Object.entries(counts).map(([status, n]) => [safeText(status, 20), safeCount(n)])))
    setSso(readSso(data.sso))
    setIdentities(readIdentities(data.sso_identities))
    setProviders(readProviders(data.providers))
    setRedirectUri(safeText(data.sso_redirect_uri, 500))
    setOpenapiUrl(safeText(data.openapi_url, 500))
    setClientSecret('')
    setClearSecret(false)
  }

  async function loadDeliveries() {
    try {
      const data = await apiRequest<{ deliveries?: Record<string, unknown>[] }>('/api/integrations/webhooks/deliveries')
      setDeliveries(readDeliveries(data.deliveries))
    } catch {
      /* the rest of the page still works */
    }
  }

  useEffect(() => {
    setPageHeader('Integrations')
    void apiRequest<Payload>('/api/integrations')
      .then((data) => { apply(data); void loadDeliveries() })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  async function run(work: () => Promise<Payload | void>, done: string) {
    if (!canChange) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const data = await work()
      if (data) apply(data)
      setNotice(done)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  function createKey(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const data = await sendJson<Payload>('POST', '/api/integrations/api-keys', { name: keyForm.name.trim(), scopes: keyForm.scopes, expires_at: keyForm.expires_at || null })
      setRevealed({ label: `API key "${safeText(keyForm.name, 100)}"`, value: safeText(data.key, 80) })
      setKeyForm({ name: '', scopes: [], expires_at: '' })
      return data
    }, 'API key created.')
  }

  function revokeKey(key: ApiKey) {
    if (!window.confirm(`Revoke "${key.name}"? Clients using it stop working immediately.`)) return
    void run(() => sendJson<Payload>('DELETE', `/api/integrations/api-keys/${key.id}`), 'API key revoked.')
  }

  function saveHook(event: FormEvent) {
    event.preventDefault()
    const body = { name: hookForm.name.trim(), url: hookForm.url.trim(), events: hookForm.events }
    void run(async () => {
      if (hookForm.id === null) {
        const data = await sendJson<Payload>('POST', '/api/integrations/webhooks', body)
        setRevealed({ label: `Signing secret for "${safeText(hookForm.name, 100)}"`, value: safeText(data.secret, 120) })
        setHookForm({ id: null, name: '', url: '', events: [], is_active: true })
        return data
      }
      const data = await sendJson<Payload>('PUT', `/api/integrations/webhooks/${hookForm.id}`, { ...body, is_active: hookForm.is_active, rotate_secret: false })
      setHookForm({ id: null, name: '', url: '', events: [], is_active: true })
      return data
    }, hookForm.id === null ? 'Webhook endpoint created.' : 'Webhook endpoint saved.')
  }

  function rotateSecret(hook: Webhook) {
    if (!window.confirm(`Rotate the signing secret of "${hook.name}"? The receiver must switch to the new one.`)) return
    void run(async () => {
      const data = await sendJson<Payload>('PUT', `/api/integrations/webhooks/${hook.id}`, { name: hook.name, url: hook.url, events: hook.events, is_active: hook.is_active, rotate_secret: true })
      setRevealed({ label: `New signing secret for "${hook.name}"`, value: safeText(data.secret, 120) })
      return data
    }, 'Signing secret rotated.')
  }

  function toggleHook(hook: Webhook) {
    void run(() => sendJson<Payload>('PUT', `/api/integrations/webhooks/${hook.id}`, { name: hook.name, url: hook.url, events: hook.events, is_active: !hook.is_active, rotate_secret: false }), hook.is_active ? 'Endpoint paused.' : 'Endpoint resumed.')
  }

  function deleteHook(hook: Webhook) {
    if (!window.confirm(`Delete "${hook.name}" and its delivery history?`)) return
    void run(() => sendJson<Payload>('DELETE', `/api/integrations/webhooks/${hook.id}`), 'Webhook endpoint deleted.')
  }

  function retry(delivery: Delivery) {
    void run(async () => { await sendJson('POST', `/api/integrations/webhooks/deliveries/${delivery.id}/retry`); await loadDeliveries() }, 'Delivery queued again.')
  }

  function saveSso(event: FormEvent) {
    event.preventDefault()
    const payload: Record<string, unknown> = {
      enabled: sso.enabled, provider: sso.provider, issuer: sso.issuer, client_id: sso.client_id, allowed_domains: sso.allowed_domains,
      link_by_email: sso.link_by_email, button_label: sso.button_label,
    }
    if (clientSecret) payload.client_secret = clientSecret
    if (clearSecret) payload.clear_secret = true
    void run(() => sendJson<Payload>('PUT', '/api/integrations/sso', payload), 'SSO settings saved.')
  }

  function unlink(identity: Identity) {
    if (!window.confirm(`Unlink ${identity.email || identity.username} from ${identity.username}? They will be linked again by email on their next sign-in if that is allowed.`)) return
    void run(() => sendJson<Payload>('DELETE', `/api/integrations/sso/identities/${identity.id}`), 'SSO link removed.')
  }

  function toggle(list: string[], name: string) {
    return list.includes(name) ? list.filter((item) => item !== name) : [...list, name]
  }

  const chosenProvider = providers.find((provider) => provider.name === sso.provider)
  const statusClass = (status: string) => (status === 'sent' ? 'font-semibold text-emerald-700' : status === 'failed' ? 'font-semibold text-red-600' : 'text-gray-600')

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Integrations</h2>
        <p className="text-xs text-gray-500">
          Read-only API keys for other systems, webhooks that tell them when attendance is marked or a timetable changes, and staff sign-in through your identity provider.
          {openapiUrl && <> The API is described at <a href={openapiUrl} target="_blank" rel="noreferrer" className="font-semibold text-blue-700 underline">openapi.json</a>.</>}
        </p>
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view these settings. Changing them needs the settings permission.</p>}
      </section>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-2">
        {revealed && <Secret label={revealed.label} value={revealed.value} onDone={() => setRevealed(null)} />}

        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-xs font-bold tracking-wide text-gray-500 uppercase">API keys</h3>
          <p className="mb-3 text-[11px] text-gray-500">Send a key as <code className="font-mono">Authorization: Bearer ttk_…</code> to <code className="font-mono">/api/v1</code>. A key only reads what its scopes allow.</p>
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-200 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                <tr><th className="px-2 py-1">Name</th><th className="px-2 py-1">Prefix</th><th className="px-2 py-1">Scopes</th><th className="px-2 py-1">Last used</th><th className="px-2 py-1">Expires</th><th className="px-2 py-1">Status</th><th className="px-2 py-1" /></tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {keys.length === 0 && <tr><td colSpan={7} className="px-2 py-6 text-center text-gray-400">No API keys yet.</td></tr>}
                {keys.map((key) => (
                  <tr key={key.id} className={key.revoked_at ? 'text-gray-400' : ''}>
                    <td className="px-2 py-1 font-semibold text-gray-800">{key.name}</td>
                    <td className="px-2 py-1 font-mono">ttk_{key.prefix}_…</td>
                    <td className="px-2 py-1">{key.scopes.join(', ')}</td>
                    <td className="px-2 py-1">{key.last_used_at || 'never'}</td>
                    <td className="px-2 py-1">{key.expires_at || 'never'}</td>
                    <td className="px-2 py-1">{key.revoked_at ? `revoked ${key.revoked_at}` : 'active'}</td>
                    <td className="px-2 py-1 text-right">{canChange && !key.revoked_at && <button type="button" className={dangerButton} disabled={busy} onClick={() => revokeKey(key)}>Revoke</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canChange && (
            <form onSubmit={createKey} className="mt-4 grid gap-3 border-t border-gray-100 pt-4 md:grid-cols-3">
              <label className="block text-xs font-semibold text-gray-700">Name
                <input value={keyForm.name} onChange={(event) => setKeyForm({ ...keyForm, name: event.target.value })} className={fieldClass()} placeholder="ERP export" required maxLength={100} />
              </label>
              <label className="block text-xs font-semibold text-gray-700">Expires (optional)
                <input type="date" value={keyForm.expires_at} onChange={(event) => setKeyForm({ ...keyForm, expires_at: event.target.value })} className={fieldClass()} />
              </label>
              <div className="text-xs font-semibold text-gray-700 md:col-span-3">Scopes
                <div className="mt-1 grid gap-2 md:grid-cols-2">
                  {scopes.map((scope) => (
                    <label key={scope.name} className="flex items-start gap-2 font-medium">
                      <input type="checkbox" className="mt-0.5" checked={keyForm.scopes.includes(scope.name)} onChange={() => setKeyForm({ ...keyForm, scopes: toggle(keyForm.scopes, scope.name) })} />
                      <span><code className="font-mono">{scope.name}</code><span className="block text-gray-400">{scope.description}</span></span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="md:col-span-3"><button type="submit" className={primaryButton} disabled={busy || !keyForm.name.trim() || keyForm.scopes.length === 0}>Create key</button></div>
            </form>
          )}
        </section>

        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-xs font-bold tracking-wide text-gray-500 uppercase">Webhooks</h3>
          <p className="mb-3 text-[11px] text-gray-500">
            Each delivery is a JSON POST signed with the endpoint secret (<code className="font-mono">X-Timetable-Signature: sha256=HMAC(secret, timestamp.body)</code>); failed posts are retried with growing delays.
            Queue: {Object.entries(queue).map(([status, n]) => `${n} ${status}`).join(', ') || 'empty'}.
          </p>
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-200 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                <tr><th className="px-2 py-1">Name</th><th className="px-2 py-1">URL</th><th className="px-2 py-1">Events</th><th className="px-2 py-1">Last delivery</th><th className="px-2 py-1">State</th><th className="px-2 py-1" /></tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {hooks.length === 0 && <tr><td colSpan={6} className="px-2 py-6 text-center text-gray-400">No webhook endpoints yet.</td></tr>}
                {hooks.map((hook) => (
                  <tr key={hook.id} className={hook.is_active ? '' : 'text-gray-400'}>
                    <td className="px-2 py-1 font-semibold text-gray-800">{hook.name}</td>
                    <td className="max-w-xs truncate px-2 py-1 font-mono" title={hook.url}>{hook.url}</td>
                    <td className="px-2 py-1">{hook.events.join(', ')}</td>
                    <td className="px-2 py-1">{hook.last_delivery_at ? `${hook.last_delivery_at} (${hook.last_status})` : 'none'}</td>
                    <td className="px-2 py-1">{hook.is_active ? 'active' : 'paused'}</td>
                    <td className="px-2 py-1 text-right whitespace-nowrap">
                      {canChange && (
                        <span className="inline-flex gap-1">
                          <button type="button" className={secondaryButton} disabled={busy} onClick={() => setHookForm({ id: hook.id, name: hook.name, url: hook.url, events: hook.events, is_active: hook.is_active })}>Edit</button>
                          <button type="button" className={secondaryButton} disabled={busy} onClick={() => toggleHook(hook)}>{hook.is_active ? 'Pause' : 'Resume'}</button>
                          <button type="button" className={secondaryButton} disabled={busy} onClick={() => rotateSecret(hook)}>Rotate secret</button>
                          <button type="button" className={dangerButton} disabled={busy} onClick={() => deleteHook(hook)}>Delete</button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canChange && (
            <form onSubmit={saveHook} className="mt-4 grid gap-3 border-t border-gray-100 pt-4 md:grid-cols-2">
              <p className="text-xs font-bold text-gray-700 md:col-span-2">{hookForm.id === null ? 'Add an endpoint' : `Edit "${hookForm.name}"`}</p>
              <label className="block text-xs font-semibold text-gray-700">Name
                <input value={hookForm.name} onChange={(event) => setHookForm({ ...hookForm, name: event.target.value })} className={fieldClass()} required maxLength={100} />
              </label>
              <label className="block text-xs font-semibold text-gray-700">URL (https)
                <input type="url" value={hookForm.url} onChange={(event) => setHookForm({ ...hookForm, url: event.target.value })} className={fieldClass()} placeholder="https://erp.example.edu/hooks/timetable" required maxLength={500} spellCheck={false} />
              </label>
              <div className="text-xs font-semibold text-gray-700 md:col-span-2">Events
                <div className="mt-1 grid gap-2 md:grid-cols-2">
                  <label className="flex items-start gap-2 font-medium">
                    <input type="checkbox" className="mt-0.5" checked={hookForm.events.includes('*')} onChange={() => setHookForm({ ...hookForm, events: hookForm.events.includes('*') ? [] : ['*'] })} />
                    <span>All events</span>
                  </label>
                  {events.map((event) => (
                    <label key={event.name} className="flex items-start gap-2 font-medium">
                      <input type="checkbox" className="mt-0.5" disabled={hookForm.events.includes('*')} checked={hookForm.events.includes('*') || hookForm.events.includes(event.name)} onChange={() => setHookForm({ ...hookForm, events: toggle(hookForm.events, event.name) })} />
                      <span><code className="font-mono">{event.name}</code><span className="block text-gray-400">{event.description}</span></span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex gap-2 md:col-span-2">
                <button type="submit" className={primaryButton} disabled={busy || !hookForm.name.trim() || !hookForm.url.trim() || hookForm.events.length === 0}>{hookForm.id === null ? 'Create endpoint' : 'Save endpoint'}</button>
                {hookForm.id !== null && <button type="button" className={secondaryButton} onClick={() => setHookForm({ id: null, name: '', url: '', events: [], is_active: true })}>Cancel</button>}
              </div>
            </form>
          )}
          <div className="mt-4 border-t border-gray-100 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-[10px] font-bold tracking-wider text-gray-400 uppercase">Recent deliveries</h4>
              <button type="button" className={secondaryButton} onClick={() => void loadDeliveries()}>Refresh</button>
            </div>
            <div className="overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-gray-200 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                  <tr><th className="px-2 py-1">When</th><th className="px-2 py-1">Endpoint</th><th className="px-2 py-1">Event</th><th className="px-2 py-1">Attempts</th><th className="px-2 py-1">Status</th><th className="px-2 py-1" /></tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {deliveries.length === 0 && <tr><td colSpan={6} className="px-2 py-6 text-center text-gray-400">Nothing delivered yet.</td></tr>}
                  {deliveries.map((delivery) => (
                    <tr key={delivery.id}>
                      <td className="px-2 py-1 text-gray-600">{delivery.created_at}</td>
                      <td className="px-2 py-1 text-gray-600">{delivery.endpoint_name}</td>
                      <td className="px-2 py-1 font-mono text-gray-800">{delivery.event}</td>
                      <td className="px-2 py-1 text-gray-600">{delivery.attempts}{delivery.response_status !== null && ` (HTTP ${delivery.response_status})`}</td>
                      <td className="px-2 py-1">
                        <span className={statusClass(delivery.status)}>{delivery.status}</span>
                        {delivery.last_error && <span className="block text-[10px] text-gray-400" title={delivery.last_error}>{delivery.last_error}</span>}
                      </td>
                      <td className="px-2 py-1 text-right">{canChange && delivery.status === 'failed' && <button type="button" className={secondaryButton} disabled={busy} onClick={() => retry(delivery)}>Retry</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-xs font-bold tracking-wide text-gray-500 uppercase">Staff single sign-on (OpenID Connect)</h3>
          <p className="mb-3 text-[11px] text-gray-500">
            Staff with a matching account sign in with Google Workspace, Microsoft Entra ID or another OpenID Connect provider. Students always use their password.
            {redirectUri && <> Register this redirect URI with the provider: <code className="font-mono select-all">{redirectUri}</code></>}
          </p>
          <form onSubmit={saveSso} className="grid gap-3 md:grid-cols-2">
            <label className="flex items-center gap-2 text-xs font-semibold text-gray-700 md:col-span-2">
              <input type="checkbox" checked={sso.enabled} disabled={!canChange} onChange={(event) => setSso({ ...sso, enabled: event.target.checked })} />
              Show the single sign-on button on the sign-in pages
            </label>
            <label className="block text-xs font-semibold text-gray-700">Provider
              <select value={sso.provider} disabled={!canChange} onChange={(event) => setSso({ ...sso, provider: event.target.value })} className={fieldClass()}>
                {providers.map((provider) => <option key={provider.name} value={provider.name}>{provider.label}</option>)}
              </select>
            </label>
            <label className="block text-xs font-semibold text-gray-700">Issuer URL
              <input value={sso.issuer} disabled={!canChange} onChange={(event) => setSso({ ...sso, issuer: event.target.value })} className={fieldClass()} placeholder={chosenProvider?.issuer || (sso.provider === 'microsoft' ? 'https://login.microsoftonline.com/<tenant-id>/v2.0' : 'https://idp.example.edu')} spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Client ID
              <input value={sso.client_id} disabled={!canChange} onChange={(event) => setSso({ ...sso, client_id: event.target.value })} className={fieldClass()} autoComplete="off" spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Client secret
              <input type="password" value={clientSecret} disabled={!canChange || clearSecret} onChange={(event) => setClientSecret(event.target.value)} className={fieldClass()} autoComplete="new-password" placeholder={sso.has_client_secret ? 'Stored (encrypted). Type to replace' : 'Not set'} />
              {sso.has_client_secret && (
                <span className="mt-1 flex items-center gap-2 font-medium text-gray-500">
                  <input type="checkbox" checked={clearSecret} disabled={!canChange} onChange={(event) => setClearSecret(event.target.checked)} />
                  Remove the stored secret
                </span>
              )}
            </label>
            <label className="block text-xs font-semibold text-gray-700">Allowed email domains
              <input value={sso.allowed_domains} disabled={!canChange} onChange={(event) => setSso({ ...sso, allowed_domains: event.target.value })} className={fieldClass()} placeholder="college.edu staff.college.edu (empty: any verified email)" spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Button label
              <input value={sso.button_label} disabled={!canChange} onChange={(event) => setSso({ ...sso, button_label: event.target.value })} className={fieldClass()} placeholder="Sign in with Google" maxLength={60} />
            </label>
            <label className="flex items-start gap-2 text-xs font-semibold text-gray-700 md:col-span-2">
              <input type="checkbox" className="mt-0.5" checked={sso.link_by_email} disabled={!canChange} onChange={(event) => setSso({ ...sso, link_by_email: event.target.checked })} />
              <span>Link a first sign-in to the staff account with the same verified email<span className="block font-medium text-gray-400">Off: only accounts already linked below can sign in through the provider.</span></span>
            </label>
            {canChange && <div className="md:col-span-2"><button type="submit" className={primaryButton} disabled={busy}>Save SSO settings</button></div>}
          </form>
          <div className="mt-4 border-t border-gray-100 pt-4">
            <h4 className="mb-2 text-[10px] font-bold tracking-wider text-gray-400 uppercase">Linked accounts</h4>
            <div className="overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-gray-200 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                  <tr><th className="px-2 py-1">User</th><th className="px-2 py-1">Role</th><th className="px-2 py-1">Provider email</th><th className="px-2 py-1">Last sign-in</th><th className="px-2 py-1" /></tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {identities.length === 0 && <tr><td colSpan={5} className="px-2 py-6 text-center text-gray-400">Nobody has signed in through the provider yet.</td></tr>}
                  {identities.map((identity) => (
                    <tr key={identity.id}>
                      <td className="px-2 py-1 font-semibold text-gray-800">{identity.username}</td>
                      <td className="px-2 py-1 text-gray-600">{identity.role}</td>
                      <td className="px-2 py-1 text-gray-600">{identity.email || '-'}</td>
                      <td className="px-2 py-1 text-gray-600">{identity.last_login_at || '-'}</td>
                      <td className="px-2 py-1 text-right">{canChange && <button type="button" className={dangerButton} disabled={busy} onClick={() => unlink(identity)}>Unlink</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-white px-4 py-2">
        <div>
          <FailureNotice message={error} />
          <SuccessNotice message={notice} />
        </div>
      </div>
    </section>
  )
}
