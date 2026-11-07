import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { linkVisible, type AccessSession } from '../../../app/page-access'
import { adminNavigation, portalNavigation, type NavGroup, type NavLink, type NavMenu as NavMenuItem } from '../../../features/navigation/admin-navigation'
import { apiRequest } from '../../api/client'
import { appPath } from '../../api/auth'
import { getCsrfToken, type Branding } from '../../api/endpoints'
import { staticAssetUrl } from '../../security/sanitize'

type SidebarProps = {
  open: boolean
  branding: Branding
  username: string
  role: string
  photo: string
  access: AccessSession
  onNavigate: () => void
}

function visibleGroups(groups: NavGroup[], access: AccessSession) {
  return groups.flatMap((group) => {
    const links = (group.links || []).filter((item) => linkVisible(access, item))
    const menus = (group.menus || []).flatMap((menu) => {
      const children = menu.children.filter((item) => linkVisible(access, item))
      return children.length > 0 ? [{ ...menu, children }] : []
    })
    if (links.length === 0 && menus.length === 0) return []
    return [{ ...group, links, menus }]
  })
}

async function endSession() {
  try {
    const { csrf_token: csrfToken } = await getCsrfToken()
    await apiRequest('/api/session/logout', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    })
    window.location.replace('/')
  } catch {
    window.location.assign(appPath('/logout'))
  }
}

function itemClass() {
  return 'shell-nav nav-item mb-1 flex items-center rounded-lg px-3 py-2 transition-colors'
}

function NavAnchor({ item, onNavigate }: { item: NavLink; onNavigate: () => void }) {
  const className = item.active && item.primary
    ? 'shell-accent nav-item mb-4 flex items-center rounded-lg px-3 py-2.5 shadow-md'
    : item.active
      ? 'shell-nav-active nav-item mb-1 flex items-center rounded-lg px-3 py-2'
      : itemClass()
  return (
    <Link to={item.href} className={className} onClick={onNavigate}>
      <i className={`fas ${item.icon} w-6 text-center`} />
      <span className={item.active && item.primary ? 'ml-3 font-medium' : 'ml-3 text-sm'}>{item.label}</span>
    </Link>
  )
}

function NavMenu({ menu, onNavigate }: { menu: NavMenuItem; onNavigate: () => void }) {
  const childActive = menu.children.some((item) => item.active)
  const [open, setOpen] = useState(childActive)

  useEffect(() => {
    if (childActive) setOpen(true)
  }, [childActive])

  return (
    <div>
      <button
        type="button"
        className={`shell-nav nav-item mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 transition-colors ${childActive ? 'shell-nav-active' : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="flex items-center">
          <i className={`fas ${menu.icon} w-6 text-center`} />
          <span className="ml-3 text-sm">{menu.label}</span>
        </span>
        <i className={`fas fa-chevron-down text-xs transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      {open ? (
        <div className="shell-line mt-1 ml-4 space-y-1 border-l pl-2">
          {menu.children.map((item) => (
            <NavAnchor key={item.href} item={item} onNavigate={onNavigate} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

const sidebarScrollKey = 'sidebar-nav-scroll'

function keepActiveLinkVisible(nav: HTMLElement) {
  const active = nav.querySelector<HTMLElement>('.shell-nav-active')
  if (!active) return
  const navBox = nav.getBoundingClientRect()
  const itemBox = active.getBoundingClientRect()
  if (itemBox.top < navBox.top) nav.scrollTop -= navBox.top - itemBox.top
  else if (itemBox.bottom > navBox.bottom) nav.scrollTop += itemBox.bottom - navBox.bottom
}

export function Sidebar({ open, branding, username, role, photo, access, onNavigate }: SidebarProps) {
  const { pathname } = useLocation()
  const navRef = useRef<HTMLElement>(null)
  const groups = role === 'Teacher' || role === 'Student' ? portalNavigation(role, pathname) : visibleGroups(adminNavigation(pathname), access)
  const initial = (username || 'U').slice(0, 1).toUpperCase()
  const logo = staticAssetUrl(branding.site_logo)
  const portrait = staticAssetUrl(photo)
  const showPhoto = Boolean(portrait) && !portrait.endsWith('/default-avatar.svg') && !portrait.endsWith('/default-avatar.png')

  useLayoutEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const saved = Number(sessionStorage.getItem(sidebarScrollKey) || '')
    if (Number.isFinite(saved) && saved > 0) nav.scrollTop = saved
    keepActiveLinkVisible(nav)
  }, [pathname])

  return (
    <aside
      id="sidebar"
      className={`shell-sidebar shell-line fixed top-0 left-0 z-50 flex h-screen w-64 transform flex-col border-r shadow-xl transition-transform duration-300 ${open ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}
    >
      <div className="shell-line flex h-16 shrink-0 items-center border-b px-4">
        <Link to={role === 'Teacher' || role === 'Student' ? '/' : '/admin'} className="flex min-w-0 flex-1 items-center space-x-2">
          {logo ? (
            <img src={logo} alt="" className="h-8 w-8 shrink-0 object-contain" />
          ) : (
            <div className="shell-accent flex h-8 w-8 shrink-0 items-center justify-center rounded shadow-lg">
              <i className="fas fa-calendar-alt text-xs" />
            </div>
          )}
          <span className="truncate text-base font-bold tracking-wide">{branding.site_title}</span>
        </Link>
        <button type="button" className="shell-muted ml-2 shrink-0 md:hidden" onClick={onNavigate} aria-label="Close menu">
          <i className="fas fa-times" />
        </button>
      </div>

      <nav
        ref={navRef}
        aria-label="Primary"
        className="sidebar-scroll flex-1 space-y-1 overflow-y-auto px-3 py-4 pb-24"
        onScroll={(event) => sessionStorage.setItem(sidebarScrollKey, String(event.currentTarget.scrollTop))}
      >
        {groups.map((group, index) => (
          <div key={`${group.title || 'home'}-${index}`} className={group.title ? 'mt-5' : undefined}>
            {group.title ? (
              <p className="shell-muted mb-2 px-3 text-xs font-bold tracking-wider uppercase">{group.title}</p>
            ) : null}
            {group.menus?.map((menu) => (
              <NavMenu key={menu.label} menu={menu} onNavigate={onNavigate} />
            ))}
            {group.links?.map((item) => (
              <NavAnchor key={item.href} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        ))}
      </nav>

      <div className="shell-line shrink-0 border-t p-4">
        <Link to="/profile" className="shell-nav group mb-3 flex w-full items-center rounded-lg p-2 transition-colors">
          <span className="relative shrink-0">
            {showPhoto ? (
              <img src={portrait} alt="" className="h-9 w-9 rounded-full border border-gray-600 object-cover" />
            ) : (
              <span className="shell-accent flex h-9 w-9 items-center justify-center rounded-full border text-sm font-bold">
                {initial}
              </span>
            )}
            <span className="absolute right-0 bottom-0 h-2.5 w-2.5 rounded-full border-2 bg-green-500" style={{ borderColor: 'var(--color-sidebar, #ffffff)' }} />
          </span>
          <div className="ml-3 overflow-hidden">
            <p className="truncate text-sm font-medium">{username}</p>
            <p className="shell-muted truncate text-xs">View Profile</p>
          </div>
        </Link>
        <button
          type="button"
          onClick={() => void endSession()}
          className="flex w-full items-center justify-center rounded bg-red-600 py-2 text-sm font-medium text-white shadow-lg transition-colors hover:bg-red-700"
        >
          <i className="fas fa-sign-out-alt mr-2" /> Logout
        </button>
      </div>
    </aside>
  )
}
