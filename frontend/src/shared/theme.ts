import type { Branding } from './api/endpoints'
import { staticAssetUrl } from './security/sanitize'

function channel(hex: string, start: number) {
  return Number.parseInt(hex.slice(start, start + 2), 16)
}

export function isLightColor(color: string) {
  const hex = /^#[0-9A-Fa-f]{6}$/.test(color) ? color : '#ffffff'
  const luminance = (0.299 * channel(hex, 1) + 0.587 * channel(hex, 3) + 0.114 * channel(hex, 5)) / 255
  return luminance > 0.62
}

export function inkFor(color: string) {
  return isLightColor(color) ? '#111827' : '#f9fafb'
}

export function mutedFor(color: string) {
  return isLightColor(color) ? '#4b5563' : '#d1d5db'
}

const lightSurface = '#ffffff'
const darkSurface = '#0e1522'

function chromeColor(color: string, mode: 'light' | 'dark') {
  const value = /^#[0-9A-Fa-f]{6}$/.test(color) ? color.toLowerCase() : mode === 'dark' ? darkSurface : lightSurface
  const light = isLightColor(value)
  if (mode === 'light') return light ? value : lightSurface
  if (light || value === '#111827') return darkSurface
  return value
}

export function applyBrandingTheme(branding: Pick<Branding, 'primary_color' | 'secondary_color' | 'accent_color' | 'sidebar_bg' | 'header_bg'>, mode: 'light' | 'dark' = 'light') {
  const root = document.documentElement
  const sidebar = chromeColor(branding.sidebar_bg, mode)
  const header = chromeColor(branding.header_bg, mode)
  const accent = branding.primary_color
  root.style.setProperty('--color-sidebar', sidebar)
  root.style.setProperty('--color-accent', accent)
  root.style.setProperty('--color-header', header)
  root.style.setProperty('--color-secondary', branding.secondary_color)
  root.style.setProperty('--color-brand-accent', branding.accent_color)
  root.style.setProperty('--sidebar-fg', inkFor(sidebar))
  root.style.setProperty('--sidebar-muted', mutedFor(sidebar))
  root.style.setProperty('--sidebar-line', isLightColor(sidebar) ? 'rgba(17,24,39,0.12)' : 'rgba(255,255,255,0.14)')
  root.style.setProperty('--sidebar-hover', isLightColor(sidebar) ? 'rgba(17,24,39,0.06)' : 'rgba(255,255,255,0.08)')
  root.style.setProperty('--header-fg', inkFor(header))
  root.style.setProperty('--header-muted', mutedFor(header))
  root.style.setProperty('--header-line', isLightColor(header) ? '#e5e7eb' : 'rgba(255,255,255,0.16)')
  root.style.setProperty('--accent-fg', inkFor(accent))
}

export function applyBrandingHead(branding: Pick<Branding, 'site_title' | 'favicon'>) {
  if (branding.site_title) document.title = branding.site_title
  const href = staticAssetUrl(branding.favicon)
  if (!href) return
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  if (link.href !== new URL(href, window.location.origin).href) link.href = href
}

export function publishBranding() {
  window.dispatchEvent(new Event('branding-updated'))
}
