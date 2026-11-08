import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { Dialog } from '../../../shared/components/dialog'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'

type Device = {
  id: number
  deviceId: string
  name: string
  platform: string
  owner: string
  rate: number
  active: boolean
  lastUsed: string
}

type Owner = { id: number; username: string }

const fieldClass = 'w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 outline-none focus:border-indigo-500'

function readDevice(row: Record<string, unknown>): Device {
  return {
    id: safeCount(row.id),
    deviceId: safeText(row.device_id, 64),
    name: safeText(row.name, 80),
    platform: safeText(row.platform, 40),
    owner: safeText(row.owner, 50),
    rate: safeCount(row.rate_limit),
    active: row.is_active === true,
    lastUsed: safeText(row.last_used, 20),
  }
}

export function DevicesPage() {
  const setPageHeader = useSetPageHeader()
  const [devices, setDevices] = useState<Device[]>([])
  const [owners, setOwners] = useState<Owner[]>([])
  const [open, setOpen] = useState(false)
  const [deviceId, setDeviceId] = useState('')
  const [name, setName] = useState('')
  const [platform, setPlatform] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [rate, setRate] = useState('120')
  const [secret, setSecret] = useState('')
  const [rotating, setRotating] = useState<Device | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function load() {
    return apiRequest<Record<string, unknown>>('/api/devices').then((data) => {
      const source = Array.isArray(data.devices) ? data.devices : []
      const people = Array.isArray(data.owners) ? data.owners : []
      setDevices(source.map((item) => readDevice(item as Record<string, unknown>)))
      setOwners(people.map((item) => {
        const row = item as Record<string, unknown>
        return { id: safeCount(row.id), username: safeText(row.username, 50) }
      }).filter((item) => item.id > 0 && item.username))
    })
  }

  useEffect(() => {
    setPageHeader('Mobile devices')
    void load().catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  function register() {
    if (busy) return
    setBusy(true)
    setError('')
    const payload: Record<string, string | number | null> = {
      device_id: deviceId,
      device_name: name,
      platform,
      rate_limit: Number(rate) || 120,
      owner_user_id: ownerId ? Number(ownerId) : null,
    }
    void postJson<Record<string, unknown>>('/api/devices', payload)
      .then((data) => {
        setSecret(safeText(data.secret, 128))
        setOpen(false)
        setDeviceId('')
        setName('')
        setPlatform('')
        setOwnerId('')
        setRate('120')
        return load()
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  function rotate(id: number) {
    if (busy) return
    setBusy(true)
    setError('')
    void postJson<Record<string, unknown>>(`/api/devices/${id}/rotate`, {})
      .then((data) => {
        setSecret(safeText(data.secret, 128))
        setNotice('A new key was created. The previous key no longer works.')
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  function toggle(id: number) {
    if (busy) return
    setBusy(true)
    setError('')
    void postJson(`/api/devices/${id}/toggle`, {})
      .then(() => load())
      .then(() => setNotice('Device status updated.'))
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setBusy(false))
  }

  return (
    <section className="flex flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-500">Register a device, then copy its key. The key is shown once.</p>
        <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white" onClick={() => setOpen(true)}>Register device</button>
      </div>
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="rounded-r-lg border-l-4 border-green-500 bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}
      {secret ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-900">New key — copy it now. It will not be shown again.</p>
          <p className="mt-2 break-all font-mono text-sm text-amber-950">{secret}</p>
          <div className="mt-3 flex gap-2">
            <button type="button" className="rounded-md bg-amber-700 px-3 py-2 text-sm font-semibold text-white" onClick={() => { void navigator.clipboard?.writeText(secret) }}>Copy</button>
            <button type="button" className="rounded-md border border-amber-300 px-3 py-2 text-sm text-amber-900" onClick={() => setSecret('')}>Dismiss</button>
          </div>
        </div>
      ) : null}
      <div className="min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
              <tr>
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">Owner</th>
                <th className="px-4 py-3">Rate limit</th>
                <th className="px-4 py-3">Last used</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {devices.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-16 text-center text-gray-500">No devices registered.</td></tr>
              ) : devices.map((device) => (
                <tr key={device.id} className="hover:bg-indigo-50/40">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-gray-800">{device.name || device.deviceId}</p>
                    <p className="text-xs text-gray-400">{device.deviceId}{device.platform ? ` · ${device.platform}` : ''}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{device.owner || '—'}</td>
                  <td className="px-4 py-3 text-gray-700">{device.rate}/min</td>
                  <td className="px-4 py-3 text-gray-700">{device.lastUsed || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${device.active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>{device.active ? 'Active' : 'Inactive'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-3">
                      <button type="button" className="text-sm font-semibold text-indigo-600" disabled={busy} onClick={() => setRotating(device)}>Rotate key</button>
                      <button type="button" className="text-sm font-semibold text-gray-700" disabled={busy} onClick={() => toggle(device.id)}>{device.active ? 'Deactivate' : 'Activate'}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {rotating ? (
        <Dialog title="Rotate key" onClose={() => { if (!busy) setRotating(null) }}>
          <p className="text-sm text-gray-700">Create a new key for {rotating.name || rotating.deviceId}? The current key stops working.</p>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="rounded-md border border-gray-300 px-3 py-2 text-sm" onClick={() => setRotating(null)}>Cancel</button>
            <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={() => { const id = rotating.id; setRotating(null); rotate(id) }}>Rotate</button>
          </div>
        </Dialog>
      ) : null}
      {open ? (
        <Dialog title="Register device" onClose={() => { if (!busy) setOpen(false) }}>
          <div className="grid gap-3">
            <label className="text-sm text-gray-700">Device ID
              <input className={fieldClass} value={deviceId} maxLength={64} onChange={(event) => setDeviceId(event.target.value)} />
            </label>
            <label className="text-sm text-gray-700">Name
              <input className={fieldClass} value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="text-sm text-gray-700">Platform
              <input className={fieldClass} value={platform} maxLength={40} onChange={(event) => setPlatform(event.target.value)} />
            </label>
            <label className="text-sm text-gray-700">Owner
              <select className={fieldClass} value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
                <option value="">Unassigned</option>
                {owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.username}</option>)}
              </select>
            </label>
            <label className="text-sm text-gray-700">Requests per minute
              <input className={fieldClass} type="number" min={10} max={1000} value={rate} onChange={(event) => setRate(event.target.value)} />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className="rounded-md border border-gray-300 px-3 py-2 text-sm" onClick={() => setOpen(false)}>Cancel</button>
              <button type="button" className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={register}>{busy ? 'Saving…' : 'Register'}</button>
            </div>
          </div>
        </Dialog>
      ) : null}
    </section>
  )
}
