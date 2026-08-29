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
import { Sidebar } from '@/shared/layout/Sidebar'
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
 * **상한을 푸는 화면.** 폭은 여기가 정한다 — 화면이 스스로 정하면 규칙이 흩어지고,
 * `boundaries.test.ts` 가 그것을 막는다.
 *
 * 시험 상세가 첫 손님이다: 왼쪽에 시험 조건, 오른쪽 탭 안에서 다시 요약값과 곡선
 * 으로 갈리는 3단 구조라 1600 에서는 곡선이 눌린다. **표를 그리는 화면은 넣지
 * 않는다** — 4K 에서 한 줄이 화면을 가로지르면 눈이 행을 놓친다.
 */
const WIDE = [/^\/test-runs\/[^/]+$/]

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const { slug } = useParams<{ slug?: string }>()
  const { pathname } = useLocation()
  const wide = WIDE.some((one) => one.test(pathname))
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

      {/* 화면이 채우는 왼쪽 영역 — **사이드바 바로 옆**이다. 재료 상세가 다른
          재료 목록을 여기 넣는다. 아무도 안 쓰면 폭이 0 이다. */}
      <LeftPanelHost />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          onToggleSidebar={() => setCollapsed((value) => !value)}
          workspaceSlug={workspaceSlug}
        />
        <main className="flex-1 overflow-auto p-6">
          {/* **본문 폭을 여기 한 곳에서 정한다.**
              전에는 화면마다 `mx-auto max-w-4xl` ~ `max-w-7xl` 을 제각각 달았다
              (17개 화면에 5가지 폭). 규칙이 없으니 새 화면은 옆 파일을 베꼈고,
              그래서 같은 성격의 표가 화면마다 다른 폭으로 잘렸다.

              1600px 인 이유: 시험 목록·재료 목록의 열이 10개를 넘는데
              1152px(6xl)에서는 이름과 날짜가 줄바꿈됐다. 반대로 제한을 아예
              없애면 4K 에서 표 한 줄이 화면을 가로지른다 — 눈이 행을 놓친다.

              좁아야 하는 화면(공지·알림·VOC 같이 **읽는** 것)은 자기 안에서
              다시 좁힌다. 그쪽은 폭이 넓을수록 읽기 나쁘다. */}
          {/* **왼쪽 정렬이다(`mx-auto` 를 뺐다).** 가운데 정렬이면 2560 화면에서
              좌우 336px 씩이 죽고, 사이드바와 내용 사이가 그만큼 벌어진다. 더
              나쁜 것은 **상한을 푼 화면으로 옮길 때 왼쪽 끝이 튀는 것**이다 —
              가운데 정렬에서는 넓은 화면과 좁은 화면의 시작점이 다르다.

              왼쪽 정렬이면 폭이 달라도 시작점이 같아 오른쪽으로만 늘어난다. */}
          <div className={cn('w-full', wide ? '' : 'max-w-[1600px]')}>
            {/* 화면 대부분을 나눠 싣는다(router.tsx). 껍데기는 이미 떠 있으므로
                여기서 기다리는 동안에도 사이드바와 상단 바는 그대로 있다. */}
            <Suspense fallback={<PageSkeleton />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      {/* 화면이 채우는 오른쪽 영역. 아무도 안 쓰면 폭이 0 이다.
          **본문 안에 두면 폭 제한(`max-w-[1600px]`)을 따라 가운데로 딸려 들어간다.** */}
      <RightPanelHost />

      {/* 읽지 않은 팝업 공지는 스스로 뜬다 — 공지 화면에 들어가야만 보이면
          "배포 없이 안내를 전한다" 는 목적이 성립하지 않는다. */}
      <NoticePopup />
      </div>
      </LeftPanelProvider>
    </RightPanelProvider>
  )
}
