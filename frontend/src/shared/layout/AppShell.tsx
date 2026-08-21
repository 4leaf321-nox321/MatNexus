/**
 * 앱 껍데기 — 사이드바 + 헤더 + 본문.
 *
 * 본문만 스크롤한다. 헤더·사이드바가 함께 스크롤되면 워크벤치처럼 세로로 긴
 * 화면에서 탭 위치를 잃는다.
 */

import { Suspense, useState } from 'react'
import { Outlet, useParams } from 'react-router-dom'

import { NoticePopup } from '@/modules/notices/NoticePopup'
import { useAuth } from '@/shared/auth/AuthContext'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Header } from '@/shared/layout/Header'
import { Sidebar } from '@/shared/layout/Sidebar'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

/** 화면 조각을 받아 오는 동안. **빈 화면을 보이지 않는다.** */
function PageSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const { slug } = useParams<{ slug?: string }>()
  const { user } = useAuth()
  // 부서 스코프가 아닌 화면(재료·알림·관리)에서도 사이드바의 '시험 데이터'·
  // '워크벤치' 는 **어느 부서인지** 정해야 한다. `default` 로 두면 자기 부서가
  // 아닌 곳을 가리켜 목록이 비어 보이고, 데이터가 없는 것과 구별이 안 된다.
  const workspaceSlug =
    slug ?? user?.home_workspace_slug ?? user?.memberships[0]?.slug ?? DEFAULT_WORKSPACE

  return (
    <div className="flex h-svh overflow-hidden">
      <Sidebar collapsed={collapsed} workspaceSlug={workspaceSlug} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          onToggleSidebar={() => setCollapsed((value) => !value)}
          workspaceSlug={workspaceSlug}
        />
        <main className="flex-1 overflow-auto p-6">
          {/* 화면 대부분을 나눠 싣는다(router.tsx). 껍데기는 이미 떠 있으므로
              여기서 기다리는 동안에도 사이드바와 상단 바는 그대로 있다. */}
          <Suspense fallback={<PageSkeleton />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      {/* 읽지 않은 팝업 공지는 스스로 뜬다 — 공지 화면에 들어가야만 보이면
          "배포 없이 안내를 전한다" 는 목적이 성립하지 않는다. */}
      <NoticePopup />
    </div>
  )
}
