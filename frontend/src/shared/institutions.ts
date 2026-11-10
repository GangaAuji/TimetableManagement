import { safeCount, safeText } from './security/sanitize'

/** Who else may timetable a room or allocate a faculty member (docs/DESIGN_INSTITUTIONS.md). */
export const sharingOptions = ['private', 'listed', 'organization'] as const
export type Sharing = (typeof sharingOptions)[number]

export const sharingLabels: Record<Sharing, string> = {
  private: 'Only this institution',
  listed: 'Listed to chosen institutions',
  organization: 'Whole organization',
}

export type InstitutionOption = { id: number; name: string; short_name: string }

export function asSharing(value: unknown): Sharing {
  return sharingOptions.includes(value as Sharing) ? (value as Sharing) : 'private'
}

export function asInstitutionOptions(value: unknown): InstitutionOption[] {
  if (!Array.isArray(value)) return []
  return value
    .map((row) => ({
      id: safeCount((row as { id?: unknown })?.id),
      name: safeText((row as { name?: unknown })?.name, 150),
      short_name: safeText((row as { short_name?: unknown })?.short_name, 40),
    }))
    .filter((row) => row.id > 0 && row.name)
    .slice(0, 200)
}

export function asIdList(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  return Array.from(new Set(value.map((item) => safeCount(item)).filter((item) => item > 0))).slice(0, 200)
}

export function institutionLabel(option: InstitutionOption): string {
  return option.short_name || option.name
}
