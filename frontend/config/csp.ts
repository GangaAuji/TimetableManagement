type HeaderMode = 'development' | 'production'

const styleHosts = 'https://fonts.googleapis.com https://cdnjs.cloudflare.com'
const fontHosts = 'https://fonts.gstatic.com https://cdnjs.cloudflare.com'
const imageHosts = 'https://images.unsplash.com'

export function securityHeaders(mode: HeaderMode): Record<string, string> {
  const development = mode === 'development'
  const scriptSrc = development ? "'self' 'unsafe-inline' 'unsafe-eval'" : "'self'"
  const styleSrc = development
    ? `'self' 'unsafe-inline' ${styleHosts}`
    : `'self' ${styleHosts}`
  const connectSrc = development ? "'self' ws://127.0.0.1:5173" : "'self'"

  const policy = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    `style-src ${styleSrc}`,
    "style-src-attr 'unsafe-inline'",
    `font-src 'self' data: ${fontHosts}`,
    `img-src 'self' data: ${imageHosts}`,
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "worker-src 'none'",
    "manifest-src 'self'",
  ].join('; ')

  return {
    'Content-Security-Policy': policy,
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'X-Permitted-Cross-Domain-Policies': 'none',
  }
}
