import type { Branding } from '../../api/endpoints'

export function copyrightLine(branding: Branding) {
  const text = branding.copyright_text.trim()
  const institution = branding.institution_name.trim()
  const saved = text.toLowerCase()
  const alreadyComplete = saved.includes('all rights reserved') || (institution !== '' && saved.includes(institution.toLowerCase()))
  if (alreadyComplete) return text
  return `${text} ${new Date().getFullYear()} ${institution}. All rights reserved.`.replace(/\s+/g, ' ').trim()
}

export function Footer({ branding }: { branding: Branding }) {
  return (
    <footer className="mt-auto border-t border-gray-200 bg-white/95 backdrop-blur-sm">
      <div className="px-2 py-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-gray-100 text-accent">
              <i className="fas fa-shield-alt text-sm" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-gray-800">{branding.site_title}</p>
              <p className="text-xs text-gray-500">{copyrightLine(branding)}</p>
            </div>
          </div>
          <div className="text-xs text-gray-500 sm:text-sm md:text-right">
            <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1">
              <i className="fas fa-bolt mr-2" style={{ color: 'var(--color-brand-accent, #047857)' }} />
              {branding.footer_text}
            </span>
          </div>
        </div>
      </div>
    </footer>
  )
}
