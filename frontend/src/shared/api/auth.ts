import { getCsrfToken } from './endpoints'
import { appPath, safeText } from '../security/sanitize'

const loginPaths = new Set(['/login', '/admin/login'])

export { appPath }

export async function submitLogin(path: '/login' | '/admin/login', username: string, password: string) {
  if (!loginPaths.has(path)) {
    return { ok: false as const, message: 'Sign in failed. Check your username and password.' }
  }

  const { csrf_token: csrfToken } = await getCsrfToken()
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  body.set('csrf_token', csrfToken)

  const response = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    cache: 'no-store',
    redirect: 'follow',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'text/html',
    },
    body,
  })

  const html = await response.text()
  const failed = response.url.includes('/login')
  if (!failed && response.ok) {
    return { ok: true as const }
  }

  const alertMatch = html.match(/role="alert">\s*([^<]+)/)
  const message = safeText(alertMatch?.[1], 180)
  return {
    ok: false as const,
    message: message || 'Sign in failed. Check your username and password.',
  }
}
