import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { FailureNotice, SuccessNotice } from '../../../shared/components/success-notice'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { fieldClass } from '../../academics/ui'

type Settings = {
  enabled: boolean
  smtp_host: string
  smtp_port: string
  smtp_user: string
  smtp_from: string
  smtp_starttls: boolean
  reply_to: string
  has_password: boolean
  defaulter_alerts: boolean
  cancellation_alerts: boolean
  proxy_alerts: boolean
  not_marked_digest: boolean
  shift_alerts: boolean
}
type Status = { enabled: boolean; delivery: string; smtp_host: string; queued: number; failed: number; sent: number }
type Payload = { settings?: Record<string, unknown>; status?: Record<string, unknown>; can_change?: boolean }
type OutboxRow = { id: number; kind: string; recipient_email: string; subject: string; status: string; attempts: number; last_error: string; created_at: string; sent_at: string }

const switches = [
  ['defaulter_alerts', 'Defaulter alerts', 'Students below the attendance threshold, once per month, after the nightly close-day'],
  ['cancellation_alerts', 'Lecture cancelled', 'Roster students and the teacher when a lecture is cancelled'],
  ['proxy_alerts', 'Substitute arranged', 'Both teachers when a proxy is assigned'],
  ['not_marked_digest', 'Not-marked digest', 'Each HOD: yesterday\'s lectures in their department with no attendance'],
  ['shift_alerts', 'Shift requests', 'The HOD on a new request; the teacher on the decision'],
] as const

const emptySettings: Settings = {
  enabled: true, smtp_host: '', smtp_port: '', smtp_user: '', smtp_from: '', smtp_starttls: true, reply_to: '', has_password: false,
  defaulter_alerts: true, cancellation_alerts: true, proxy_alerts: true, not_marked_digest: true, shift_alerts: true,
}
const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const secondaryButton = 'rounded-xl border px-3 py-2 text-xs font-bold disabled:opacity-50'

function readSettings(source: Record<string, unknown> | undefined): Settings {
  const value = source || {}
  return {
    enabled: value.enabled !== false,
    smtp_host: safeText(value.smtp_host, 190),
    smtp_port: value.smtp_port ? String(safeCount(value.smtp_port)) : '',
    smtp_user: safeText(value.smtp_user, 190),
    smtp_from: safeText(value.smtp_from, 190),
    smtp_starttls: value.smtp_starttls !== false,
    reply_to: safeText(value.reply_to, 190),
    has_password: value.has_password === true,
    defaulter_alerts: value.defaulter_alerts !== false,
    cancellation_alerts: value.cancellation_alerts !== false,
    proxy_alerts: value.proxy_alerts !== false,
    not_marked_digest: value.not_marked_digest !== false,
    shift_alerts: value.shift_alerts !== false,
  }
}

function readStatus(source: Record<string, unknown> | undefined): Status {
  const value = source || {}
  return {
    enabled: value.enabled === true,
    delivery: safeText(value.delivery, 20),
    smtp_host: safeText(value.smtp_host, 190),
    queued: safeCount(value.queued),
    failed: safeCount(value.failed),
    sent: safeCount(value.sent),
  }
}

function readOutbox(rows: Record<string, unknown>[] | undefined): OutboxRow[] {
  return (rows || []).map((row) => ({
    id: safeCount(row.id),
    kind: safeText(row.kind, 40),
    recipient_email: safeText(row.recipient_email, 190),
    subject: safeText(row.subject, 200),
    status: safeText(row.status, 20),
    attempts: safeCount(row.attempts),
    last_error: safeText(row.last_error, 200),
    created_at: safeText(row.created_at, 19),
    sent_at: safeText(row.sent_at, 19),
  })).filter((row) => row.id > 0)
}

export function NotificationSettingsPage() {
  const setPageHeader = useSetPageHeader()
  const [values, setValues] = useState<Settings>(emptySettings)
  const [status, setStatus] = useState<Status>({ enabled: false, delivery: 'none', smtp_host: '', queued: 0, failed: 0, sent: 0 })
  const [canChange, setCanChange] = useState(false)
  const [password, setPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [testTo, setTestTo] = useState('')
  const [outbox, setOutbox] = useState<OutboxRow[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  function apply(data: Payload) {
    setValues(readSettings(data.settings))
    setStatus(readStatus(data.status))
    setCanChange(data.can_change === true)
    setPassword('')
    setClearPassword(false)
  }

  async function loadOutbox() {
    try {
      const data = await apiRequest<{ notifications?: Record<string, unknown>[]; status?: Record<string, unknown> }>('/api/notifications')
      setOutbox(readOutbox(data.notifications))
      setStatus(readStatus(data.status))
    } catch {
      /* the settings card still works without the list */
    }
  }

  useEffect(() => {
    setPageHeader('Notifications')
    void apiRequest<Payload>('/api/notifications/settings')
      .then((data) => { apply(data); void loadOutbox() })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!canChange) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const payload: Record<string, unknown> = {
        enabled: values.enabled,
        smtp_host: values.smtp_host,
        smtp_port: values.smtp_port ? Number(values.smtp_port) : '',
        smtp_user: values.smtp_user,
        smtp_from: values.smtp_from,
        smtp_starttls: values.smtp_starttls,
        reply_to: values.reply_to,
        defaulter_alerts: values.defaulter_alerts,
        cancellation_alerts: values.cancellation_alerts,
        proxy_alerts: values.proxy_alerts,
        not_marked_digest: values.not_marked_digest,
        shift_alerts: values.shift_alerts,
      }
      if (password) payload.smtp_password = password
      if (clearPassword) payload.clear_password = true
      const data = await apiRequest<Payload>('/api/notifications/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(payload),
      })
      apply(data)
      setNotice('Notification settings saved.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function sendTest() {
    if (!canChange || !testTo.trim()) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await postJson<{ queued?: unknown }>('/api/notifications/test', { to: testTo.trim() })
      setNotice('Test message queued. The worker sends it on its next pass; watch the outbox below.')
      await loadOutbox()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const deliveryLabel = status.delivery === 'tenant' ? `this institution's SMTP account (${status.smtp_host})`
    : status.delivery === 'server' ? `the server's SMTP account (${status.smtp_host})`
      : 'nowhere yet: no SMTP account is configured, so messages wait in the queue'

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Notifications</h2>
        <p className="text-xs text-gray-500">Email alerts for defaulters, cancellations, substitutes, unmarked lectures and shift requests. Mail goes through {deliveryLabel}.</p>
        <p className="mt-1 text-[11px] font-medium text-gray-500">Queue: {status.queued} waiting, {status.failed} failed, {status.sent} sent.</p>
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view these settings. Changing them needs the settings permission.</p>}
      </section>
      <form id="notification-form" className="min-h-0 flex-1 space-y-4 overflow-auto p-2" onSubmit={(event) => void save(event)}>
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Delivery</h3>
          <label className="mb-3 flex items-center gap-2 text-xs font-semibold text-gray-700">
            <input type="checkbox" checked={values.enabled} disabled={!canChange} onChange={(event) => setValues({ ...values, enabled: event.target.checked })} />
            Send notifications for this institution
          </label>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-xs font-semibold text-gray-700">SMTP host
              <input value={values.smtp_host} disabled={!canChange} onChange={(event) => setValues({ ...values, smtp_host: event.target.value })} className={fieldClass()} placeholder="Leave empty to use the server account" spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Port
              <input type="number" min={1} max={65535} value={values.smtp_port} disabled={!canChange} onChange={(event) => setValues({ ...values, smtp_port: event.target.value })} className={fieldClass()} placeholder="587" />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Username
              <input value={values.smtp_user} disabled={!canChange} onChange={(event) => setValues({ ...values, smtp_user: event.target.value })} className={fieldClass()} autoComplete="off" spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Password
              <input type="password" value={password} disabled={!canChange || clearPassword} onChange={(event) => setPassword(event.target.value)} className={fieldClass()} autoComplete="new-password" placeholder={values.has_password ? 'Stored (encrypted). Type to replace' : 'Not set'} />
              {values.has_password && (
                <span className="mt-1 flex items-center gap-2 font-medium text-gray-500">
                  <input type="checkbox" checked={clearPassword} disabled={!canChange} onChange={(event) => setClearPassword(event.target.checked)} />
                  Remove the stored password
                </span>
              )}
            </label>
            <label className="block text-xs font-semibold text-gray-700">From address
              <input type="email" value={values.smtp_from} disabled={!canChange} onChange={(event) => setValues({ ...values, smtp_from: event.target.value })} className={fieldClass()} spellCheck={false} />
            </label>
            <label className="block text-xs font-semibold text-gray-700">Reply-to
              <input type="email" value={values.reply_to} disabled={!canChange} onChange={(event) => setValues({ ...values, reply_to: event.target.value })} className={fieldClass()} spellCheck={false} />
            </label>
          </div>
          <label className="mt-3 flex items-center gap-2 text-xs font-semibold text-gray-700">
            <input type="checkbox" checked={values.smtp_starttls} disabled={!canChange} onChange={(event) => setValues({ ...values, smtp_starttls: event.target.checked })} />
            Use STARTTLS
          </label>
        </section>
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Triggers</h3>
          <div className="grid gap-3 md:grid-cols-2">
            {switches.map(([key, label, hint]) => (
              <label key={key} className="flex items-start gap-2 text-xs font-semibold text-gray-700">
                <input type="checkbox" className="mt-0.5" checked={values[key]} disabled={!canChange} onChange={(event) => setValues({ ...values, [key]: event.target.checked })} />
                <span>{label}<span className="block font-medium text-gray-400">{hint}</span></span>
              </label>
            ))}
          </div>
        </section>
        {canChange && (
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Test</h3>
            <div className="flex flex-wrap items-end gap-2">
              <label className="block min-w-64 text-xs font-semibold text-gray-700">Send a test message to
                <input type="email" value={testTo} onChange={(event) => setTestTo(event.target.value)} className={fieldClass()} placeholder="you@example.edu" spellCheck={false} />
              </label>
              <button type="button" disabled={saving || !testTo.trim()} onClick={() => void sendTest()} className={secondaryButton}>Queue test</button>
            </div>
            <p className="mt-2 text-[11px] text-gray-500">Save the account first; the test uses the saved settings.</p>
          </section>
        )}
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs font-bold tracking-wide text-gray-500 uppercase">Outbox</h3>
            <button type="button" onClick={() => void loadOutbox()} className={secondaryButton}>Refresh</button>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-200 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                <tr><th className="px-2 py-1">When</th><th className="px-2 py-1">Kind</th><th className="px-2 py-1">To</th><th className="px-2 py-1">Subject</th><th className="px-2 py-1">Status</th></tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {outbox.length === 0 && <tr><td colSpan={5} className="px-2 py-6 text-center text-gray-400">Nothing queued yet.</td></tr>}
                {outbox.map((row) => (
                  <tr key={row.id}>
                    <td className="px-2 py-1 text-gray-600">{row.created_at}</td>
                    <td className="px-2 py-1 text-gray-600">{row.kind}</td>
                    <td className="px-2 py-1 text-gray-600">{row.recipient_email || '-'}</td>
                    <td className="px-2 py-1 text-gray-800">{row.subject}</td>
                    <td className="px-2 py-1">
                      <span className={row.status === 'sent' ? 'font-semibold text-emerald-700' : row.status === 'failed' ? 'font-semibold text-red-600' : 'text-gray-600'}>{row.status}</span>
                      {row.last_error && <span className="block text-[10px] text-gray-400" title={row.last_error}>{row.last_error}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </form>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-white px-4 py-2">
        <div>
          <FailureNotice message={error} />
          <SuccessNotice message={notice} />
        </div>
        {canChange && (
          <button type="submit" form="notification-form" disabled={saving} className={`ml-auto ${primaryButton}`}>{saving ? 'Saving...' : 'Save settings'}</button>
        )}
      </div>
    </section>
  )
}
