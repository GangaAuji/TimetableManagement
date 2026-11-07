import { useEffect, useState, type FormEvent } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken, type SessionInfo } from '../../../shared/api/endpoints'
import { displayValue, messageFrom } from '../../../shared/components/data-list'
import { staticAssetUrl } from '../../../shared/security/sanitize'

const fieldClass = 'w-full rounded-lg border px-3 py-2 text-sm outline-none'
const readClass = 'border-transparent bg-transparent px-0 font-medium text-gray-800'
const editClass = 'border-gray-200 bg-gray-50 focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20'

export function PortalProfilePage() {
  const setPageHeader = useSetPageHeader()
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  const [username, setUsername] = useState('')
  const [role, setRole] = useState(session.role)
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('active')
  const [joined, setJoined] = useState('')
  const [lastSeen, setLastSeen] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [address, setAddress] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [bio, setBio] = useState('')
  const [photoName, setPhotoName] = useState('')
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [photoPath, setPhotoPath] = useState(session.profile_photo)
  const [editing, setEditing] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const portrait = staticAssetUrl(photoPath || session.profile_photo)
  const showPhoto = Boolean(portrait) && !portrait.endsWith('/default-avatar.svg') && !portrait.endsWith('/default-avatar.png')
  const home = role === 'Student' ? 'text-emerald-700 bg-emerald-50' : 'text-indigo-700 bg-indigo-50'

  useEffect(() => {
    setPageHeader('Profile Settings')
    void apiRequest<Record<string, unknown>>('/api/account')
      .then((data) => {
        setUsername(displayValue(data.username, 50))
        setRole(displayValue(data.role, 50) || session.role)
        setDepartment(displayValue(data.department_name, 100))
        setStatus(displayValue(data.status, 20) || 'active')
        setJoined(displayValue(data.created_at, 19))
        setLastSeen(displayValue(data.last_login, 19))
        setBirthDate(displayValue(data.date_of_birth, 10))
        setAddress(displayValue(data.address, 500))
        setEmail(displayValue(data.email, 100))
        setPhone(displayValue(data.phone, 20))
        setBio(displayValue(data.bio, 500))
        setPhotoPath(displayValue(data.profile_photo, 180))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [session.role, setPageHeader])

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSaved('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const form = new FormData()
      form.set('email', email)
      form.set('phone', phone)
      form.set('address', address)
      form.set('bio', bio)
      form.set('date_of_birth', birthDate)
      if (photoFile) form.set('profile_photo', photoFile)
      await apiRequest('/api/account', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: form,
      })
      setEditing(false)
      setSaved('Profile saved.')
      window.location.reload()
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function savePassword() {
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
      setPasswordOpen(false)
      setSaved('Password changed.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  return (
    <form onSubmit={(event) => void saveProfile(event)} className="grid grid-cols-1 gap-2 lg:grid-cols-12">
      <div className="flex flex-col gap-2 lg:col-span-4">
        <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-lg">
          <div className="h-24 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500" />
          <div className="relative px-5 pb-5 text-center">
            <div className="relative -mt-12 mb-3 inline-block">
              {showPhoto ? (
                <img src={portrait} alt="" className="h-24 w-24 rounded-full border-4 border-white object-cover shadow-md" />
              ) : (
                <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-white bg-indigo-600 text-2xl font-bold text-white shadow-md">
                  {(username || session.username || 'U').slice(0, 1).toUpperCase()}
                </div>
              )}
              <label className="absolute right-0 bottom-0 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-2 border-white bg-gray-900 text-white shadow" title="Upload profile photo">
                <i className="fas fa-camera text-xs" />
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/gif"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0] || null
                    setPhotoFile(file)
                    setPhotoName(file ? file.name : '')
                    setEditing(true)
                  }}
                />
              </label>
              <span className={`absolute bottom-1 left-1 h-4 w-4 rounded-full border-2 border-white ${status === 'active' ? 'bg-green-500' : 'bg-red-500'}`} title={status} />
            </div>
            <h2 className="text-xl font-bold text-gray-800">{username || session.username}</h2>
            <div className="mt-1 mb-3 flex items-center justify-center gap-2">
              <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-bold tracking-wide text-indigo-600 uppercase">{role}</span>
              {department ? <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-bold tracking-wide text-gray-600 uppercase">{department}</span> : null}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 border-t border-gray-100 pt-3">
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase">Joined</p>
                <p className="text-xs font-bold text-gray-700">{joined || '-'}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase">Last seen</p>
                <p className="text-xs font-bold text-gray-700">{lastSeen || '-'}</p>
              </div>
            </div>
          </div>
        </section>
        <section className="rounded-2xl border border-gray-100 bg-white p-5 shadow-lg">
          <h3 className="mb-3 text-[10px] font-bold tracking-wider text-gray-400 uppercase">Shortcuts</h3>
          <Link to={role === 'Teacher' || role === 'Student' ? '/' : '/admin'} className={`flex items-center rounded-xl p-2.5 ${home}`}>
            <span className="mr-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white text-xs shadow-sm"><i className={`fas ${role === 'Student' ? 'fa-user-graduate' : 'fa-chalkboard-teacher'}`} /></span>
            <span className="text-sm font-semibold">Dashboard</span>
          </Link>
          <button type="button" onClick={() => setPasswordOpen(true)} className="mt-2 flex w-full items-center rounded-xl bg-gray-50 p-2.5 text-left text-gray-700 hover:bg-gray-100">
            <span className="mr-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white text-xs text-gray-500 shadow-sm"><i className="fas fa-key" /></span>
            <span className="text-sm font-semibold">Change Password</span>
          </button>
        </section>
      </div>

      <section className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-xl lg:col-span-8">
        <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50/30 px-6 py-4">
          <div>
            <h3 className="text-lg font-bold text-gray-800">Profile Details</h3>
            <p className="text-xs text-gray-500">Personal information</p>
          </div>
          <label className="flex items-center gap-2 text-xs font-semibold text-gray-500">
            <input type="checkbox" checked={editing} onChange={(event) => setEditing(event.target.checked)} className="h-4 w-4 accent-indigo-600" />
            {editing ? 'Edit' : 'View'}
          </label>
        </div>
        <div className="flex flex-col gap-2 p-6">
          {error ? <p className="text-xs text-red-700">{error}</p> : null}
          {saved ? <p className="text-xs text-emerald-700">{saved}</p> : null}
          <div>
            <h4 className="mb-3 flex items-center text-[10px] font-bold tracking-wider text-indigo-500 uppercase"><i className="fas fa-address-card mr-2" /> Contact Info</h4>
            <div className="grid gap-5 md:grid-cols-2">
              <label className="text-xs font-semibold text-gray-400 uppercase">Email
                <input type="email" value={email} readOnly={!editing} maxLength={100} onChange={(event) => setEmail(event.target.value)} className={`${fieldClass} mt-1 ${editing ? editClass : readClass}`} />
              </label>
              <label className="text-xs font-semibold text-gray-400 uppercase">Phone
                <input value={phone} readOnly={!editing} maxLength={20} onChange={(event) => setPhone(event.target.value)} className={`${fieldClass} mt-1 ${editing ? editClass : readClass}`} />
              </label>
            </div>
          </div>
          <hr className="border-gray-100" />
          <div>
            <h4 className="mb-3 flex items-center text-[10px] font-bold tracking-wider text-indigo-500 uppercase"><i className="fas fa-user mr-2" /> Personal Details</h4>
            <div className="grid gap-5 md:grid-cols-2">
              <label className="text-xs font-semibold text-gray-400 uppercase">Birth date
                <input type="date" value={birthDate} readOnly={!editing} onChange={(event) => setBirthDate(event.target.value)} className={`${fieldClass} mt-1 ${editing ? editClass : readClass}`} />
              </label>
              <label className="text-xs font-semibold text-gray-400 uppercase">Department
                <input value={department || 'None'} readOnly className={`${fieldClass} mt-1 ${readClass} text-gray-500`} />
              </label>
            </div>
            <label className="mt-5 block text-xs font-semibold text-gray-400 uppercase">Address
              <textarea value={address} readOnly={!editing} maxLength={500} onChange={(event) => setAddress(event.target.value)} className={`${fieldClass} mt-1 min-h-20 ${editing ? editClass : readClass}`} />
            </label>
            {photoName ? <p className="text-xs text-gray-500">Selected photo: {photoName}</p> : null}
            <label className="mt-5 block text-xs font-semibold text-gray-400 uppercase">Bio
              <textarea value={bio} readOnly={!editing} maxLength={500} onChange={(event) => setBio(event.target.value)} className={`${fieldClass} mt-1 min-h-24 ${editing ? editClass : readClass}`} />
            </label>
          </div>
          {editing ? <button type="submit" className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white">Save profile</button> : null}
        </div>
      </section>

      {passwordOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-gray-800">Change Password</h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-semibold text-gray-400 uppercase">Current password
                <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} className={`${fieldClass} mt-1 ${editClass}`} />
              </label>
              <label className="block text-xs font-semibold text-gray-400 uppercase">New password
                <input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className={`${fieldClass} mt-1 ${editClass}`} />
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setPasswordOpen(false)} className="rounded-xl border px-4 py-2 text-xs font-bold text-gray-600">Cancel</button>
              <button type="button" onClick={() => void savePassword()} className="rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white">Update password</button>
            </div>
          </div>
        </div>
      ) : null}
    </form>
  )
}
