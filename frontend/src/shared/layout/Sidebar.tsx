/**
 * 사이드바 — 접으면 폭 0으로 줄어들고 본문이 전체 폭을 쓴다(RA 방식).
 *
 * 폭을 0으로 만들되 내부 래퍼는 고정폭을 유지한다. 그래야 접힐 때 글자가
 * 찌그러지지 않고 그대로 잘려 나간다.
 */

import { NavLink } from 'react-router-dom'

import { cn } from '@/shared/lib/utils'
import { NAV_GROUPS, itemHref } from '@/shared/layout/navigation'

interface SidebarProps {
  collapsed: boolean
  workspaceSlug: string
  onNavigate?: () => void
}

function SidebarBody({ workspaceSlug, onNavigate }: Omit<SidebarProps, 'collapsed'>) {
  return (
    <div className="flex h-full w-60 flex-col">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <span className="text-base font-semibold tracking-tight">MatNexus</span>
        <span className="text-muted-foreground text-xs">물성 관리</span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">{group.title}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.label}>
                  <NavLink
                    to={itemHref(item, workspaceSlug)}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                          : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                      )
                    }
                  >
                    <item.icon className="size-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  )
}

export function Sidebar({ collapsed, workspaceSlug }: SidebarProps) {
  return (
    <aside
      data-app-chrome="sidebar"
      data-collapsed={collapsed}
      aria-hidden={collapsed}
      className={cn(
        'bg-sidebar hidden h-full shrink-0 flex-col overflow-hidden md:flex',
        'transition-[width] duration-200 ease-in-out',
        collapsed ? 'w-0 border-r-0' : 'w-60 border-r',
      )}
    >
      <SidebarBody workspaceSlug={workspaceSlug} />
    </aside>
  )
}

export { SidebarBody }
