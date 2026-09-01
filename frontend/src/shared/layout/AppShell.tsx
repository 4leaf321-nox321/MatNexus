/**
 * 앱 껍데기 — 사이드바 + 헤더 + 본문.
 *
 * 본문만 스크롤한다. 헤더·사이드바가 함께 스크롤되면 워크벤치처럼 세로로 긴
 * 화면에서 탭 위치를 잃는다.
 */

import { Suspense, useState } from 'react'
import { Outlet, useLocation, useParams } from 'react-router-dom'

import { NoticePopup } from '@/modules/notices/NoticePopup'
import { useAuth } from '@/shared/auth/AuthContext'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Header } from '@/shared/layout/Header'
import {
  LeftPanelHost,
  LeftPanelProvider,
  RightPanelHost,
  RightPanelProvider,
} from '@/shared/layout/SidePanel'
import { Sidebar, SidebarDrawer } from '@/shared/layout/Sidebar'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'
import { cn } from '@/shared/lib/utils'

/** 화면 조각을 받아 오는 동안. **빈 화면을 보이지 않는다.** */
function PageSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}


/**
 * **화면 높이를 채우고, 스크롤은 안쪽에서 하는 화면.**
 *
 * 기본은 본문이 통째로 스크롤된다 — 대부분의 화면이 「위에서 아래로 읽는」 것이라
 * 그게 맞다.
 *
 * 여기 있는 것은 **나란히 둔 둘을 견주는** 화면이다. 페이지가 통째로 스크롤되면
 * 오른쪽을 내려 보는 동안 왼쪽이 위로 사라지는데, 나란히 둔 뜻이 바로 그 둘을
 * 함께 보는 것이다.
 *
 *     /materials/:id   선언 물성 | 잰 값 — 문헌값과 실측을 견준다
 *
 * **함부로 늘리지 않는다.** 안쪽 스크롤은 화면마다 높이를 스스로 맞춰야 하고,
 * 그것을 빠뜨리면 내용이 잘린 채로 아무 표시 없이 사라진다.
 */
export const FULL_HEIGHT = [/^\/materials\/[^/]+$/]

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const { slug } = useParams<{ slug?: string }>()
  const { pathname } = useLocation()
  const tall = FULL_HEIGHT.some((one) => one.test(pathname))
  const { user } = useAuth()
  // 부서 스코프가 아닌 화면(재료·알림·관리)에서도 사이드바의 '홈'·'워크벤치'·
  // '부서 멤버' 는 **어느 부서인지** 정해야 한다. `default` 로 두면 자기 부서가
  // 아닌 곳을 가리켜 목록이 비어 보이고, 데이터가 없는 것과 구별이 안 된다.
  const workspaceSlug =
    slug ?? user?.home_workspace_slug ?? user?.memberships[0]?.slug ?? DEFAULT_WORKSPACE

  return (
    /* 오른쪽 영역의 여닫기는 **상단 바**가 한다 — 껍데기를 여닫는 단추는 다
       거기 있다. 그래서 `Header` 와 자리(`RightPanelHost`)가 같은 제공자 안에
       있어야 한다. */
    <RightPanelProvider>
      <LeftPanelProvider>
      <div className="flex h-svh overflow-hidden">
      <Sidebar collapsed={collapsed} workspaceSlug={workspaceSlug} />
      <SidebarDrawer open={drawer} onOpenChange={setDrawer} workspaceSlug={workspaceSlug} />

      {/* 화면이 채우는 왼쪽 영역 — **사이드바 바로 옆**이다. 재료 상세가 다른
          재료 목록을 여기 넣는다. 아무도 안 쓰면 폭이 0 이다. */}
      <LeftPanelHost />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          // **같은 단추가 화면 폭에 따라 다른 일을 한다.** 넓으면 붙박이 사이드바를
          // 접고, 좁으면(`md` 미만, 사이드바가 아예 없다) 서랍을 연다.
          onToggleSidebar={() => {
            if (window.matchMedia('(min-width: 768px)').matches) {
              setCollapsed((value) => !value)
            } else {
              setDrawer(true)
            }
          }}
          workspaceSlug={workspaceSlug}
        />
        <main className={cn('flex-1 p-6', tall ? 'min-h-0 overflow-hidden' : 'overflow-auto')}>
          {/* **본문은 폭을 다 쓴다. 상한이 없다**(2026-08-30 에 걷었다).

              전에는 화면마다 `mx-auto max-w-4xl` ~ `max-w-7xl` 을 제각각 달았다
              (17개 화면에 5가지 폭). 그것을 한 곳으로 모으면서 1600px 을 상한으로
              뒀고, 넓어야 하는 화면은 경로 목록(`WIDE`)으로 풀어 줬다.

              **그 상한이 실제로 표를 접었다.** 시편 목록의 치수 칸
              (`width 12.47 mm · thickness 0.986 mm · gauge_length 50 mm`)이 두 줄로
              접혔고, 열을 줄이거나 목록에 경로를 더하는 것으로 계속 막아야 했다 —
              「이 화면도 넣자」 가 반복되면 목록이 곧 전부가 된다.

              4K 에서 줄이 길어지는 문제는 남는다. 그때는 **그 표가 열 폭을 스스로
              잡는다**(`w-px`·`min-w`) — 폭을 껍데기가 잘라 내는 것보다 낫다.

              좁아야 하는 화면(공지·알림·VOC 같이 **읽는** 것)은 자기 안에서
              다시 좁힌다(`boundaries.test.ts` 의 `NARROW_BY_DESIGN`). */}
          {/* **왼쪽 정렬이다(`mx-auto` 를 뺐다).** 가운데 정렬이면 2560 화면에서
              좌우가 죽고, 사이드바와 내용 사이가 그만큼 벌어진다. */}
          <div className={cn('w-full', tall && 'h-full')}>
            {/* 화면 대부분을 나눠 싣는다(router.tsx). 껍데기는 이미 떠 있으므로
                여기서 기다리는 동안에도 사이드바와 상단 바는 그대로 있다. */}
            <Suspense fallback={<PageSkeleton />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      {/* 화면이 채우는 오른쪽 영역. 아무도 안 쓰면 폭이 0 이다.
          **본문 안에 두면 본문의 여백(`p-6`) 안으로 들어가고 본문과 함께
          스크롤된다** — 사이드바와 같은 층에 있어야 화면 끝에 붙는다. */}
      <RightPanelHost />

      {/* 읽지 않은 팝업 공지는 스스로 뜬다 — 공지 화면에 들어가야만 보이면
          "배포 없이 안내를 전한다" 는 목적이 성립하지 않는다. */}
      <NoticePopup />
      </div>
      </LeftPanelProvider>
    </RightPanelProvider>
  )
}
