/**
 * 사이드바 — 접으면 폭 0으로 줄어들고 본문이 전체 폭을 쓴다(RA 방식).
 *
 * 폭을 0으로 만들되 내부 래퍼는 고정폭을 유지한다. 그래야 접힐 때 글자가
 * 찌그러지지 않고 그대로 잘려 나간다.
 */

import { NavLink, useNavigate } from 'react-router-dom'

import { UNKNOWN_VERSION, systemApi } from '@/shared/api/system'
import { useAuth } from '@/shared/auth/AuthContext'
import { cn } from '@/shared/lib/utils'
import { isAnyManager, isSystemAdmin } from '@/shared/auth/roles'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/shared/components/ui/sheet'
import { REALMS, REALM_ORDER, itemHref, visibleGroups } from '@/shared/layout/navigation'
import { rememberRealm, useRealm } from '@/shared/layout/realm'
import { useResource } from '@/shared/hooks/useResource'

interface SidebarProps {
  collapsed: boolean
  workspaceSlug: string
  onNavigate?: () => void
}

function SidebarBody({ workspaceSlug, onNavigate }: Omit<SidebarProps, 'collapsed'>) {
  const { user } = useAuth()
  // **서버가 정본이다.** 번들에 박으면 그것은 빌드된 버전이지 지금 도는 서버가
  // 아니다 — 배포가 반쯤 끝난 상태에서 둘이 갈리고, 그때 화면이 거짓말을 한다.
  const health = useResource(() => systemApi.health(), [])
  const release = health.data?.version
  // 서버가 이 빌드와 다른 버전인가. **개발에서만 본다** — 배포에서는 백엔드
  // 한 프로세스가 SPA 까지 서빙하므로 둘이 다를 수가 없고, 그 자리에 경고가
  // 뜨면 그것 자체가 거짓말이다.
  const stale =
    import.meta.env.DEV &&
    !!release &&
    release !== UNKNOWN_VERSION &&
    release !== __APP_VERSION__
  // **볼 수 있는 것만 보여 준다.** 눌러야 403 을 아는 메뉴는 "할 수 있는 일" 을
  // 알려 주지 못한다. 권한은 서버가 판정한다 — 여기는 표시일 뿐이다.
  //
  // **그리고 지금 서 있는 영역의 것만.** 재료 물성과 복합 물성은 메뉴를 나눠
  // 갖는다 — 한 목록에 같이 세우면 시편·시험이 두 번 나오고, 사람이 어느 쪽에
  // 있는지 헷갈린다(navigation.ts 의 `NavRealm`).
  const realm = useRealm()
  const navigate = useNavigate()
  const groups = visibleGroups(
    {
      isSystemAdmin: isSystemAdmin(user),
      isAnyManager: isAnyManager(user),
    },
    realm
  )

  return (
    <div className="flex h-full w-60 flex-col">
      <div className="flex h-14 shrink-0 flex-col justify-center border-b px-4">
        <span className="text-base leading-tight font-semibold tracking-tight">MatNexus</span>
        <span className="text-muted-foreground text-xs leading-tight">
          물성 관리
          {/* **못 찾았으면 안 적는다.** `unknown` 을 그대로 띄우면 버전 자리에
              고장난 것처럼 보이는데, 실제로는 개발 경로에서 돈다는 뜻이다. */}
          {release && release !== UNKNOWN_VERSION && (
            <span
              className={cn('ml-1.5 font-mono', stale && 'font-semibold text-amber-600')}
              title={
                stale
                  ? `이 화면은 ${__APP_VERSION__} 인데 서버는 ${release} 입니다. ` +
                    '다른 서버에 붙어 있을 수 있습니다.'
                  : '지금 도는 서버의 버전입니다'
              }
            >
              {/* **버전 글자는 제 노드에 둔다.** 배지를 형제로 붙이면 바깥
                  span 의 글자가 `v1.73.0≠ v1.130.0` 으로 이어져, 버전만으로는
                  찾을 수 없게 된다(시험이 그것을 잡았다). */}
              <span>{release}</span>
              {/* **다르면 말한다.** 개발과 운영이 같은 포트를 쓰던 동안, 프론트가
                  옛 서버(v1.115.0)에 붙어 있는데도 아무 데도 티가 안 났다 —
                  화면은 「존재하지 않는 엔드포인트」 만 말했고, 그것만 보고는
                  코드가 틀린 것인지 서버가 옛것인지 가를 수 없었다(2026-08-28).
                  버전이 이미 여기 떠 있었는데도 **같은지 다른지를 안 말해서**
                  아무도 못 봤다. */}
              {stale && <span className="ml-1">≠ {__APP_VERSION__}</span>}
            </span>
          )}
        </span>
      </div>

      {/* **영역 스위치.** 맨 위에서 갈라진다 — 그룹 하나를 더 두는 것이 아니라
          아래 메뉴 전체가 바뀐다. 누르면 그 영역의 홈으로 간다: 공용 화면(알림)에
          서 있을 때 스위치만 바뀌고 화면은 그대로면 「아무 일도 안 일어났다」 로
          읽힌다. */}
      <div
        role="tablist"
        aria-label="영역"
        className="bg-muted mx-2 mt-3 grid grid-cols-2 gap-0.5 rounded-md p-0.5"
      >
        {REALM_ORDER.map((key) => {
          const active = key === realm
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              title={REALMS[key].hint}
              onClick={() => {
                rememberRealm(key)
                navigate(REALMS[key].home(workspaceSlug))
                onNavigate?.()
              }}
              className={cn(
                'rounded px-2 py-1 text-xs font-medium transition-colors',
                active
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {REALMS[key].label}
            </button>
          )
        })}
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-4">
        {/* **영역까지 키에 넣는다.** 재료·복합 물성 영역이 각자 「홈」 을 갖는데,
            제목 없는 그룹은 첫 항목 이름이 키라 둘이 같은 키가 된다 — 한 영역만
            그려서 지금은 안 겹치지만, 그 전제가 깨지는 순간(HMR 로 옛 사이드바에
            새 메뉴가 물리는 때처럼) React 가 「같은 키」 를 경고한다. */}
        {groups.map((group) => (
          <div key={`${group.realm ?? 'shared'}:${group.title ?? group.items[0]?.label}`}>
            {/* **제목이 없으면 자리도 안 남긴다.** 빈 <p> 를 두면 홈 위에 설명
                없는 여백이 생겨 「뭔가 안 나온다」 로 읽힌다. */}
            {group.title && (
              <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">{group.title}</p>
            )}
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
                    {item.pending && (
                      <span className="text-muted-foreground/70 ml-auto shrink-0 rounded border px-1 text-[10px] leading-4">
                        미구현
                      </span>
                    )}
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

/**
 * 좁은 화면의 메뉴 — **서랍으로 연다.**
 *
 * 옆의 `<aside>` 는 `md` 미만에서 아예 안 그려진다(`hidden md:flex`). 상단의 접기
 * 단추는 폭만 `w-60↔w-0` 으로 바꾸므로, **좁은 화면에서는 눌러도 아무 일이 없고
 * 메뉴로 가는 길이 하나도 없었다** — 주소를 직접 치지 않으면 다른 화면에 못 간다.
 *
 * 고르면 닫는다(`onNavigate`). 서랍이 덮은 채로 두면 방금 연 화면을 못 본다.
 */
export function SidebarDrawer({
  open,
  onOpenChange,
  workspaceSlug,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  workspaceSlug: string
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="bg-sidebar w-72 p-0 md:hidden">
        <SheetHeader className="sr-only">
          <SheetTitle>메뉴</SheetTitle>
        </SheetHeader>
        <SidebarBody workspaceSlug={workspaceSlug} onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
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

// `SidebarBody` 는 서랍과 붙박이 사이드바가 함께 쓴다. 밖으로 내보내지 않는다 —
// 내보내 두면 「어디서 쓰는지 모르는 export」 가 되고, 실제로 그렇게 남아 있었다.
