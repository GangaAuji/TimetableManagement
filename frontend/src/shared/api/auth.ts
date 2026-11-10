import { getCsrfToken } from './endpoints'
import { safeText } from '../security/sanitize'

const loginPaths = new Set(['/login', '/admin/login'])

export { appPath } from '../security/sanitize'

export type PendingStep = 'totp' | 'enroll'

export type LoginResult =
  | { ok: true; recoveryCodes?: string[] }
  | { ok: false; pending: PendingStep; secret: string; otpauthUri: string; account: string }
  | { ok: false; message: string; cleared?: boolean }

function recoveryCodesOf(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && /^[0-9A-F]{4}-[0-9A-F]{4}$/.test(item)).slice(0, 8)
}

function setupFrom(data: Record<string, unknown>) {
  const secret = typeof data.secret === 'string' && /^[A-Z2-7]{16,64}$/.test(data.secret) ? data.secret : ''
  const otpauthUri = typeof data.otpauth_uri === 'string' && data.otpauth_uri.startsWith('otpauth://totp/') ? data.otpauth_uri : ''
  return { secret, otpauthUri, account: safeText(data.account, 64) }
}

async function readJson(response: Response) {
  try {
    const data: unknown = await response.json()
    return data && typeof data === 'object' ? data as Record<string, unknown> : null
  } catch {
    return null
  }
}

export async function submitLogin(path: '/login' | '/admin/login', username: string, password: string): Promise<LoginResult> {
  if (!loginPaths.has(path)) {
    return { ok: false, message: 'Sign in failed. Check your username and password.' }
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
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body,
  })

  const data = await readJson(response)
  if (!data) {
    return { ok: false, message: 'Sign in could not be completed. Refresh the page and try again.' }
  }
  if (data.ok === true && (data.pending === 'totp' || data.pending === 'enroll')) {
    return { ok: false, pending: data.pending, ...setupFrom(data) }
  }
  if (data.ok === true && 'pending' in data) {
    return { ok: false, message: 'Sign in again.' }
  }
  if (data.ok === true) {
    return { ok: true }
  }
  return {
    ok: false,
    message: safeText(data.message, 180) || 'Sign in failed. Check your username and password.',
  }
}

export async function loadPendingSignIn(): Promise<Extract<LoginResult, { pending: PendingStep }> | null> {
  const response = await fetch('/login/pending', {
    credentials: 'include',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  const data = await readJson(response)
  if (!data || (data.pending !== 'totp' && data.pending !== 'enroll')) return null
  return { ok: false, pending: data.pending, ...setupFrom(data) }
}

export async function submitSecondFactor(code: string): Promise<LoginResult> {
  const { csrf_token: csrfToken } = await getCsrfToken()
  const body = new URLSearchParams()
  body.set('code', code)
  body.set('csrf_token', csrfToken)
  const response = await fetch('/login/second-factor', {
    method: 'POST',
    credentials: 'include',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body,
  })
  const data = await readJson(response)
  if (!data) {
    return { ok: false, message: 'Sign in could not be completed. Refresh the page and try again.' }
  }
  if (data.ok === true) {
    const recoveryCodes = recoveryCodesOf(data.recovery_codes)
    return recoveryCodes.length ? { ok: true, recoveryCodes } : { ok: true }
  }
  return {
    ok: false,
    message: safeText(data.message, 180) || 'That code was not accepted.',
    cleared: data.cleared === true,
  }
}
