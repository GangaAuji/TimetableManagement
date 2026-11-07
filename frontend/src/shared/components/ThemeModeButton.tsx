import { useEffect, useState } from 'react'
import { currentThemeMode, toggleThemeMode, type ThemeMode } from '../theme-mode'

export function useThemeMode() {
  const [mode, setMode] = useState<ThemeMode>(() => currentThemeMode())

  useEffect(() => {
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<ThemeMode>).detail
      if (detail === 'light' || detail === 'dark') setMode(detail)
    }
    window.addEventListener('theme-mode', sync)
    return () => window.removeEventListener('theme-mode', sync)
  }, [])

  return mode
}

export function ThemeModeButton({ className = '', compact = false }: { className?: string; compact?: boolean }) {
  const mode = useThemeMode()
  const dark = mode === 'dark'

  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ${className}`}
      aria-pressed={dark}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => toggleThemeMode()}
    >
      <i className={`fas ${dark ? 'fa-sun' : 'fa-moon'}`} />
      <span className={compact ? 'hidden text-xs font-bold sm:inline' : 'text-xs font-bold'}>{dark ? 'Light' : 'Dark'}</span>
    </button>
  )
}
