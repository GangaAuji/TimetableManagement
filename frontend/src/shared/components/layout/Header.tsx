import { useEffect, useState, type ReactNode } from 'react'
import { ThemeModeButton } from '../ThemeModeButton'

type HeaderProps = {
  title: ReactNode
  onMenuToggle: () => void
}

function formatClock(date: Date) {
  const day = date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return `${day} • ${time}`
}

export function Header({ title, onMenuToggle }: HeaderProps) {
  const [clock, setClock] = useState(() => formatClock(new Date()))

  useEffect(() => {
    const timer = window.setInterval(() => setClock(formatClock(new Date())), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <header className="shell-header sticky top-0 z-30 px-2 py-3 shadow-sm">
      <div className="flex items-center gap-2 sm:gap-3">
        <button
          id="sidebar-toggle"
          type="button"
          className="shell-chip -ml-1 shrink-0 rounded-lg p-2 md:hidden"
          onClick={onMenuToggle}
          aria-label="Open menu"
        >
          <i className="fas fa-bars text-lg" />
        </button>
        <div className="min-w-0 flex-1 text-lg font-bold sm:text-xl">{title}</div>
        <div className="flex shrink-0 items-center gap-2">
          <ThemeModeButton compact className="shell-chip px-2.5" />
          <div className="shell-chip hidden items-center rounded-full px-3 py-1 text-sm font-medium lg:flex">
            <i className="far fa-clock mr-2" style={{ color: 'var(--color-secondary, #10b981)' }} />
            <span className="whitespace-nowrap">{clock}</span>
          </div>
        </div>
      </div>
    </header>
  )
}
