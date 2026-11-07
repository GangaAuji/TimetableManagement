import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { DefinitionItem, displayValue, messageFrom, type DataRow } from '../../../shared/components/data-list'

export function AccountPage() {
  const setPageHeader = useSetPageHeader()
  const [profile, setProfile] = useState<DataRow | null>(null)
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [bio, setBio] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  useEffect(() => {
    setPageHeader('Profile')
    void apiRequest<Record<string, unknown>>('/api/account')
      .then((data) => {
        const nextEmail = displayValue(data.email, 100)
        const nextPhone = displayValue(data.phone, 20)
        const nextBio = displayValue(data.bio, 500)
        setEmail(nextEmail)
        setPhone(nextPhone)
        setBio(nextBio)
        setProfile({
          username: displayValue(data.username),
          role: displayValue(data.role),
          department_name: displayValue(data.department_name),
          status: displayValue(data.status),
        })
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSaved('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest('/api/account', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ email, phone, bio }),
      })
      setSaved('Profile saved.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function savePassword(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSaved('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest('/api/account/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      setCurrentPassword('')
      setNewPassword('')
      setSaved('Password changed.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-5">
        <h2 className="text-sm font-bold text-gray-800">Profile</h2>
        {error && <p className="mt-3 text-xs text-red-700">{error}</p>}
        {saved && <p className="mt-3 text-xs text-emerald-700">{saved}</p>}
        {profile && (
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <DefinitionItem label="Username" value={String(profile.username)} />
            <DefinitionItem label="Role" value={String(profile.role)} />
            <DefinitionItem label="Department" value={String(profile.department_name)} />
            <DefinitionItem label="Status" value={String(profile.status)} />
          </dl>
        )}
      </div>
      <form className="space-y-3 rounded-2xl border border-gray-200 bg-white p-5" onSubmit={(event) => void saveProfile(event)}>
        <h2 className="text-sm font-bold text-gray-800">Contact</h2>
        <label className="block text-xs text-gray-600">Email
          <input className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" value={email} maxLength={100} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="block text-xs text-gray-600">Phone
          <input className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" value={phone} maxLength={20} onChange={(event) => setPhone(event.target.value)} />
        </label>
        <label className="block text-xs text-gray-600">Bio
          <textarea className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" value={bio} maxLength={500} onChange={(event) => setBio(event.target.value)} />
        </label>
        <button type="submit" className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white">Save profile</button>
      </form>
      <form className="space-y-3 rounded-2xl border border-gray-200 bg-white p-5" onSubmit={(event) => void savePassword(event)}>
        <h2 className="text-sm font-bold text-gray-800">Change password</h2>
        <label className="block text-xs text-gray-600">Current password
          <input type="password" autoComplete="current-password" className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" value={currentPassword} maxLength={128} onChange={(event) => setCurrentPassword(event.target.value)} />
        </label>
        <label className="block text-xs text-gray-600">New password
          <input type="password" autoComplete="new-password" className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" value={newPassword} maxLength={128} onChange={(event) => setNewPassword(event.target.value)} />
        </label>
        <button type="submit" className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white">Change password</button>
      </form>
    </section>
  )
}
