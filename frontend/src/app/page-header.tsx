import { createContext, useContext, useState, type ReactNode } from 'react'
import { AppShell } from '../shared/components/layout/AppShell'
import type { Branding, SessionInfo } from '../shared/api/endpoints'

const PageHeaderContext = createContext<(node: ReactNode) => void>(() => {})

export function useSetPageHeader() {
  return useContext(PageHeaderContext)
}

type AdminFrameProps = {
  branding: Branding
  session: Extract<SessionInfo, { authenticated: true }>
  children: ReactNode
}

export function AdminFrame({ branding, session, children }: AdminFrameProps) {
  const [header, setHeader] = useState<ReactNode>(branding.admin_title || 'Admin Panel')

  return (
    <PageHeaderContext.Provider value={setHeader}>
      <AppShell branding={branding} session={session} header={header}>
        {children}
      </AppShell>
    </PageHeaderContext.Provider>
  )
}
