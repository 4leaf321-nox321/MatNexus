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
import MaterialDetailPage from '@/modules/materials/MaterialDetailPage'
import MaterialsPage from '@/modules/materials/MaterialsPage'
import BatchUploadPage from '@/modules/tests/BatchUploadPage'
import FormatProfileEditorPage from '@/modules/tests/FormatProfileEditorPage'
import RecipesPage from '@/modules/processing/RecipesPage'
import UnitsPage from '@/modules/units/UnitsPage'
import FormatProfilesPage from '@/modules/tests/FormatProfilesPage'
import TestTypesPage from '@/modules/tests/TestTypesPage'
import StoragePage from '@/modules/tests/StoragePage'
import TestRunDetailPage from '@/modules/tests/TestRunDetailPage'
import TestRunsPage from '@/modules/tests/TestRunsPage'
import NoticesPage from '@/modules/notices/NoticesPage'
import NotificationsPage from '@/modules/notifications/NotificationsPage'
import SignupPage from '@/modules/auth/SignupPage'
import VocPage from '@/modules/voc/VocPage'
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
          { path: 'materials', element: <MaterialsPage /> },
          { path: 'materials/:id', element: <MaterialDetailPage /> },
          { path: 'test-runs/:id', element: <TestRunDetailPage /> },
          { path: 'compare', ...stub('곡선 비교', 'Phase 3') },

          // 내 활동
          { path: 'personal', ...stub('내 작업함', 'Phase 1') },
          { path: 'notifications', element: <NotificationsPage /> },

          // 공통
          { path: 'notices', element: <NoticesPage /> },
          { path: 'voc', element: <VocPage /> },
          {
            path: 'guide',
            ...stub('사용자 가이드', 'Phase 1', '런타임으로 제공해 배포 없이 갱신.'),
          },

          // 부서 설정 — **`admin/` 아래가 아니다.** 형식 프로파일은 부서 관리자가
          // 만든다. 주소가 `admin/` 이면 메뉴 이름('부서 설정')과 어긋나고, 사람은
          // 주소줄을 보고도 "이건 내 일이 아니구나" 로 읽는다.
          //
          // 라우터가 정적 구간을 동적 구간보다 먼저 고르므로 `new` 는 `:key` 에
          // 먹히지 않는다. 순서에 기대지 않도록 적어 둔다.
          { path: 'settings/test-types', element: <TestTypesPage /> },
          { path: 'settings/recipes', element: <RecipesPage /> },
          { path: 'settings/formats', element: <FormatProfilesPage /> },
          { path: 'settings/formats/new', element: <FormatProfileEditorPage /> },
          { path: 'settings/formats/:key', element: <FormatProfileEditorPage /> },

          // 관리 (전사)
          { path: 'admin/accounts', element: <AccountsAdminPage /> },
          { path: 'admin/workspaces', element: <WorkspacesAdminPage /> },
          { path: 'admin/units', element: <UnitsPage /> },
          { path: 'admin/storage', element: <StoragePage /> },
          { path: 'admin/connectors', ...stub('장비 커넥터', 'Phase 6') },
          { path: 'server', ...stub('서버', 'Phase 1') },

          // 부서 스코프
          {
            path: 'w/:slug',
            children: [
              { index: true, ...stub('부서 홈', 'Phase 1', '최근 등록·처리 대기·내 재료.') },
              { path: 'tests', element: <TestRunsPage /> },
              { path: 'tests/upload', element: <BatchUploadPage /> },
              {
                path: 'workbench',
                ...stub('워크벤치', 'Phase 3~4', 'Data → Process → Stats → Fit → Export.'),
              },
              // 부서 스코프 `statistics`·`exports` 는 뺐다. 워크벤치의 3번·5번
              // 탭과 같은 것이고, 결과 열람은 재료 상세의 '물성'·'CAE 카드' 다
              // — 같은 이름의 빈 화면이 남아 있으면 어느 쪽이 진짜인지 알 수 없다.
              { path: 'members', element: <MembersPage /> },
            ],
          },

          { path: '*', ...stub('없는 페이지', '—', '주소를 확인해 주세요.') },
        ],
      },
    ],
  },
])
