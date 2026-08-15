/**
 * 앱 껍데기 — 사이드바 + 헤더 + 본문.
 *
 * 본문만 스크롤한다. 헤더·사이드바가 함께 스크롤되면 워크벤치처럼 세로로 긴
 * 화면에서 탭 위치를 잃는다.
 */

import { useState } from 'react'
import { Outlet, useParams } from 'react-router-dom'

import { NoticePopup } from '@/modules/notices/NoticePopup'
import { Header } from '@/shared/layout/Header'
import { Sidebar } from '@/shared/layout/Sidebar'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const { slug } = useParams<{ slug?: string }>()
  const workspaceSlug = slug ?? DEFAULT_WORKSPACE

  return (
    <div className="flex h-svh overflow-hidden">
      <Sidebar collapsed={collapsed} workspaceSlug={workspaceSlug} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          onToggleSidebar={() => setCollapsed((value) => !value)}
          workspaceSlug={workspaceSlug}
        />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>

      {/* 읽지 않은 팝업 공지는 스스로 뜬다 — 공지 화면에 들어가야만 보이면
          "배포 없이 안내를 전한다" 는 목적이 성립하지 않는다. */}
      <NoticePopup />
    </div>
  )
}
