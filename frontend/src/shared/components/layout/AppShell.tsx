import { useState, type ReactNode } from 'react'
import { Footer } from './Footer'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import type { Branding, SessionInfo } from '../../api/endpoints'
import { useThemeMode } from '../ThemeModeButton'
import { pagePad } from '../../layout/page-frame'
import { applyBrandingHead, applyBrandingTheme } from '../../theme'

type AppShellProps = {
  branding: Branding
  session: Extract<SessionInfo, { authenticated: true }>
  header: ReactNode
  children: ReactNode
}

export function AppShell({ branding, session, header, children }: AppShellProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const mode = useThemeMode()
  applyBrandingTheme(branding, mode)
  applyBrandingHead(branding)

  return (
    <div className="bg-gray-100 font-sans text-gray-800 antialiased">
      {menuOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-40 bg-gray-900/50 md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      ) : null}
      <Sidebar
        open={menuOpen}
        branding={branding}
        username={session.username}
        role={session.role}
        photo={session.profile_photo}
        access={{ role: session.role, unrestricted: session.unrestricted, permissions: session.permissions }}
        onNavigate={() => setMenuOpen(false)}
      />
      <div className="flex h-screen min-h-0 flex-col overflow-hidden md:ml-64">
        <Header title={header} onMenuToggle={() => setMenuOpen(true)} />
        <main className={`flex min-h-0 w-full flex-1 flex-col overflow-y-auto ${pagePad}`}>{children}</main>
        <Footer branding={branding} />
      </div>
    </div>
  )
}
