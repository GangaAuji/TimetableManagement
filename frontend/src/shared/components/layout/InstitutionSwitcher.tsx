import { useState } from 'react'
import type { SessionInfo } from '../../api/endpoints'
import { sendJson } from '../../../features/academics/api'

type Props = { session: Extract<SessionInfo, { authenticated: true }> }

/**
 * Lets a user who belongs to more than one institution choose which one they
 * work in. A Super Admin can also pick "Whole organization". Rendered only
 * when there is something to choose; every page is reloaded after a switch
 * so cached lists follow the new scope.
 */
export function InstitutionSwitcher({ session }: Props) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const choices = session.institutions
  const canChooseAll = session.organization_wide
  if (choices.length === 0 || (choices.length === 1 && !canChooseAll)) return null

  const current = session.institution ? String(session.institution.id) : ''

  async function choose(value: string) {
    setBusy(true)
    setFailed(false)
    try {
      await sendJson('POST', '/api/session/institution', { institution_id: value ? Number(value) : null })
      window.location.reload()
    } catch {
      setFailed(true)
      setBusy(false)
    }
  }

  return (
    <label className="shell-chip flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium" title="Institution">
      <i className="fas fa-university" style={{ color: 'var(--color-secondary, #10b981)' }} />
      <select
        aria-label="Institution"
        className="max-w-[12rem] truncate bg-transparent text-sm font-medium outline-none"
        value={current}
        disabled={busy}
        onChange={(event) => void choose(event.target.value)}
      >
        {canChooseAll ? <option value="">Whole organization</option> : null}
        {choices.map((item) => (
          <option key={item.id} value={item.id}>
            {item.short_name || item.name}
          </option>
        ))}
      </select>
      {failed ? <span className="text-xs text-red-600">Could not switch</span> : null}
    </label>
  )
}
