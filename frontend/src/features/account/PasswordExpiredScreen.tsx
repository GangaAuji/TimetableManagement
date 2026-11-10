import { useState, type FormEvent } from 'react'
import { apiRequest } from '../../shared/api/client'
import { getCsrfToken, type Branding } from '../../shared/api/endpoints'
import { messageFrom, postJson } from '../../shared/components/data-list'
import { FailureNotice } from '../../shared/components/success-notice'

export function PasswordExpiredScreen({ branding, onSuccess }: { branding: Branding; onSuccess: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      await apiRequest('/api/account/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      onSuccess()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function signOut() {
    try {
      await postJson('/api/session/logout', {})
    } catch {
      // The session is cleared on the server when the call succeeds. A failed call still returns to sign-in.
    }
    window.location.assign('/')
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-100 p-6">
      <form className="w-full max-w-md space-y-3 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm" onSubmit={(event) => void save(event)}>
        <p className="text-xs font-bold tracking-wide text-gray-500 uppercase">{branding.institution_short_name}</p>
        <h1 className="text-lg font-bold text-gray-900">Change your password</h1>
        <p className="text-sm text-gray-600">This password has reached the age set in the security policy. Choose a new one to continue.</p>
        <FailureNotice message={error} />
        <label className="block text-xs font-semibold text-gray-700">Current password
          <input type="password" autoComplete="current-password" value={currentPassword} maxLength={128} onChange={(event) => setCurrentPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" />
        </label>
        <label className="block text-xs font-semibold text-gray-700">New password
          <input type="password" autoComplete="new-password" value={newPassword} maxLength={128} onChange={(event) => setNewPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2" />
        </label>
        <div className="flex items-center justify-between gap-3">
          <button type="button" onClick={() => void signOut()} className="text-xs font-bold text-gray-500">Sign out</button>
          <button type="submit" disabled={saving} className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{saving ? 'Saving...' : 'Update password'}</button>
        </div>
      </form>
    </main>
  )
}
