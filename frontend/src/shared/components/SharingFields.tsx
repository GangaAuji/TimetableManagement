import { fieldClass } from '../../features/academics/ui'
import { institutionLabel, sharingLabels, sharingOptions, type InstitutionOption, type Sharing } from '../institutions'

type Props = {
  /** Every active institution; the form hides itself when there is fewer than two. */
  institutions: InstitutionOption[]
  /** The institution that owns the resource; it is never offered as a share target. */
  ownerId: number | null
  sharing: Sharing
  sharedWith: number[]
  disabled?: boolean
  noun: string
  onChange: (next: { sharing: Sharing; sharedWith: number[] }) => void
}

/**
 * Sharing controls for a room or faculty member: private, listed to chosen
 * institutions, or organization-wide. Rendered only in multi-institution
 * tenants, where the choice changes who can timetable the resource.
 */
export function SharingFields({ institutions, ownerId, sharing, sharedWith, disabled, noun, onChange }: Props) {
  if (institutions.length < 2) return null
  const targets = institutions.filter((item) => item.id !== ownerId)

  function toggle(id: number, checked: boolean) {
    const next = checked ? Array.from(new Set([...sharedWith, id])) : sharedWith.filter((item) => item !== id)
    onChange({ sharing, sharedWith: next })
  }

  return (
    <fieldset className="rounded-xl border border-gray-200 p-3">
      <legend className="px-1 text-xs font-semibold text-gray-700">Sharing</legend>
      <label className="block text-xs font-semibold text-gray-700">
        Who may use this {noun}
        <select
          className={fieldClass()}
          value={sharing}
          disabled={disabled}
          onChange={(event) => onChange({ sharing: event.target.value as Sharing, sharedWith: event.target.value === 'listed' ? sharedWith : [] })}
        >
          {sharingOptions.map((option) => (
            <option key={option} value={option}>{sharingLabels[option]}</option>
          ))}
        </select>
      </label>
      {sharing === 'listed' && (
        <div className="mt-2 grid gap-1 sm:grid-cols-2">
          {targets.map((item) => (
            <label key={item.id} className="flex items-center gap-2 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={sharedWith.includes(item.id)}
                disabled={disabled}
                onChange={(event) => toggle(item.id, event.target.checked)}
              />
              {institutionLabel(item)}
            </label>
          ))}
          {targets.length === 0 && <p className="text-xs text-gray-500">No other institution to list this {noun} to.</p>}
        </div>
      )}
      <p className="mt-2 text-[11px] text-gray-500">
        Clash rules are unchanged: a shared {noun} is still one {noun}, booked once per slot.
      </p>
    </fieldset>
  )
}
