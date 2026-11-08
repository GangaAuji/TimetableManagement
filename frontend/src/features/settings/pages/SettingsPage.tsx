import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom, postJson } from '../../../shared/components/data-list'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { fieldClass } from '../../academics/ui'
import { fallbackBranding, safeColor, safeText, staticAssetUrl } from '../../../shared/security/sanitize'
import { inkFor, publishBranding } from '../../../shared/theme'

const textFields = [
  ['site_title', 'Site title'],
  ['login_title', 'Login title'],
  ['admin_title', 'Admin title'],
  ['student_title', 'Student title'],
  ['teacher_title', 'Teacher title'],
  ['tagline', 'Tagline'],
  ['welcome_message', 'Welcome message'],
  ['copyright_text', 'Copyright'],
  ['footer_text', 'Footer'],
  ['support_email', 'Support email'],
  ['support_phone', 'Support phone'],
] as const

const colorFields = [
  ['primary_color', 'Primary', 'Active menu and main buttons'],
  ['secondary_color', 'Secondary', 'Small highlights, such as the clock'],
  ['accent_color', 'Accent', 'Extra highlight kept with the saved branding'],
  ['sidebar_bg', 'Sidebar', 'Light colors are used in light mode. Dark colors are used in dark mode'],
  ['header_bg', 'Header', 'Light colors are used in light mode. Dark colors are used in dark mode'],
] as const

const fileFields = [
  ['site_logo', 'Site logo'],
  ['login_logo', 'Login logo'],
  ['favicon', 'Favicon'],
] as const

const backgroundFields = [
  ['login_background', 'Student and teacher sign-in'],
  ['admin_login_background', 'Admin sign-in'],
  ['register_background', 'Registration'],
] as const

const imageFields = [...fileFields, ...backgroundFields]

const primaryButton = 'rounded-xl bg-gray-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50'
const secondaryButton = 'rounded-xl border px-3 py-2 text-xs font-bold'

function emptySettings() {
  return Object.fromEntries([...textFields, ...colorFields, ...imageFields].map(([key]) => [key, '']))
}

export function SettingsPage() {
  const setPageHeader = useSetPageHeader()
  const [values, setValues] = useState<Record<string, string>>(emptySettings)
  const [files, setFiles] = useState<Record<string, File | null>>({})
  const [canChange, setCanChange] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  function apply(data: { settings?: Record<string, unknown>; can_change?: boolean }) {
    const next = emptySettings()
    const source = data.settings || {}
    for (const [key] of textFields) next[key] = safeText(source[key], 240)
    for (const [key] of colorFields) next[key] = safeColor(source[key], fallbackBranding[key])
    for (const [key] of imageFields) next[key] = safeText(source[key], 180)
    setValues(next)
    setCanChange(data.can_change === true)
    setFiles({})
  }

  useEffect(() => {
    setPageHeader('Settings')
    void apiRequest<{ settings?: Record<string, unknown>; can_change?: boolean }>('/api/settings')
      .then(apply)
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
      const body = new FormData()
      for (const [key] of textFields) body.append(key, values[key] || '')
      for (const [key] of colorFields) body.append(key, values[key] || '')
      for (const [key] of imageFields) {
        const file = files[key]
        if (file) body.append(key, file)
      }
      const data = await apiRequest<{ settings?: Record<string, unknown>; can_change?: boolean }>('/api/settings', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body,
      })
      apply(data)
      publishBranding()
      setNotice('Branding settings updated.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    if (!canChange || !window.confirm('Reset branding text and colors to the defaults?')) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const data = await postJson<{ settings?: Record<string, unknown>; can_change?: boolean }>('/api/settings/reset', {})
      apply(data)
      publishBranding()
      setNotice('Branding settings reset to defaults.')
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  const sidebar = /^#[0-9A-Fa-f]{6}$/.test(values.sidebar_bg || '') ? values.sidebar_bg : fallbackBranding.sidebar_bg
  const header = /^#[0-9A-Fa-f]{6}$/.test(values.header_bg || '') ? values.header_bg : fallbackBranding.header_bg
  const primary = /^#[0-9A-Fa-f]{6}$/.test(values.primary_color || '') ? values.primary_color : fallbackBranding.primary_color
  const secondary = /^#[0-9A-Fa-f]{6}$/.test(values.secondary_color || '') ? values.secondary_color : fallbackBranding.secondary_color

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
      <section className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">Branding</h2>
        <p className="text-xs text-gray-500">Titles, colors, and logos. The menu and top bar follow light or dark mode, and text stays readable on the color that matches that mode.</p>
        {!canChange && <p className="mt-2 text-xs text-gray-500">You can view these settings. Changing them needs the branding permission.</p>}
      </section>
      <form id="branding-form" className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px]" onSubmit={(event) => void save(event)}>
        <div className="min-h-0 space-y-4 overflow-auto p-2">
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Titles and contact</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {textFields.map(([key, label]) => (
                <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                  <input value={values[key] || ''} disabled={!canChange} onChange={(event) => setValues({ ...values, [key]: event.target.value })} className={fieldClass()} />
                </label>
              ))}
            </div>
          </section>
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Colors</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {colorFields.map(([key, label, hint]) => {
                const color = /^#[0-9A-Fa-f]{6}$/.test(values[key] || '') ? values[key] : fallbackBranding[key]
                return (
                  <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                    <span className="mt-0.5 block font-medium text-gray-400">{hint}</span>
                    <span className="mt-2 flex items-center gap-2">
                      <input type="color" value={color} disabled={!canChange} onChange={(event) => setValues({ ...values, [key]: event.target.value })} className="h-10 w-12 shrink-0 rounded border border-gray-300 bg-white" />
                      <input value={values[key] || ''} disabled={!canChange} onChange={(event) => setValues({ ...values, [key]: event.target.value })} className={fieldClass()} spellCheck={false} />
                    </span>
                  </label>
                )
              })}
            </div>
          </section>
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-1 text-xs font-bold tracking-wide text-gray-500 uppercase">Logos</h3>
            <p className="mb-3 text-xs text-gray-500">The login logo appears on the sign-in and registration pages. The site logo is the menu mark. The favicon is the browser tab icon.</p>
            <div className="grid gap-4 md:grid-cols-3">
              {fileFields.map(([key, label]) => {
                const current = staticAssetUrl(values[key])
                return (
                  <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                    <span className="mt-2 flex h-16 items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50">
                      {current ? <img src={current} alt="" className="h-12 max-w-full object-contain" /> : <span className="text-[10px] font-medium text-gray-400">No file yet</span>}
                    </span>
                    <input type="file" accept=".png,.jpg,.jpeg,.gif,.svg" disabled={!canChange} onChange={(event) => setFiles({ ...files, [key]: event.target.files?.[0] || null })} className="mt-2 block w-full text-xs" />
                  </label>
                )
              })}
            </div>
          </section>
          <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Page backgrounds</h3>
            <p className="mb-3 text-xs text-gray-500">Shown behind the sign-in and registration cards. Use a wide photo so the edges stay visible.</p>
            <div className="grid gap-4 md:grid-cols-3">
              {backgroundFields.map(([key, label]) => {
                const current = staticAssetUrl(values[key])
                return (
                  <label key={key} className="block text-xs font-semibold text-gray-700">{label}
                    <span className="mt-2 flex h-24 items-center justify-center overflow-hidden rounded-xl border border-dashed border-gray-200 bg-gray-50">
                      {current ? <img src={current} alt="" className="h-full w-full object-cover" /> : <span className="text-[10px] font-medium text-gray-400">No image yet</span>}
                    </span>
                    <input type="file" accept=".png,.jpg,.jpeg,.gif,.svg" disabled={!canChange} onChange={(event) => setFiles({ ...files, [key]: event.target.files?.[0] || null })} className="mt-2 block w-full text-xs" />
                  </label>
                )
              })}
            </div>
          </section>
        </div>
        <aside className="flex min-h-0 flex-col overflow-auto border-t border-gray-100 bg-white p-4 xl:border-t-0 xl:border-l">
          <h3 className="mb-3 text-xs font-bold tracking-wide text-gray-500 uppercase">Preview</h3>
          <div className="mb-3 flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
              {staticAssetUrl(values.site_logo) ? <img src={staticAssetUrl(values.site_logo)} alt="" className="h-10 w-10 object-contain" /> : <i className="fas fa-image text-gray-300" />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-bold text-gray-800">{values.site_title || 'Site title'}</span>
              <span className="block truncate text-[10px] text-gray-400">Site logo</span>
            </span>
            <span className="flex h-8 w-8 items-center justify-center overflow-hidden rounded border border-gray-200 bg-gray-50" title="Favicon">
              {staticAssetUrl(values.favicon) ? <img src={staticAssetUrl(values.favicon)} alt="" className="h-6 w-6 object-contain" /> : <i className="fas fa-star text-[10px] text-gray-300" />}
            </span>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-gray-200">
            <div className="flex items-center gap-2 px-3 py-2 text-xs font-bold" style={{ background: header, color: inkFor(header) }}>
              {staticAssetUrl(values.login_logo) || staticAssetUrl(values.site_logo) ? (
                <img src={staticAssetUrl(values.login_logo) || staticAssetUrl(values.site_logo)} alt="" className="h-5 w-auto max-w-16 object-contain" />
              ) : null}
              <span className="min-w-0 flex-1 truncate">{values.site_title || 'Site title'}</span>
              <span style={{ color: secondary }}>12:00</span>
            </div>
            <div className="flex min-h-44 flex-1">
              <div className="w-28 p-3 text-[11px]" style={{ background: sidebar, color: inkFor(sidebar) }}>
                <div className="mb-2 flex items-center gap-1">
                  {staticAssetUrl(values.site_logo) ? <img src={staticAssetUrl(values.site_logo)} alt="" className="h-4 w-4 object-contain" /> : null}
                  <span className="truncate text-[10px] font-bold">{values.site_title || 'Menu'}</span>
                </div>
                <div className="mb-2 rounded px-2 py-1 font-bold" style={{ background: primary, color: inkFor(primary) }}>Dashboard</div>
                <div className="px-2 py-1 opacity-70">Settings</div>
                <div className="px-2 py-1 opacity-70">Audit</div>
              </div>
              <div className="flex-1 bg-gray-100 p-3 text-[11px] text-gray-500">Page content stays on the light background.</div>
            </div>
          </div>
          <p className="mt-3 text-[11px] leading-5 text-gray-500">The login logo is used on sign-in and registration. The favicon is the browser icon. Colors follow light or dark mode.</p>
        </aside>
      </form>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 bg-white px-4 py-2">
        <div>
          {error && <p className="text-xs text-red-700">{error}</p>}
          {notice && <p className="text-xs text-emerald-700">{notice}</p>}
        </div>
        {canChange && (
          <div className="ml-auto flex gap-2">
            <button type="button" disabled={saving} onClick={() => void reset()} className={secondaryButton}>Reset defaults</button>
            <button type="submit" form="branding-form" disabled={saving} className={primaryButton}>{saving ? 'Saving...' : 'Save settings'}</button>
          </div>
        )}
      </div>
    </section>
  )
}
