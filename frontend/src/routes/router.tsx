/**
 * 라우트 표.
 *
 * 사이드바(navigation.ts)에 있는 항목은 여기에 대응 경로가 있어야 한다. 아직
 * 구현되지 않은 화면은 Placeholder로 두되 **어느 단계에서 들어오는지 명시**한다.
 *
 * `/login` 과 `/force-password-change` 만 가드 밖에 있고 나머지는 전부
 * ProtectedRoute 아래에 둔다 — 새 화면을 추가할 때 가드를 깜빡할 자리가 없도록.
 */

import { createBrowserRouter, Navigate } from 'react-router-dom'

import AccountsAdminPage from '@/modules/accounts/AccountsAdminPage'
import ForcePasswordChangePage from '@/modules/auth/ForcePasswordChangePage'
import LoginPage from '@/modules/auth/LoginPage'
import SignupPage from '@/modules/auth/SignupPage'
import MembersPage from '@/modules/workspaces/MembersPage'
import WorkspacesAdminPage from '@/modules/workspaces/WorkspacesAdminPage'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { Placeholder } from '@/shared/components/Placeholder'
import { AppShell } from '@/shared/layout/AppShell'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

const stub = (title: string, phase: string, description?: string) => ({
  element: <Placeholder title={title} phase={phase} description={description} />,
})

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: '/force-password-change', element: <ForcePasswordChangePage /> },
      {
        path: '/',
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to={`/w/${DEFAULT_WORKSPACE}`} replace /> },

          // 카탈로그 (전사)
          {
            path: 'materials',
            ...stub('재료 카탈로그', 'Phase 2', '재료 검색과 상세 5개 영역.'),
          },
          { path: 'materials/:id', ...stub('재료 상세', 'Phase 2') },
          { path: 'compare', ...stub('곡선 비교', 'Phase 3') },

          // 내 활동
          { path: 'personal', ...stub('내 작업함', 'Phase 1') },
          {
            path: 'notifications',
            ...stub('알림', 'Phase 1', '규칙·발화상태·발송 3분할 구조.'),
          },

          // 공통
          {
            path: 'notices',
            ...stub('공지', 'Phase 1', '배포 없이 안내를 갱신하는 유일한 수단.'),
          },
          { path: 'voc', ...stub('VOC', 'Phase 1') },
          {
            path: 'guide',
            ...stub('사용자 가이드', 'Phase 1', '런타임으로 제공해 배포 없이 갱신.'),
          },

          // 관리
          { path: 'admin/accounts', element: <AccountsAdminPage /> },
          { path: 'admin/workspaces', element: <WorkspacesAdminPage /> },
          {
            path: 'admin/test-types',
            ...stub('시험종류 정의', 'Phase 2', '정의는 데이터(D7).'),
          },
          { path: 'admin/connectors', ...stub('장비 커넥터', 'Phase 6') },
          { path: 'server', ...stub('서버', 'Phase 1') },

          // 부서 스코프
          {
            path: 'w/:slug',
            children: [
              { index: true, ...stub('부서 홈', 'Phase 1', '최근 등록·처리 대기·내 재료.') },
              { path: 'tests', ...stub('시험 데이터', 'Phase 2') },
              {
                path: 'workbench',
                ...stub('워크벤치', 'Phase 3~4', 'Data → Process → Stats → Fit → Export.'),
              },
              { path: 'statistics', ...stub('통계', 'Phase 3') },
              { path: 'exports', ...stub('내보내기', 'Phase 4') },
              { path: 'members', element: <MembersPage /> },
            ],
          },

          { path: '*', ...stub('없는 페이지', '—', '주소를 확인해 주세요.') },
        ],
      },
    ],
  },
])
