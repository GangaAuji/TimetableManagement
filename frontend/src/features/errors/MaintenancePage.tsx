import type { Branding } from '../../shared/api/endpoints'
import { fallbackBranding, staticAssetUrl } from '../../shared/security/sanitize'

const emailAddress = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function MaintenancePage({ branding = fallbackBranding }: { branding?: Branding }) {
  const logo = staticAssetUrl(branding.login_logo) || staticAssetUrl(branding.site_logo)
  const email = emailAddress.test(branding.support_email) ? branding.support_email : ''
  const phone = branding.support_phone.trim()

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(16,185,129,0.22),transparent_42%)]" />
      <section className="relative w-full max-w-lg rounded-3xl bg-white px-8 py-12 text-center shadow-2xl">
        {logo ? <img src={logo} alt="" className="mx-auto mb-5 h-14 w-auto max-w-48 object-contain" /> : null}
        <p className="text-xs font-bold tracking-[0.16em] text-gray-400 uppercase">{branding.site_title}</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-gray-900">{branding.maintenance_title}</h1>
        <p className="mt-4 text-sm leading-6 text-gray-600">{branding.maintenance_message}</p>
        {email || phone ? (
          <p className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-gray-700">
            {email ? <a href={`mailto:${email}`} className="font-bold text-emerald-700">{email}</a> : null}
            {phone ? <span>{phone}</span> : null}
          </p>
        ) : null}
      </section>
    </div>
  )
}
