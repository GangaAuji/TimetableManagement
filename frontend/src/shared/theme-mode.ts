export type ThemeMode = 'light' | 'dark'

const storageKey = 'timetable-theme'

export function currentThemeMode(): ThemeMode {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function applyThemeMode(mode: ThemeMode) {
  document.documentElement.classList.toggle('dark', mode === 'dark')
  document.documentElement.style.colorScheme = mode
  localStorage.setItem(storageKey, mode)
  window.dispatchEvent(new CustomEvent<ThemeMode>('theme-mode', { detail: mode }))
}

export function applyStoredThemeMode() {
  const saved = localStorage.getItem(storageKey)
  const mode: ThemeMode = saved === 'dark' ? 'dark' : 'light'
  document.documentElement.classList.toggle('dark', mode === 'dark')
  document.documentElement.style.colorScheme = mode
}

export function toggleThemeMode() {
  const next: ThemeMode = currentThemeMode() === 'dark' ? 'light' : 'dark'
  applyThemeMode(next)
  return next
}
