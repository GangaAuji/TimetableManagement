import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type LogRow = {
  id: string
  user_id: string
  username: string
  action: string
  entity_type: string
  status: string
  ip_address: string
  created_at: string
}
function Sparkline({ values, color }: { values: number[]; color: string }) {
  const points = values.length > 0 ? values : [0]
  const width = 128
  const height = 36
  const max = Math.max(...points, 1)
  const step = points.length > 1 ? width / (points.length - 1) : 0
  const line = points.map((value, index) => `${index * step},${height - 4 - (value / max) * (height - 8)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-1 h-9 w-full" role="img" aria-label="Trend for the last 24 hours">
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" points={line} />
    </svg>
  )
}

function StatLink({ href, icon, iconClass, label, value, spark, color }: { href: string; icon: string; iconClass: string; label: string; value: number; spark: number[]; color: string }) {
  return (
    <a href={href} className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-gray-500">{label}</p>
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${iconClass}`}>
          <i className={`fas ${icon} text-sm`} />
        </span>
      </div>
      <p className="mt-2 text-3xl font-bold text-gray-900">{value}</p>
      <Sparkline values={spark} color={color} />
    </a>
  )
}

function WeekChart({ days }: { days: { label: string; total: number }[] }) {
  const bars = days.length > 0 ? days : ['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label) => ({ label, total: 0 }))
  const max = Math.max(...bars.map((day) => day.total), 1)
  return (
    <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="text-xs font-bold text-gray-800">Activity this week</h3>
      <p className="text-[10px] text-gray-400">Actions each day</p>
      <div className="mt-3 flex h-28 items-end gap-1.5">
        {bars.map((day, index) => (
          <div key={`${day.label}-${index}`} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
            <div className="flex w-full flex-1 items-end">
              <div className="w-full rounded-t bg-indigo-400" style={{ height: `${Math.max(8, (day.total / max) * 100)}%` }} title={`${day.total}`} />
            </div>
            <span className="text-[10px] font-semibold text-gray-400">{day.label}</span>
          </div>
        ))}
      </div>
    </article>
  )
}

function logsFrom(value: unknown): LogRow[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((row) => {
    if (!row || typeof row !== 'object') return []
    const record = row as Record<string, unknown>
    const id = String(safeCount(record.id))
    if (id === '0') return []
    return [{
      id,
      user_id: String(safeCount(record.user_id)),
      username: safeText(record.username, 50),
      action: safeText(record.action, 80),
      entity_type: safeText(record.entity_type, 40),
      status: safeText(record.status, 20),
      ip_address: safeText(record.ip_address, 45),
      created_at: safeText(record.created_at, 19),
    }]
  })
}

export function AuditPage() {
  const setPageHeader = useSetPageHeader()
  const [stats, setStats] = useState({ activities: 0, active_users: 0, failed: 0, sessions: 0 })
  const [series, setSeries] = useState<{ activities: number[]; failed: number[]; people: number[]; days: { label: string; total: number }[] }>({ activities: [], failed: [], people: [], days: [] })
  const [active, setActive] = useState<{ username: string; count: string }[]>([])
  const [critical, setCritical] = useState<LogRow[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setPageHeader('Audit')
  }, [setPageHeader])

  useEffect(() => {
    void apiRequest<Record<string, unknown>>('/api/audit?page=1&per_page=10').then((data) => {
      const counts = (data.stats && typeof data.stats === 'object' ? data.stats : {}) as Record<string, unknown>
      setStats({
        activities: safeCount(counts.activities),
        active_users: safeCount(counts.active_users),
        failed: safeCount(counts.failed),
        sessions: safeCount(counts.sessions),
      })
      const chart = (data.series && typeof data.series === 'object' ? data.series : {}) as Record<string, unknown>
      const seriesCounts = (key: string) => (Array.isArray(chart[key]) ? (chart[key] as unknown[]) : []).map((item) => safeCount(item))
      setSeries({
        activities: seriesCounts('activities'),
        failed: seriesCounts('failed'),
        people: seriesCounts('people'),
        days: (Array.isArray(chart.days) ? chart.days : []).flatMap((item) => {
          if (!item || typeof item !== 'object') return []
          const record = item as Record<string, unknown>
          return [{ label: safeText(record.label, 3) || '·', total: safeCount(record.total) }]
        }),
      })
      setCritical(logsFrom(data.critical).slice(0, 5))
      setActive((Array.isArray(data.active_users) ? data.active_users : []).flatMap((row) => {
        if (!row || typeof row !== 'object') return []
        const record = row as Record<string, unknown>
        const username = safeText(record.username, 50)
        return username ? [{ username, count: String(safeCount(record.count)) }] : []
      }).slice(0, 5))
    }).catch((reason: unknown) => setError(messageFrom(reason)))
  }, [])

  const sessionSpark = Array.from({ length: 24 }, () => stats.sessions)

  return (
    <section className="flex flex-col gap-2">
      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p>}
      <div className="grid gap-2 xl:grid-cols-[minmax(0,1fr)_240px]">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <StatLink href="/admin/audit/logs" icon="fa-bolt" iconClass="bg-indigo-50 text-indigo-600" label="Last 24 hours" value={stats.activities} spark={series.activities} color="#6366f1" />
          <StatLink href="/admin/audit/logs" icon="fa-user-check" iconClass="bg-violet-50 text-violet-600" label="Active people" value={stats.active_users} spark={series.people} color="#8b5cf6" />
          <StatLink href="/admin/audit/failed-logins" icon="fa-triangle-exclamation" iconClass="bg-amber-50 text-amber-600" label="Failed logins" value={stats.failed} spark={series.failed} color="#d97706" />
          <StatLink href="/admin/audit/sessions" icon="fa-desktop" iconClass="bg-blue-50 text-blue-600" label="Open sessions" value={stats.sessions} spark={sessionSpark} color="#2563eb" />
        </div>
        <WeekChart days={series.days} />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <a href="/admin/audit/logs" className="rounded-2xl border border-gray-200 bg-white p-4 text-sm font-bold text-gray-800 shadow-sm">Open the log table</a>
        <a href="/admin/audit/sessions" className="rounded-2xl border border-gray-200 bg-white p-4 text-sm font-bold text-gray-800 shadow-sm">Manage sessions</a>
        <a href="/admin/audit/failed-logins" className="rounded-2xl border border-gray-200 bg-white p-4 text-sm font-bold text-gray-800 shadow-sm">Review failed logins</a>
      </div>
      <div className="grid gap-2 lg:grid-cols-2">
        <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-800">Most active this week</h3>
            <a href="/admin/audit/logs" className="text-[10px] font-bold text-indigo-700">View logs</a>
          </div>
          {active.length === 0 ? <p className="text-xs text-gray-500">No activity this week.</p> : active.map((item) => (
            <div key={item.username} className="flex items-center justify-between border-t border-gray-100 py-2.5 text-xs">
              <span className="font-semibold text-gray-800">{item.username}</span>
              <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold text-indigo-700">{item.count}</span>
            </div>
          ))}
        </section>
        <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-800">Recent critical actions</h3>
            <a href="/admin/audit/logs" className="text-[10px] font-bold text-indigo-700">View logs</a>
          </div>
          {critical.length === 0 ? <p className="text-xs text-gray-500">No critical actions.</p> : critical.map((item) => (
            <p key={item.id} className="border-t border-gray-100 py-2.5 text-xs">
              <span className="font-semibold text-gray-800">{item.username || 'Unknown'}</span>
              <span className="mt-0.5 block text-gray-400">{item.action}</span>
            </p>
          ))}
        </section>
      </div>
    </section>
  )
}

export { AuditFailedPage, AuditLogsPage, AuditSessionsPage } from './audit-tables'
